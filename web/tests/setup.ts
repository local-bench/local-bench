import { createHash } from "node:crypto";

// next.config.mjs sets trailingSlash: true; next/link normalizes hrefs via this
// build-time env flag. Without it, test renders strip the canonical trailing
// slashes that production emits, so href pins would test a non-production form.
process.env["__NEXT_TRAILING_SLASH"] = "true";

if (!("DigestStream" in crypto)) {
  class NodeDigestStream extends WritableStream<Uint8Array> {
    readonly digest: Promise<ArrayBuffer>;

    constructor(algorithm: "SHA-256") {
      if (algorithm !== "SHA-256") throw new TypeError(`unsupported digest algorithm: ${algorithm}`);
      const hash = createHash("sha256");
      let resolveDigest: (value: ArrayBuffer) => void = () => undefined;
      let rejectDigest: (reason: unknown) => void = () => undefined;
      const digest = new Promise<ArrayBuffer>((resolve, reject) => {
        resolveDigest = resolve;
        rejectDigest = reject;
      });
      super({
        abort: (reason) => rejectDigest(reason),
        close: () => {
          const bytes = hash.digest();
          resolveDigest(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
        },
        write: (chunk) => {
          hash.update(chunk);
        },
      });
      this.digest = digest;
    }
  }

  Object.defineProperty(crypto, "DigestStream", { configurable: true, value: NodeDigestStream });
}
