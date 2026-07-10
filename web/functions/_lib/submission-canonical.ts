import { digestHex, sha256DigestStream } from "./submission-digest";

export const PAYLOAD_HASH_EXCLUDED_TOP_LEVEL_FIELDS = ["envelope", "signature", "submission_envelope"] as const;
const EXCLUDED_TOP_LEVEL_FIELDS = new Set<string>(PAYLOAD_HASH_EXCLUDED_TOP_LEVEL_FIELDS);

export async function canonicalPayloadSha256(value: unknown): Promise<string> {
  return sha256FragmentsHex(canonicalFragments(value, true));
}

export function canonicalPayloadJson(value: unknown): string {
  return Array.from(canonicalFragments(value, true)).join("");
}

export function canonicalPayloadBytes(value: unknown): Uint8Array<ArrayBuffer> {
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let length = 0;
  for (const chunk of encodedChunks(canonicalFragments(value, true))) {
    chunks.push(chunk);
    length += chunk.byteLength;
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

export function canonicalJson(value: unknown): string {
  return Array.from(canonicalFragments(value, false)).join("");
}

function* canonicalFragments(value: unknown, stripSubmissionMetadata: boolean, depth = 0): Generator<string> {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    yield JSON.stringify(value);
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("canonical JSON only supports finite numbers");
    }
    yield JSON.stringify(value);
    return;
  }
  if (Array.isArray(value)) {
    yield "[";
    for (let index = 0; index < value.length; index += 1) {
      if (index > 0) yield ",";
      yield* canonicalFragments(value[index], false, depth + 1);
    }
    yield "]";
    return;
  }
  if (isRecord(value)) {
    yield "{";
    let emitted = false;
    for (const key of Object.keys(value).sort()) {
      const item = value[key];
      if (item === undefined || (stripSubmissionMetadata && depth === 0 && EXCLUDED_TOP_LEVEL_FIELDS.has(key))) continue;
      if (emitted) yield ",";
      emitted = true;
      yield JSON.stringify(key);
      yield ":";
      yield* canonicalFragments(item, false, depth + 1);
    }
    yield "}";
    return;
  }
  throw new TypeError("canonical JSON only supports JSON values");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function sha256Hex(value: string): Promise<string> {
  return sha256FragmentsHex([value]);
}

async function sha256FragmentsHex(fragments: Iterable<string>): Promise<string> {
  const digest = sha256DigestStream();
  const writer = digest.getWriter();
  for (const chunk of encodedChunks(fragments)) await writer.write(chunk);
  await writer.close();
  return digestHex(await digest.digest);
}

function* encodedChunks(fragments: Iterable<string>): Generator<Uint8Array<ArrayBuffer>> {
  const encoder = new TextEncoder();
  let pending = "";
  for (const fragment of fragments) {
    pending += fragment;
    if (pending.length >= 65_536) {
      yield encoder.encode(pending);
      pending = "";
    }
  }
  if (pending.length > 0) yield encoder.encode(pending);
}
