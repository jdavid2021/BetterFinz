import type { ErrorEvent, EventHint } from "@sentry/nextjs";

const secretKeys = new Set([
  "authorization",
  "cookie",
  "cookies",
  "set_cookie",
  "token",
  "access_token",
  "refresh_token",
  "password",
  "secret",
  "client_secret",
  "api_key",
  "params",
  "parameters",
]);
const identityKeys = new Set(["household_id", "householdid", "user_id", "userid"]);
const accountNumber = /(?<![\w-])\d{8,17}(?![\w-])/g;
const uuid = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi;
const tokenValue = /\b(authorization|cookie|token|password|secret|api[_-]?key)\b(\s*[=:]\s*)([^\s,;]+)/gi;

function pseudonym(value: unknown): string {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `redacted-id:${(hash >>> 0).toString(16)}`;
}

function scrubText(value: string): string {
  return value
    .replace(tokenValue, "$1$2[Filtered]")
    .replace(accountNumber, "[Filtered account number]")
    .replace(uuid, "[Filtered id]");
}

function scrub(value: unknown, key = ""): unknown {
  const normalizedKey = key.toLowerCase().replaceAll("-", "_");
  if (secretKeys.has(normalizedKey)) return "[Filtered]";
  if (identityKeys.has(normalizedKey)) return pseudonym(value);
  if (Array.isArray(value)) return value.map((item) => scrub(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([itemKey, item]) => [itemKey, scrub(item, itemKey)]),
    );
  }
  return typeof value === "string" ? scrubText(value) : value;
}

export function scrubSentryEvent(event: ErrorEvent, _hint: EventHint): ErrorEvent {
  if (event.request) {
    delete event.request.cookies;
    delete event.request.data;
  }
  if (event.user) {
    delete event.user.email;
    if (event.user.id) event.user.id = pseudonym(event.user.id);
  }
  return scrub(event) as ErrorEvent;
}
