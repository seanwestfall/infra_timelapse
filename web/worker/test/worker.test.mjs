import assert from "node:assert/strict";
import test from "node:test";

import { handleRequest } from "../src/index.js";

const ENV = {
  API_BASE_URL: "https://capture-api.example.run.app",
  ORIGIN_AUTH_TOKEN: "origin-secret",
  ALLOWED_ORIGINS: "https://infra.example,https://preview.example",
};

function context() {
  const writes = [];
  return {
    writes,
    waitUntil(promise) {
      writes.push(promise);
    },
  };
}

function memoryCache() {
  const entries = new Map();
  return {
    entries,
    async match(request) {
      return entries.get(request.url)?.clone();
    },
    async put(request, response) {
      entries.set(request.url, response.clone());
    },
  };
}

test("forwards only allowlisted paths and safe headers", async () => {
  const originalFetch = globalThis.fetch;
  let observed;
  globalThis.fetch = async (url, options) => {
    observed = { url: String(url), options };
    return new Response('{"manifests":[]}', {
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": "upstream=secret",
      },
    });
  };
  try {
    const response = await handleRequest(
      new Request("https://infra.example/api/index?ignored=1", {
        headers: {
          Accept: "application/json",
          Authorization: "Bearer browser-token",
          Cookie: "session=browser-cookie",
          Origin: "https://infra.example",
        },
      }),
      ENV,
      context(),
    );
    assert.equal(response.status, 200);
    assert.equal(observed.url, "https://capture-api.example.run.app/api/index");
    assert.equal(observed.options.headers.get("accept"), "application/json");
    assert.equal(
      observed.options.headers.get("X-Infra-Timelapse-Origin-Token"),
      "origin-secret",
    );
    assert.equal(observed.options.headers.has("authorization"), false);
    assert.equal(observed.options.headers.has("cookie"), false);
    assert.equal(response.headers.has("set-cookie"), false);
    assert.equal(
      response.headers.get("access-control-allow-origin"),
      "https://infra.example",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("forwards and caches backend statistics", async () => {
  const originalFetch = globalThis.fetch;
  const cache = memoryCache();
  let calls = 0;
  globalThis.fetch = async (url) => {
    calls += 1;
    assert.equal(String(url), "https://capture-api.example.run.app/api/stats");
    return new Response('{"storage":{"total_bytes":42}}', {
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const url = "https://infra.example/api/stats";
    const ctx = context();
    const first = await handleRequest(new Request(url), ENV, ctx, cache);
    await Promise.all(ctx.writes);
    const second = await handleRequest(new Request(url), ENV, context(), cache);
    assert.equal((await first.json()).storage.total_bytes, 42);
    assert.equal((await second.json()).storage.total_bytes, 42);
    assert.equal(calls, 1);
    assert.equal(
      second.headers.get("cache-control"),
      "public, max-age=300, s-maxage=900",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects traversal, non-PNG paths, and unsupported methods", async () => {
  const cases = [
    "/api/captures/captures/run/../secret.png",
    "/api/captures/captures/run/%2e%2e/secret.png",
    "/api/captures/captures/run/ports/file.jpg",
    "/api/captures/https%3A%2F%2Fexample.com%2Ffile.png",
  ];
  for (const path of cases) {
    const response = await handleRequest(
      new Request(`https://infra.example${path}`),
      ENV,
    );
    assert.equal(response.status, 404, path);
  }
  const post = await handleRequest(
    new Request("https://infra.example/api/index", { method: "POST" }),
    ENV,
  );
  assert.equal(post.status, 405);
});

test("rejects unapproved cross-origin requests", async () => {
  const response = await handleRequest(
    new Request("https://api.example/api/index", {
      headers: { Origin: "https://untrusted.example" },
    }),
    ENV,
  );
  assert.equal(response.status, 403);
});

test("caches successful images but not upstream errors", async () => {
  const originalFetch = globalThis.fetch;
  const cache = memoryCache();
  const ctx = context();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response("PNGDATA", {
      headers: { "Content-Type": "image/png", ETag: '"test-etag"' },
    });
  };
  try {
    const url =
      "https://infra.example/api/captures/captures/run/ports/test/2026-08-08.png";
    const first = await handleRequest(new Request(url), ENV, ctx, cache);
    await Promise.all(ctx.writes);
    const second = await handleRequest(new Request(url), ENV, context(), cache);
    assert.equal(await first.text(), "PNGDATA");
    assert.equal(await second.text(), "PNGDATA");
    assert.equal(calls, 1);
    assert.equal(
      second.headers.get("cache-control"),
      "public, max-age=31536000, immutable",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("does not satisfy byte ranges from an unvarying full-response cache", async () => {
  const originalFetch = globalThis.fetch;
  const cache = memoryCache();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(calls === 1 ? "FULL" : "PART", {
      status: calls === 1 ? 200 : 206,
      headers: {
        "Content-Type": "image/png",
        ...(calls === 1 ? {} : { "Content-Range": "bytes 0-3/8" }),
      },
    });
  };
  try {
    const url =
      "https://infra.example/api/captures/captures/run/ports/test/2026-08-08.png";
    const ctx = context();
    await handleRequest(new Request(url), ENV, ctx, cache);
    await Promise.all(ctx.writes);
    const ranged = await handleRequest(
      new Request(url, { headers: { Range: "bytes=0-3" } }),
      ENV,
      context(),
      cache,
    );
    assert.equal(ranged.status, 206);
    assert.equal(await ranged.text(), "PART");
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fails closed when origin configuration is incomplete", async () => {
  const originalError = console.error;
  console.error = () => {};
  try {
    const response = await handleRequest(
      new Request("https://infra.example/api/index"),
      { API_BASE_URL: ENV.API_BASE_URL },
    );
    assert.equal(response.status, 503);
  } finally {
    console.error = originalError;
  }
});
