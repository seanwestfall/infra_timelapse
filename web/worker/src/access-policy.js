const CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ACCOUNT_ID_PATTERN = /^[0-9a-f]{32}$/i;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const WRITABLE_POLICY_FIELDS = [
  "name",
  "decision",
  "include",
  "exclude",
  "require",
  "precedence",
  "session_duration",
  "approval_groups",
  "approval_required",
  "purpose_justification_prompt",
  "purpose_justification_required",
  "isolation_required",
  "mfa_config",
];

function accessConfiguration(env) {
  const accountId = String(env.CLOUDFLARE_ACCOUNT_ID || "");
  const appId = String(env.ACCESS_APPLICATION_ID || "");
  const policyId = String(env.ACCESS_POLICY_ID || "");
  const token = String(env.CLOUDFLARE_ACCESS_API_TOKEN || "");
  if (
    !ACCOUNT_ID_PATTERN.test(accountId) ||
    !UUID_PATTERN.test(appId) ||
    !UUID_PATTERN.test(policyId) ||
    !token
  ) {
    throw new Error("Cloudflare Access registration is not configured");
  }
  const policyUrl = `${CLOUDFLARE_API_BASE}/accounts/${accountId}/access/apps/${appId}/policies/${policyId}`;
  return { policyUrl, token };
}

async function cloudflareResult(response) {
  const payload = await response.json();
  if (!response.ok || payload.success !== true || !payload.result) {
    throw new Error(`Cloudflare API request failed with status ${response.status}`);
  }
  return payload.result;
}

function policyUpdate(policy, email) {
  if (!Array.isArray(policy.include)) {
    throw new Error("Cloudflare Access policy has no Include rules");
  }
  const normalizedEmail = email.toLowerCase();
  const alreadyIncluded = policy.include.some(
    (rule) => rule?.email?.email?.toLowerCase() === normalizedEmail,
  );
  const update = {};
  for (const field of WRITABLE_POLICY_FIELDS) {
    if (policy[field] !== undefined) update[field] = policy[field];
  }
  if (!alreadyIncluded) {
    update.include = [...policy.include, { email: { email: normalizedEmail } }];
  }
  return { alreadyIncluded, update };
}

export function normalizeEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  if (email.length > 254 || !EMAIL_PATTERN.test(email)) return null;
  const [local, domain, ...extra] = email.split("@");
  if (extra.length || local.length > 64 || domain.length > 253) return null;
  return email;
}

export async function addEmailToAccessPolicy(email, env, fetchApi = fetch) {
  const { policyUrl, token } = accessConfiguration(env);
  const headers = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  const current = await cloudflareResult(
    await fetchApi(policyUrl, { method: "GET", headers }),
  );
  const { alreadyIncluded, update } = policyUpdate(current, email);
  if (alreadyIncluded) return { added: false };

  await cloudflareResult(
    await fetchApi(policyUrl, {
      method: "PUT",
      headers,
      body: JSON.stringify(update),
    }),
  );
  return { added: true };
}
