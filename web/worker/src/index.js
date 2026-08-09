const INDEX_PATH = "/api/index";
const CAPTURE_PREFIX = "/api/captures/";
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

function allowedOrigin(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return { allowed: true, origin: null };
  const allowed = String(env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return { allowed: allowed.includes(origin), origin };
}

function cacheControl(kind) {
  return kind === "index"
    ? "public, max-age=60, s-maxage=300"
    : "public, max-age=31536000, immutable";
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

export async function handleRequest(request, env, ctx = {}, cache = null) {
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

  const route = routeFor(incomingUrl);
  if (!route) return jsonResponse({ error: "Not found" }, 404);

  const cors = allowedOrigin(request, env);
  if (!cors.allowed) return jsonResponse({ error: "Origin not allowed" }, 403);

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
