import assert from "node:assert/strict";
import test from "node:test";

import { confirmEmailToken, requestEmailConfirmation } from "../src/registration.js";

function queuedDatabase(resultSets, observations = []) {
  return () => async (strings, ...values) => {
    observations.push({ query: strings.join("?"), values });
    return resultSets.shift() || [];
  };
}

test("stores a hashed pending token and sends both text and HTML confirmation", async () => {
  const sent = [];
  const queries = [];
  const env = {
    DATABASE_URL: "postgresql://example.test/db",
    CONFIRMATION_PAGE_URL: "https://infra.example/confirm.html",
    EMAIL_SERVICE_URL: "https://email-service.example.run.app",
    EMAIL_ORIGIN_AUTH_TOKEN: "email-origin-secret",
  };
  const result = await requestEmailConfirmation("person@example.com", env, {
    createDatabaseClient: queuedDatabase([[{ email: "person@example.com" }]], queries),
    now: new Date("2026-08-24T00:00:00Z"),
    fetchEmail: async (url, options) => {
      sent.push({ url: String(url), options });
      return new Response(null, { status: 202 });
    },
  });
  assert.deepEqual(result, { sent: true, alreadyConfirmed: false });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "https://email-service.example.run.app/api/email/send");
  assert.equal(
    sent[0].options.headers["X-Infra-Timelapse-Email-Token"],
    "email-origin-secret",
  );
  const message = JSON.parse(sent[0].options.body);
  assert.equal(message.to, "person@example.com");
  assert.match(message.text, /confirm\.html#token=[A-Za-z0-9_-]{43}/);
  assert.match(message.html, /Confirm my email/);
  assert.equal(queries[0].values[0], "person@example.com");
  assert.match(queries[0].values[1], /^[0-9a-f]{64}$/);
  assert.equal(queries[0].values[2], "2026-08-24T00:30:00.000Z");
});

test("does not resend to an already-confirmed address", async () => {
  let sends = 0;
  const result = await requestEmailConfirmation(
    "person@example.com",
    {
      DATABASE_URL: "postgresql://example.test/db",
    },
    {
      createDatabaseClient: queuedDatabase([[]]),
      fetchEmail: async () => { sends += 1; },
    },
  );
  assert.deepEqual(result, { sent: false, alreadyConfirmed: true });
  assert.equal(sends, 0);
});

test("fails when the GCP email service does not accept delivery", async () => {
  await assert.rejects(
    requestEmailConfirmation(
      "person@example.com",
      {
        DATABASE_URL: "postgresql://example.test/db",
        EMAIL_SERVICE_URL: "https://email-service.example.run.app",
        EMAIL_ORIGIN_AUTH_TOKEN: "email-origin-secret",
      },
      {
        createDatabaseClient: queuedDatabase([[{ email: "person@example.com" }]]),
        fetchEmail: async () => new Response(null, { status: 502 }),
      },
    ),
    /Email service returned status 502/,
  );
});

test("confirms a valid token, grants Access, and records the grant", async () => {
  const queries = [];
  const grants = [];
  const token = "b".repeat(43);
  const result = await confirmEmailToken(
    token,
    { DATABASE_URL: "postgresql://example.test/db" },
    async (email) => { grants.push(email); },
    {
      createDatabaseClient: queuedDatabase([
        [{ email: "person@example.com", access_granted_at: null }],
        [],
      ], queries),
    },
  );
  assert.deepEqual(result, { status: "confirmed" });
  assert.deepEqual(grants, ["person@example.com"]);
  assert.equal(queries.length, 2);
  assert.match(queries[0].values[0], /^[0-9a-f]{64}$/);
  assert.equal(queries[1].values[0], "person@example.com");
});

test("rejects malformed or unknown confirmation tokens", async () => {
  assert.deepEqual(
    await confirmEmailToken("bad", {}, async () => {}),
    { status: "invalid" },
  );
  assert.deepEqual(
    await confirmEmailToken(
      "c".repeat(43),
      { DATABASE_URL: "postgresql://example.test/db" },
      async () => {},
      { createDatabaseClient: queuedDatabase([[]]) },
    ),
    { status: "invalid" },
  );
});
