import { DATABASE_PATHS, queryInventory } from "./database.js";
import cloudflareManifest from "../../../deploy/cloudflare-manifest.json" with { type: "json" };

const INDEX_PATH = "/api/index";
const CAPTURE_PREFIX = "/api/captures/";
const SATELLITE_PREFIX = "/api/satellites/";
const CELESTRAK_BASE = "https://celestrak.org/NORAD/elements/gp.php";
const SATELLITES = new Map([
  ["39084", "Landsat 8"],
  ["49260", "Landsat 9"],
  ["42063", "Sentinel-2B"],
  ["60989", "Sentinel-2C"],
]);
const ORIGIN_AUTH_HEADER = "X-Infra-Timelapse-Origin-Token";
const FORWARDED_REQUEST_HEADERS = ["accept", "if-none-match", "range"];
const FORWARDED_RESPONSE_HEADERS = [
  "accept-ranges",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "last-modified",
];
const MANIFEST_ALLOWED_ORIGINS = new Set([
  cloudflareManifest.production.pages_origin,
  ...(cloudflareManifest.cors.additional_exact_origins || []),
]);
const MANIFEST_ALLOWED_SUFFIXES =
  cloudflareManifest.cors.https_subdomain_suffixes || [];

function jsonResponse(body, status, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}

function originBase(value) {
  const base = new URL(String(value || ""));
  const localDevelopment =
    base.protocol === "http:" &&
    ["127.0.0.1", "localhost"].includes(base.hostname);
  if (base.protocol !== "https:" && !localDevelopment) {
    throw new Error("API_BASE_URL must use HTTPS");
  }
  base.pathname = "/";
  base.search = "";
  base.hash = "";
  base.username = "";
  base.password = "";
  return base;
}

function capturePath(pathname) {
  if (!pathname.startsWith(CAPTURE_PREFIX)) return null;
  let objectName;
  try {
    objectName = decodeURIComponent(pathname.slice(CAPTURE_PREFIX.length));
  } catch {
    return null;
  }
  if (
    !objectName.startsWith("captures/") ||
    !objectName.toLowerCase().endsWith(".png") ||
    objectName.includes("\\") ||
    objectName.includes("//")
  ) {
    return null;
  }
  const parts = objectName.split("/");
  if (
    parts.length < 4 ||
    parts.some((part) => !part || part === "." || part === "..") ||
    parts.some((part) => !/^[A-Za-z0-9._-]+$/.test(part))
  ) {
    return null;
  }
  return objectName;
}

function routeFor(url) {
  if (url.pathname === INDEX_PATH) {
    return { kind: "index", upstreamPath: INDEX_PATH };
  }
  const objectName = capturePath(url.pathname);
  if (objectName) {
    const encoded = objectName.split("/").map(encodeURIComponent).join("/");
    return {
      kind: "capture",
      upstreamPath: `${CAPTURE_PREFIX}${encoded}`,
    };
  }
  return null;
}

function satelliteId(pathname) {
  if (!pathname.startsWith(SATELLITE_PREFIX)) return null;
  const match = pathname.match(/^\/api\/satellites\/(\d{5})\/elements$/);
  if (!match || !SATELLITES.has(match[1])) return null;
  return match[1];
}

function allowedOrigin(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return { allowed: true, origin: null };
  const allowed = new Set([
    ...MANIFEST_ALLOWED_ORIGINS,
    ...String(env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
  ]);
  const suffixes = [
    ...MANIFEST_ALLOWED_SUFFIXES,
    ...String(env.ALLOWED_ORIGIN_SUFFIXES || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    String(env.PAGES_PREVIEW_SUFFIX || "").trim(),
  ].filter((suffix) => suffix.startsWith(".") && suffix.length > 1);
  let suffixAllowed = false;
  try {
    const candidate = new URL(origin);
    suffixAllowed = candidate.protocol === "https:" &&
      candidate.origin === origin &&
      suffixes.some((suffix) =>
        candidate.hostname.endsWith(suffix) &&
        candidate.hostname.length > suffix.length
      );
  } catch {
    suffixAllowed = false;
  }
  return { allowed: allowed.has(origin) || suffixAllowed, origin };
}

function cacheControl(kind) {
  return kind === "index"
    ? "public, max-age=60, s-maxage=300"
    : "public, max-age=31536000, immutable";
}

function databaseHeaders(corsOrigin) {
  const headers = {
    "Cache-Control": "public, max-age=60, s-maxage=300",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
  if (corsOrigin) {
    headers["Access-Control-Allow-Origin"] = corsOrigin;
    headers.Vary = "Origin";
  }
  return headers;
}

function satelliteHeaders() {
  return {
    "Cache-Control": "public, max-age=300, s-maxage=7200, stale-if-error=86400",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
}

function responseWithCors(response, corsOrigin, method = "GET") {
  const headers = new Headers(response.headers);
  if (corsOrigin) {
    headers.set("Access-Control-Allow-Origin", corsOrigin);
    headers.set("Vary", "Origin");
  }
  return new Response(method === "HEAD" ? null : response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function satelliteResponse(
  request,
  ctx,
  cache,
  noradId,
  corsOrigin,
  fetchSatelliteElements = fetch,
) {
  const cacheKey = new Request(
    `https://if-api.internal${SATELLITE_PREFIX}${noradId}/elements`,
    { method: "GET" },
  );
  if (cache) {
    const cached = await cache.match(cacheKey);
    if (cached) return responseWithCors(cached, corsOrigin, request.method);
  }

  const upstreamUrl = new URL(CELESTRAK_BASE);
  upstreamUrl.searchParams.set("CATNR", noradId);
  upstreamUrl.searchParams.set("FORMAT", "JSON");
  let upstream;
  try {
    upstream = await fetchSatelliteElements(upstreamUrl, {
      headers: { Accept: "application/json" },
      redirect: "error",
    });
  } catch (error) {
    console.error("CelesTrak request failed", error);
    return jsonResponse({ error: "Satellite elements unavailable" }, 502);
  }
  if (!upstream.ok) {
    console.error("CelesTrak returned", upstream.status);
    return jsonResponse({ error: "Satellite elements unavailable" }, 502);
  }

  let records;
  try {
    records = await upstream.json();
  } catch (error) {
    console.error("CelesTrak returned invalid JSON", error);
    return jsonResponse({ error: "Satellite elements unavailable" }, 502);
  }
  const elements = Array.isArray(records) ? records[0] : null;
  if (!elements || String(elements.NORAD_CAT_ID) !== noradId || !elements.EPOCH) {
    console.error("CelesTrak returned unexpected elements");
    return jsonResponse({ error: "Satellite elements unavailable" }, 502);
  }

  const response = jsonResponse(
    {
      source: "CelesTrak",
      norad_id: Number(noradId),
      name: SATELLITES.get(noradId),
      fetched_at: new Date().toISOString(),
      elements,
    },
    200,
    satelliteHeaders(),
  );
  if (cache) {
    const cacheWrite = cache.put(cacheKey, response.clone());
    if (ctx.waitUntil) ctx.waitUntil(cacheWrite);
    else await cacheWrite;
  }
  return responseWithCors(response, corsOrigin, request.method);
}

async function databaseResponse(
  request,
  env,
  ctx,
  cache,
  kind,
  corsOrigin,
  createDatabaseClient,
) {
  if (!env.DATABASE_URL) {
    console.error("DATABASE_URL is not configured");
    return jsonResponse({ error: "Inventory database is not configured" }, 503);
  }

  const requestUrl = new URL(request.url);
  const cacheUrl = new URL(requestUrl.origin);
  cacheUrl.pathname = requestUrl.pathname;
  if (corsOrigin) cacheUrl.searchParams.set("cors-origin", corsOrigin);
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  if (cache && request.method === "GET") {
    const cached = await cache.match(cacheKey);
    if (cached) return cachedResponseForMethod(cached, request.method);
  }

  let result;
  try {
    result = await queryInventory(kind, env.DATABASE_URL, createDatabaseClient);
  } catch (error) {
    console.error("Inventory database request failed", error);
    return jsonResponse({ error: "Inventory database unavailable" }, 502);
  }

  const response = jsonResponse(result, 200, databaseHeaders(corsOrigin));
  if (cache && request.method === "GET") {
    const cacheWrite = cache.put(cacheKey, response.clone());
    if (ctx.waitUntil) ctx.waitUntil(cacheWrite);
    else await cacheWrite;
  }
  return cachedResponseForMethod(response, request.method);
}

function publicHeaders(upstreamHeaders, kind, corsOrigin) {
  const headers = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstreamHeaders.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("Cache-Control", cacheControl(kind));
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "no-referrer");
  if (corsOrigin) {
    headers.set("Access-Control-Allow-Origin", corsOrigin);
    headers.set("Vary", "Origin");
  }
  return headers;
}

function cachedResponseForMethod(response, method) {
  if (method !== "HEAD") return response;
  return new Response(null, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export async function handleRequest(
  request,
  env,
  ctx = {},
  cache = null,
  dependencies = {},
) {
  const incomingUrl = new URL(request.url);
  if (incomingUrl.pathname === "/healthz") {
    if (!(["GET", "HEAD"].includes(request.method))) {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" },
      });
    }
    const health = jsonResponse({ status: "ok" }, 200);
    return cachedResponseForMethod(health, request.method);
  }

  if (!["GET", "HEAD"].includes(request.method)) {
    return new Response("Method not allowed", {
      status: 405,
      headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" },
    });
  }

  const databaseKind = DATABASE_PATHS.get(incomingUrl.pathname);
  const selectedSatelliteId = satelliteId(incomingUrl.pathname);
  const route = routeFor(incomingUrl);
  if (!route && !databaseKind && !selectedSatelliteId) {
    return jsonResponse({ error: "Not found" }, 404);
  }

  const cors = allowedOrigin(request, env);
  if (!cors.allowed) return jsonResponse({ error: "Origin not allowed" }, 403);

  if (databaseKind) {
    return databaseResponse(
      request,
      env,
      ctx,
      cache,
      databaseKind,
      cors.origin,
      dependencies.createDatabaseClient,
    );
  }

  if (selectedSatelliteId) {
    return satelliteResponse(
      request,
      ctx,
      cache,
      selectedSatelliteId,
      cors.origin,
      dependencies.fetchSatelliteElements,
    );
  }

  let base;
  try {
    base = originBase(env.API_BASE_URL);
  } catch (error) {
    console.error("Invalid API_BASE_URL", error);
    return jsonResponse({ error: "Capture service is not configured" }, 503);
  }
  if (!env.ORIGIN_AUTH_TOKEN) {
    console.error("ORIGIN_AUTH_TOKEN is not configured");
    return jsonResponse({ error: "Capture service is not configured" }, 503);
  }

  const cacheUrl = new URL(incomingUrl.origin);
  cacheUrl.pathname = route.upstreamPath;
  if (cors.origin) cacheUrl.searchParams.set("cors-origin", cors.origin);
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  const cacheEligible = request.method === "GET" && !request.headers.has("range");
  if (cache && cacheEligible) {
    const cached = await cache.match(cacheKey);
    if (cached) return cachedResponseForMethod(cached, request.method);
  }

  const headers = new Headers({
    [ORIGIN_AUTH_HEADER]: env.ORIGIN_AUTH_TOKEN,
  });
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const upstreamUrl = new URL(route.upstreamPath, base);
  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      redirect: "manual",
    });
  } catch (error) {
    console.error("Capture service request failed", error);
    return jsonResponse({ error: "Capture service unavailable" }, 502);
  }

  if (upstreamResponse.status === 404) {
    return jsonResponse({ error: "Capture not found" }, 404);
  }
  if (![200, 206, 304].includes(upstreamResponse.status)) {
    console.error("Capture service returned", upstreamResponse.status);
    return jsonResponse({ error: "Capture service unavailable" }, 502);
  }

  const response = new Response(
    request.method === "HEAD" ? null : upstreamResponse.body,
    {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: publicHeaders(upstreamResponse.headers, route.kind, cors.origin),
    },
  );
  if (cache && cacheEligible && upstreamResponse.status === 200) {
    const cacheWrite = cache.put(cacheKey, response.clone());
    if (ctx.waitUntil) ctx.waitUntil(cacheWrite);
    else await cacheWrite;
  }
  return response;
}

export default {
  fetch(request, env, ctx) {
    return handleRequest(request, env, ctx, globalThis.caches?.default || null);
  },
};
