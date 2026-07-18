export type TicketPop = {
  readonly signature: string;
  readonly timestamp: string;
};

export type PopVerificationResult = "ok" | "invalid" | "stale";

const POP_MAX_AGE_MILLISECONDS = 10 * 60 * 1000;

export async function verifyTicketPop(
  publicKeyHex: string,
  bundleSha256: string,
  suiteReleaseId: string,
  suiteManifestSha256: string,
  pop: TicketPop | undefined,
): Promise<PopVerificationResult> {
  if (pop === undefined) {
    return "invalid";
  }
  const timestampMilliseconds = Date.parse(pop.timestamp);
  if (!Number.isFinite(timestampMilliseconds)) {
    return "invalid";
  }
  if (Math.abs(Date.now() - timestampMilliseconds) > POP_MAX_AGE_MILLISECONDS) {
    return "stale";
  }
  const message = [
    "localbench.ticket_pop.v1",
    bundleSha256,
    suiteReleaseId,
    suiteManifestSha256,
    pop.timestamp,
  ].join("\n");
  return await verifyEd25519(publicKeyHex, pop.signature, message) ? "ok" : "invalid";
}

export async function verifyCommunityGroupPop(
  publicKeyHex: string,
  declaredModelName: string,
  pop: TicketPop,
): Promise<PopVerificationResult> {
  const timestampMilliseconds = Date.parse(pop.timestamp);
  if (!Number.isFinite(timestampMilliseconds)) return "invalid";
  if (Math.abs(Date.now() - timestampMilliseconds) > POP_MAX_AGE_MILLISECONDS) return "stale";
  const message = `localbench.community_group_pop.v1\n${declaredModelName}\n${pop.timestamp}`;
  return await verifyEd25519(publicKeyHex, pop.signature, message) ? "ok" : "invalid";
}

export async function verifyAccountBindPop(
  publicKeyHex: string,
  githubUserId: string,
  pop: TicketPop,
): Promise<PopVerificationResult> {
  const timestampMilliseconds = Date.parse(pop.timestamp);
  if (!Number.isFinite(timestampMilliseconds)) return "invalid";
  if (Math.abs(Date.now() - timestampMilliseconds) > POP_MAX_AGE_MILLISECONDS) return "stale";
  const message = `localbench.account_bind.v1\n${githubUserId}\n${pop.timestamp}`;
  return await verifyEd25519(publicKeyHex, pop.signature, message) ? "ok" : "invalid";
}

export async function verifyEd25519(publicKeyHex: string, signatureHex: string, message: string | Uint8Array<ArrayBuffer>): Promise<boolean> {
  try {
    const publicKey = await crypto.subtle.importKey("raw", hexBytes(publicKeyHex), "Ed25519", false, ["verify"]);
    return await crypto.subtle.verify(
      "Ed25519",
      publicKey,
      hexBytes(signatureHex),
      typeof message === "string" ? new TextEncoder().encode(message) : message,
    );
  } catch (error) {
    if (error instanceof Error) {
      return false;
    }
    return false;
  }
}

function hexBytes(hex: string): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(hex.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    const parsed = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
    bytes[index] = parsed;
  }
  return bytes;
}
