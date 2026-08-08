const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "if-none-match",
  "range",
];

function upstreamBase(value) {
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

export async function onRequest(context) {
  if (!["GET", "HEAD"].includes(context.request.method)) {
    return new Response("Method not allowed", {
      status: 405,
      headers: { Allow: "GET, HEAD" },
    });
  }

  let base;
  try {
    base = upstreamBase(context.env.API_BASE_URL);
  } catch (error) {
    console.error("Invalid API_BASE_URL", error);
    return new Response("Capture service is not configured", { status: 503 });
  }

  const incoming = new URL(context.request.url);
  const upstream = new URL(`${incoming.pathname}${incoming.search}`, base);
  const headers = new Headers();
  FORWARDED_REQUEST_HEADERS.forEach((name) => {
    const value = context.request.headers.get(name);
    if (value) headers.set(name, value);
  });

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstream, {
      method: context.request.method,
      headers,
      redirect: "manual",
    });
  } catch (error) {
    console.error("Capture service request failed", error);
    return new Response("Capture service unavailable", { status: 502 });
  }
  const responseHeaders = new Headers(upstreamResponse.headers);
  responseHeaders.delete("set-cookie");
  responseHeaders.set("X-Content-Type-Options", "nosniff");
  return new Response(
    context.request.method === "HEAD" ? null : upstreamResponse.body,
    {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: responseHeaders,
    }
  );
}
