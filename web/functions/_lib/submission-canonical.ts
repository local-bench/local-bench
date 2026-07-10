import { digestHex, sha256DigestStream } from "./submission-digest";

export function canonicalJson(value: unknown): string {
  return Array.from(canonicalFragments(value)).join("");
}

function* canonicalFragments(value: unknown): Generator<string> {
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
      yield* canonicalFragments(value[index]);
    }
    yield "]";
    return;
  }
  if (isRecord(value)) {
    yield "{";
    let emitted = false;
    for (const key of Object.keys(value).sort()) {
      const item = value[key];
      if (item === undefined) continue;
      if (emitted) yield ",";
      emitted = true;
      yield JSON.stringify(key);
      yield ":";
      yield* canonicalFragments(item);
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
