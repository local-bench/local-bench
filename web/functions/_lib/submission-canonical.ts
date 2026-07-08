export const PAYLOAD_HASH_EXCLUDED_TOP_LEVEL_FIELDS = ["envelope", "signature", "submission_envelope"] as const;
const EXCLUDED_TOP_LEVEL_FIELDS = new Set<string>(PAYLOAD_HASH_EXCLUDED_TOP_LEVEL_FIELDS);

type JsonValue = null | boolean | number | string | readonly JsonValue[] | { readonly [key: string]: JsonValue };

export async function canonicalPayloadSha256(value: unknown): Promise<string> {
  return sha256Hex(canonicalJson(stripSubmissionMetadata(value)));
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(normalizeJsonValue(value));
}

function stripSubmissionMetadata(value: unknown): unknown {
  if (!isRecord(value)) {
    return value;
  }
  const stripped: Record<string, unknown> = {};
  for (const key of Object.keys(value).sort()) {
    if (!EXCLUDED_TOP_LEVEL_FIELDS.has(key)) {
      stripped[key] = value[key];
    }
  }
  return stripped;
}

function normalizeJsonValue(value: unknown): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("canonical JSON only supports finite numbers");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeJsonValue(item));
  }
  if (isRecord(value)) {
    const normalized: Record<string, JsonValue> = {};
    for (const key of Object.keys(value).sort()) {
      const item = value[key];
      if (item !== undefined) {
        normalized[key] = normalizeJsonValue(item);
      }
    }
    return normalized;
  }
  throw new TypeError("canonical JSON only supports JSON values");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
