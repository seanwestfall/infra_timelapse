import { DATABASE_PATHS, queryInventory } from "./database.js";
import cloudflareManifest from "../../../deploy/cloudflare-manifest.json" with { type: "json" };

const INDEX_PATH = "/api/index";
const CAPTURE_PREFIX = "/api/captures/";
const SATELLITE_PREFIX = "/api/satellites/";
const API_VERSION_PREFIX = "/api/v1";
const CELESTRAK_BASE = "https://celestrak.org/NORAD/elements/gp.php";
const SATELLITES = new Map([
  ["39084", "Landsat 8"],
  ["49260", "Landsat 9"],
  ["42063", "Sentinel-2B"],
  ["60989", "Sentinel-2C"],
]);
const FALLBACK_SATELLITE_ELEMENTS = new Map([
  ["39084", { OBJECT_NAME: "LANDSAT 8", OBJECT_ID: "2013-008A", EPOCH: "2026-08-22T15:13:47.149536", MEAN_MOTION: 14.5710376, ECCENTRICITY: 0.00012666, INCLINATION: 98.2253, RA_OF_ASC_NODE: 303.9635, ARG_OF_PERICENTER: 93.6891, MEAN_ANOMALY: 266.4453, EPHEMERIS_TYPE: 0, CLASSIFICATION_TYPE: "U", NORAD_CAT_ID: 39084, ELEMENT_SET_NO: 999, REV_AT_EPOCH: 70757, BSTAR: 6.0750701e-5, MEAN_MOTION_DOT: 2.28e-6, MEAN_MOTION_DDOT: 0 }],
  ["49260", { OBJECT_NAME: "LANDSAT 9", OBJECT_ID: "2021-088A", EPOCH: "2026-08-22T14:24:23.936256", MEAN_MOTION: 14.57099128, ECCENTRICITY: 0.00012878, INCLINATION: 98.2234, RA_OF_ASC_NODE: 303.9571, ARG_OF_PERICENTER: 105.3989, MEAN_ANOMALY: 254.7352, EPHEMERIS_TYPE: 0, CLASSIFICATION_TYPE: "U", NORAD_CAT_ID: 49260, ELEMENT_SET_NO: 999, REV_AT_EPOCH: 26067, BSTAR: 6.5256727e-5, MEAN_MOTION_DOT: 2.49e-6, MEAN_MOTION_DDOT: 0 }],
  ["42063", { OBJECT_NAME: "SENTINEL-2B", OBJECT_ID: "2017-013A", EPOCH: "2026-08-22T15:23:05.430912", MEAN_MOTION: 14.30814937, ECCENTRICITY: 0.00012592, INCLINATION: 98.565, RA_OF_ASC_NODE: 308.4637, ARG_OF_PERICENTER: 87.8936, MEAN_ANOMALY: 272.2392, EPHEMERIS_TYPE: 0, CLASSIFICATION_TYPE: "U", NORAD_CAT_ID: 42063, ELEMENT_SET_NO: 999, REV_AT_EPOCH: 49414, BSTAR: -3.991811e-6, MEAN_MOTION_DOT: -5.4e-7, MEAN_MOTION_DDOT: 0 }],
  ["60989", { OBJECT_NAME: "SENTINEL-2C", OBJECT_ID: "2024-157A", EPOCH: "2026-08-22T11:11:21.431328", MEAN_MOTION: 14.30815408, ECCENTRICITY: 0.00014142, INCLINATION: 98.5651, RA_OF_ASC_NODE: 308.2963, ARG_OF_PERICENTER: 101.0772, MEAN_ANOMALY: 259.057, EPHEMERIS_TYPE: 0, CLASSIFICATION_TYPE: "U", NORAD_CAT_ID: 60989, ELEMENT_SET_NO: 999, REV_AT_EPOCH: 10246, BSTAR: 3.9756661e-5, MEAN_MOTION_DOT: 6.1e-7, MEAN_MOTION_DDOT: 0 }],
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
  const pathname = canonicalApiPath(url.pathname);
  if (pathname === INDEX_PATH) {
    return { kind: "index", upstreamPath: INDEX_PATH };
  }
  const objectName = capturePath(pathname);
  if (objectName) {
    const encoded = objectName.split("/").map(encodeURIComponent).join("/");
    return {
      kind: "capture",
      upstreamPath: `${CAPTURE_PREFIX}${encoded}`,
    };
  }
  return null;
}

function canonicalApiPath(pathname) {
  if (pathname === API_VERSION_PREFIX) return "/api";
  if (pathname.startsWith(`${API_VERSION_PREFIX}/`)) {
    return `/api${pathname.slice(API_VERSION_PREFIX.length)}`;
  }
  return pathname;
}

function satelliteId(pathname) {
  pathname = canonicalApiPath(pathname);
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

function fallbackSatelliteResponse(request, noradId, corsOrigin) {
  return responseWithCors(
    jsonResponse(
      {
        source: "CelesTrak snapshot",
        norad_id: Number(noradId),
        name: SATELLITES.get(noradId),
        fetched_at: FALLBACK_SATELLITE_ELEMENTS.get(noradId).EPOCH,
        stale: true,
        elements: FALLBACK_SATELLITE_ELEMENTS.get(noradId),
      },
      200,
      { ...satelliteHeaders(), Warning: '110 - "Using cached orbital elements"' },
    ),
    corsOrigin,
    request.method,
  );
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
      headers: {
        Accept: "application/json",
        "User-Agent": "InfraTimelapse-SatelliteTracker/1.0",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(3000),
    });
  } catch (error) {
    console.error("CelesTrak request failed", error);
    return fallbackSatelliteResponse(request, noradId, corsOrigin);
  }
  if (!upstream.ok) {
    console.error("CelesTrak returned", upstream.status);
    return fallbackSatelliteResponse(request, noradId, corsOrigin);
  }

  let records;
  try {
    records = await upstream.json();
  } catch (error) {
    console.error("CelesTrak returned invalid JSON", error);
    return fallbackSatelliteResponse(request, noradId, corsOrigin);
  }
  const elements = Array.isArray(records) ? records[0] : null;
  if (!elements || String(elements.NORAD_CAT_ID) !== noradId || !elements.EPOCH) {
    console.error("CelesTrak returned unexpected elements");
    return fallbackSatelliteResponse(request, noradId, corsOrigin);
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

  const databaseKind = DATABASE_PATHS.get(canonicalApiPath(incomingUrl.pathname));
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
