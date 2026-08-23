import assert from "node:assert/strict";
import test from "node:test";

import { handleRequest } from "../src/index.js";

const ENV = {
  API_BASE_URL: "https://capture-api.example.run.app",
  ORIGIN_AUTH_TOKEN: "origin-secret",
  DATABASE_URL: "postgresql://inventory.example/test",
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

test("serves v1 routes while retaining the legacy API contract", async () => {
  const originalFetch = globalThis.fetch;
  const observed = [];
  globalThis.fetch = async (url) => {
    observed.push(String(url));
    return new Response('{"manifests":[]}');
  };
  try {
    for (const path of ["/api/index", "/api/v1/index"]) {
      const response = await handleRequest(
        new Request(`https://infra.example${path}`),
        ENV,
        context(),
      );
      assert.equal(response.status, 200, path);
    }
    assert.deepEqual(observed, [
      "https://capture-api.example.run.app/api/index",
      "https://capture-api.example.run.app/api/index",
    ]);

    const inventory = await handleRequest(
      new Request("https://infra.example/api/v1/nodes"),
      ENV,
      context(),
      null,
      { createDatabaseClient: () => async () => [] },
    );
    assert.equal(inventory.status, 200);
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

test("always allows origins declared by the deployment manifest", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('{"manifests":[]}');
  try {
    for (const origin of [
      "https://infratimelapse.pages.dev",
      "https://feature-abc.infratimelapse.pages.dev",
    ]) {
      const response = await handleRequest(
        new Request("https://api.example/api/index", {
          headers: { Origin: origin },
        }),
        {
          ...ENV,
          ALLOWED_ORIGINS: "",
          ALLOWED_ORIGIN_SUFFIXES: "",
          PAGES_PREVIEW_SUFFIX: "",
        },
        context(),
      );
      assert.equal(response.status, 200, origin);
      assert.equal(response.headers.get("access-control-allow-origin"), origin);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("manifest suffixes do not trust the suffix apex or lookalike domains", async () => {
  for (const origin of [
    "http://feature-abc.infratimelapse.pages.dev",
    "https://infratimelapse.pages.dev.evil.example",
    "https://evilpages.dev",
  ]) {
    const response = await handleRequest(
      new Request("https://api.example/api/index", {
        headers: { Origin: origin },
      }),
      {
        ...ENV,
        ALLOWED_ORIGINS: "",
        ALLOWED_ORIGIN_SUFFIXES: "",
        PAGES_PREVIEW_SUFFIX: "",
      },
    );
    assert.equal(response.status, 403, origin);
  }
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

test("returns node inventory from the infratimelapse schema", async () => {
  let connectionString;
  let queryText;
  const rows = [
    {
      code: "n-lianyungang-port",
      name: "Lianyungang Port",
      record_status: "draft",
      node_type: "seaport",
      monitoring_tier: "priority",
      jurisdictions: [{ iso2: "CN", role: "primary" }],
      geometry: { type: "Point", coordinates: [119.4333, 34.7167] },
    },
  ];
  const createDatabaseClient = (value) => {
    connectionString = value;
    return async (strings) => {
      queryText = strings.join("");
      return rows;
    };
  };

  const response = await handleRequest(
    new Request("https://infra.example/api/nodes", {
      headers: { Origin: "https://infra.example" },
    }),
    ENV,
    context(),
    null,
    { createDatabaseClient },
  );

  assert.equal(response.status, 200);
  assert.equal(connectionString, ENV.DATABASE_URL);
  assert.match(queryText, /FROM infratimelapse\.nodes AS n/);
  assert.equal(response.headers.get("cache-control"), "public, max-age=60, s-maxage=300");
  assert.equal(response.headers.get("access-control-allow-origin"), "https://infra.example");
  assert.deepEqual(await response.json(), {
    schema: "infratimelapse",
    count: 1,
    data: rows,
  });
});

test("serves all read-only database routes and caches successful results", async () => {
  const cache = memoryCache();
  const expectedTable = new Map([
    ["/api/nodes", "nodes"],
    ["/api/corridors", "corridors"],
    ["/api/projects", "projects"],
  ]);
  for (const [path, table] of expectedTable) {
    let calls = 0;
    const createDatabaseClient = () => async (strings) => {
      calls += 1;
      assert.match(strings.join(""), new RegExp(`infratimelapse\\.${table}`));
      return [];
    };
    const url = `https://infra.example${path}`;
    const ctx = context();
    const first = await handleRequest(
      new Request(url),
      ENV,
      ctx,
      cache,
      { createDatabaseClient },
    );
    await Promise.all(ctx.writes);
    const second = await handleRequest(
      new Request(url),
      ENV,
      context(),
      cache,
      { createDatabaseClient },
    );
    assert.equal(first.status, 200);
    assert.equal(second.status, 200);
    assert.equal(calls, 1);
  }
});

test("fails closed without a database secret and hides database errors", async () => {
  const originalError = console.error;
  console.error = () => {};
  try {
    const missingSecret = await handleRequest(
      new Request("https://infra.example/api/nodes"),
      { ...ENV, DATABASE_URL: undefined },
    );
    assert.equal(missingSecret.status, 503);
    assert.deepEqual(await missingSecret.json(), {
      error: "Inventory database is not configured",
    });

    const failedQuery = await handleRequest(
      new Request("https://infra.example/api/corridors"),
      ENV,
      context(),
      null,
      {
        createDatabaseClient: () => async () => {
          throw new Error(`connection failed: ${ENV.DATABASE_URL}`);
        },
      },
    );
    assert.equal(failedQuery.status, 502);
    assert.deepEqual(await failedQuery.json(), {
      error: "Inventory database unavailable",
    });
  } finally {
    console.error = originalError;
  }
});

test("serves allowlisted CelesTrak elements and caches them independently of CORS", async () => {
  const cache = memoryCache();
  const ctx = context();
  let calls = 0;
  let observedUrl;
  let observedOptions;
  const fetchSatelliteElements = async (url, options) => {
    calls += 1;
    observedUrl = String(url);
    observedOptions = options;
    return Response.json([
      {
        OBJECT_NAME: "LANDSAT 8",
        NORAD_CAT_ID: 39084,
        EPOCH: "2026-08-14T00:00:00.000000",
        MEAN_MOTION: 14.571,
      },
    ]);
  };

  const first = await handleRequest(
    new Request("https://api.example/api/satellites/39084/elements", {
      headers: { Origin: "https://infra.example" },
    }),
    ENV,
    ctx,
    cache,
    { fetchSatelliteElements },
  );
  await Promise.all(ctx.writes);
  const second = await handleRequest(
    new Request("https://api.example/api/satellites/39084/elements", {
      headers: { Origin: "https://preview.example" },
    }),
    ENV,
    context(),
    cache,
    { fetchSatelliteElements },
  );

  assert.equal(first.status, 200);
  assert.equal(second.status, 200);
  assert.equal(calls, 1);
  assert.equal(
    observedUrl,
    "https://celestrak.org/NORAD/elements/gp.php?CATNR=39084&FORMAT=JSON",
  );
  assert.equal(observedOptions.redirect, "follow");
  assert.equal(observedOptions.headers.Accept, "application/json");
  assert.equal(
    first.headers.get("cache-control"),
    "public, max-age=300, s-maxage=7200, stale-if-error=86400",
  );
  assert.equal(
    first.headers.get("access-control-allow-origin"),
    "https://infra.example",
  );
  assert.equal(
    second.headers.get("access-control-allow-origin"),
    "https://preview.example",
  );
  const payload = await first.json();
  assert.equal(payload.source, "CelesTrak");
  assert.equal(payload.norad_id, 39084);
  assert.equal(payload.name, "Landsat 8");
  assert.equal(payload.elements.OBJECT_NAME, "LANDSAT 8");
});

test("rejects unlisted satellites and falls back when CelesTrak fails", async () => {
  let calls = 0;
  const fetchSatelliteElements = async () => {
    calls += 1;
    return new Response("temporarily unavailable", { status: 503 });
  };

  const unknown = await handleRequest(
    new Request("https://api.example/api/satellites/25544/elements"),
    ENV,
    context(),
    null,
    { fetchSatelliteElements },
  );
  assert.equal(unknown.status, 404);
  assert.equal(calls, 0);

  const originalError = console.error;
  console.error = () => {};
  try {
    const failed = await handleRequest(
      new Request("https://api.example/api/satellites/49260/elements", {
        headers: { Origin: "https://infra.example" },
      }),
      ENV,
      context(),
      null,
      { fetchSatelliteElements },
    );
    assert.equal(failed.status, 200);
    const fallback = await failed.json();
    assert.equal(fallback.source, "CelesTrak snapshot");
    assert.equal(fallback.stale, true);
    assert.equal(fallback.norad_id, 49260);
    assert.equal(fallback.elements.NORAD_CAT_ID, 49260);
    assert.equal(
      failed.headers.get("access-control-allow-origin"),
      "https://infra.example",
    );
    assert.equal(calls, 1);
  } finally {
    console.error = originalError;
  }
});
