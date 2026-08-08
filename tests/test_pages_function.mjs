import assert from "node:assert/strict";
import test from "node:test";

import { onRequest } from "../functions/api/[[path]].js";


test("Pages Function forwards only safe request headers", async () => {
  const originalFetch = globalThis.fetch;
  let observed;
  globalThis.fetch = async (url, options) => {
    observed = { url: String(url), options };
    return new Response('{"status":"ok"}', {
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const response = await onRequest({
      env: { API_BASE_URL: "https://capture-api.example.run.app" },
      request: new Request("https://dashboard.example/api/index?fresh=1", {
        headers: {
          Accept: "application/json",
          Authorization: "Bearer browser-token",
          Cookie: "session=browser-cookie",
        },
      }),
    });

    assert.equal(response.status, 200);
    assert.equal(
      observed.url,
      "https://capture-api.example.run.app/api/index?fresh=1"
    );
    assert.equal(observed.options.headers.get("accept"), "application/json");
    assert.equal(observed.options.headers.has("authorization"), false);
    assert.equal(observed.options.headers.has("cookie"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("Pages Function fails closed without a valid API base", async () => {
  const originalError = console.error;
  console.error = () => {};
  let response;
  try {
    response = await onRequest({
      env: {},
      request: new Request("https://dashboard.example/api/index"),
    });
  } finally {
    console.error = originalError;
  }

  assert.equal(response.status, 503);
});
