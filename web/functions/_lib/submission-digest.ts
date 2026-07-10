export type Sha256DigestStream = WritableStream<Uint8Array> & {
  readonly digest: Promise<ArrayBuffer>;
};

type DigestStreamConstructor = new (algorithm: "SHA-256") => Sha256DigestStream;

export function sha256DigestStream(): Sha256DigestStream {
  const workerCrypto = crypto as Crypto & { readonly DigestStream: DigestStreamConstructor };
  return new workerCrypto.DigestStream("SHA-256");
}

export function digestHex(digest: ArrayBuffer): string {
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
