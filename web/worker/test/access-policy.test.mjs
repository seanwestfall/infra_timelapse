import assert from "node:assert/strict";
import test from "node:test";

import { addEmailToAccessPolicy, normalizeEmail } from "../src/access-policy.js";

const ENV = {
  CLOUDFLARE_ACCOUNT_ID: "0123456789abcdef0123456789abcdef",
  ACCESS_APPLICATION_ID: "123e4567-e89b-42d3-a456-426614174000",
  ACCESS_POLICY_ID: "123e4567-e89b-42d3-a456-426614174001",
  CLOUDFLARE_ACCESS_API_TOKEN: "secret-token",
};

function apiResponse(result, status = 200) {
  return new Response(JSON.stringify({ success: status < 400, result }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("normalizes plausible email addresses and rejects invalid values", () => {
  assert.equal(normalizeEmail(" Person@Example.COM "), "person@example.com");
  assert.equal(normalizeEmail("missing-at.example.com"), null);
  assert.equal(normalizeEmail("two@@example.com"), null);
});

test("adds an exact email rule while preserving writable policy fields", async () => {
  const calls = [];
  const fetchApi = async (url, options) => {
    calls.push({ url, options });
    if (options.method === "GET") {
      return apiResponse({
        id: ENV.ACCESS_POLICY_ID,
        created_at: "ignored",
        name: "Private preview",
        decision: "allow",
        include: [{ email: { email: "existing@example.com" } }],
        exclude: [{ geo: { country_code: "AQ" } }],
        precedence: 1,
      });
    }
    return apiResponse({ id: ENV.ACCESS_POLICY_ID });
  };

  const result = await addEmailToAccessPolicy("new@example.com", ENV, fetchApi);
  assert.deepEqual(result, { added: true });
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/accounts\/0123456789abcdef0123456789abcdef\/access\/apps\//);
  assert.equal(calls[0].options.headers.Authorization, "Bearer secret-token");
  const update = JSON.parse(calls[1].options.body);
  assert.deepEqual(update.include.at(-1), { email: { email: "new@example.com" } });
  assert.deepEqual(update.exclude, [{ geo: { country_code: "AQ" } }]);
  assert.equal(update.created_at, undefined);
});

test("does not update a policy that already includes the email", async () => {
  let calls = 0;
  const result = await addEmailToAccessPolicy("member@example.com", ENV, async () => {
    calls += 1;
    return apiResponse({
      name: "Private preview",
      decision: "allow",
      include: [{ email: { email: "MEMBER@example.com" } }],
    });
  });
  assert.deepEqual(result, { added: false });
  assert.equal(calls, 1);
});
