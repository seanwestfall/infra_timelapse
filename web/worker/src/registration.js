import { neon } from "@neondatabase/serverless";

import cloudflareManifest from "../../../deploy/cloudflare-manifest.json" with { type: "json" };

const TOKEN_LIFETIME_MS = 30 * 60 * 1000;
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{43}$/;

function bytesToHex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function tokenHash(token) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return bytesToHex(new Uint8Array(digest));
}

function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function confirmationPageUrl(env, token) {
  const configured = String(env.CONFIRMATION_PAGE_URL || "").trim();
  const page = new URL(
    configured || "/confirm.html",
    cloudflareManifest.production.pages_origin,
  );
  if (page.protocol !== "https:" || page.username || page.password || page.search || page.hash) {
    throw new Error("CONFIRMATION_PAGE_URL must be a clean HTTPS URL");
  }
  page.hash = `token=${token}`;
  return page.href;
}

function emailServiceConfiguration(env) {
  const serviceUrl = new URL(String(env.EMAIL_SERVICE_URL || ""));
  if (serviceUrl.protocol !== "https:" || serviceUrl.username || serviceUrl.password) {
    throw new Error("EMAIL_SERVICE_URL must use HTTPS");
  }
  serviceUrl.pathname = "/api/email/send";
  serviceUrl.search = "";
  serviceUrl.hash = "";
  const token = String(env.EMAIL_ORIGIN_AUTH_TOKEN || "");
  if (!token) throw new Error("EMAIL_ORIGIN_AUTH_TOKEN is not configured");
  return { serviceUrl, token };
}

async function sendConfirmationEmail(email, link, env, fetchEmail) {
  const { serviceUrl, token } = emailServiceConfiguration(env);
  const response = await fetchEmail(serviceUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Infra-Timelapse-Email-Token": token,
    },
    body: JSON.stringify({
      to: email,
      subject: "Confirm your Infra Timelapse access",
      text: `Confirm your email address to request access to Infra Timelapse Explorer:\n\n${link}\n\nThis link expires in 30 minutes. If you did not request access, you can ignore this email.`,
      html: `<p>Confirm your email address to request access to Infra Timelapse Explorer.</p><p><a href="${link}">Confirm my email</a></p><p>This link expires in 30 minutes. If you did not request access, you can ignore this email.</p>`,
    }),
    redirect: "manual",
    signal: AbortSignal.timeout(10_000),
  });
  if (response.status !== 202) {
    throw new Error(`Email service returned status ${response.status}`);
  }
}

async function storePending(email, token, databaseUrl, createClient, now) {
  if (!databaseUrl) throw new Error("DATABASE_URL is not configured");
  const sql = createClient(databaseUrl);
  const hash = await tokenHash(token);
  const expiresAt = new Date(now.getTime() + TOKEN_LIFETIME_MS).toISOString();
  const rows = await sql`
    INSERT INTO infratimelapse.access_registrations (
      email, confirmation_token_hash, token_expires_at, requested_at
    ) VALUES (
      ${email}, decode(${hash}, 'hex'), ${expiresAt}, now()
    )
    ON CONFLICT (email) DO UPDATE SET
      confirmation_token_hash = EXCLUDED.confirmation_token_hash,
      token_expires_at = EXCLUDED.token_expires_at,
      requested_at = now()
    WHERE infratimelapse.access_registrations.confirmed_at IS NULL
    RETURNING email
  `;
  return rows.length > 0;
}

export async function requestEmailConfirmation(
  email,
  env,
  { createDatabaseClient = neon, now = new Date(), fetchEmail = fetch } = {},
) {
  const token = newToken();
  const shouldSend = await storePending(
    email,
    token,
    env.DATABASE_URL,
    createDatabaseClient,
    now,
  );
  if (!shouldSend) return { sent: false, alreadyConfirmed: true };

  const link = confirmationPageUrl(env, token);
  await sendConfirmationEmail(email, link, env, fetchEmail);
  return { sent: true, alreadyConfirmed: false };
}

export async function confirmEmailToken(
  token,
  env,
  addEmailToPolicy,
  { createDatabaseClient = neon } = {},
) {
  if (!TOKEN_PATTERN.test(String(token || ""))) return { status: "invalid" };
  if (!env.DATABASE_URL) throw new Error("DATABASE_URL is not configured");
  const sql = createDatabaseClient(env.DATABASE_URL);
  const hash = await tokenHash(token);
  const rows = await sql`
    UPDATE infratimelapse.access_registrations
    SET confirmed_at = COALESCE(confirmed_at, now())
    WHERE confirmation_token_hash = decode(${hash}, 'hex')
      AND (confirmed_at IS NOT NULL OR token_expires_at > now())
    RETURNING email, access_granted_at
  `;
  if (!rows.length) return { status: "invalid" };
  const registration = rows[0];
  if (registration.access_granted_at) return { status: "confirmed" };

  await addEmailToPolicy(registration.email, env);
  await sql`
    UPDATE infratimelapse.access_registrations
    SET access_granted_at = now()
    WHERE email = ${registration.email}
      AND access_granted_at IS NULL
  `;
  return { status: "confirmed" };
}
