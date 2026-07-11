import { AwsClient } from "aws4fetch";
import {
  MAX_UPLOAD_BYTES,
  SUBMISSIONS_BUCKET_NAME,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { digestHex, sha256DigestStream } from "./submission-digest";

type R2SigningConfig = {
  readonly accessKeyId: string;
  readonly accountId: string;
  readonly bucketName: string;
  readonly secretAccessKey: string;
};

export type RawBundleVerification =
  | { readonly kind: "ok"; readonly sizeBytes: number }
  | { readonly kind: "error"; readonly code: string; readonly error: string; readonly status: number };

export type RawBundleMetadata =
  | { readonly kind: "ok"; readonly size: number | null }
  | { readonly kind: "error"; readonly code: string; readonly error: string; readonly status: number };

export async function rawBundleMetadata(env: SubmissionApiEnv, rawBundleSha256: string): Promise<RawBundleMetadata> {
  if (env.SUBMISSIONS.head !== undefined) {
    const object = await env.SUBMISSIONS.head(rawBundleKey(rawBundleSha256));
    if (object === null) {
      return { code: "raw_bundle_missing", error: "raw bundle is not present in R2", kind: "error", status: 404 };
    }
    return { kind: "ok", size: object.size ?? null };
  }
  const object = await env.SUBMISSIONS.get(rawBundleKey(rawBundleSha256));
  if (object === null) {
    return { code: "raw_bundle_missing", error: "raw bundle is not present in R2", kind: "error", status: 404 };
  }
  return { kind: "ok", size: object.size ?? null };
}

export async function verifyRawBundle(env: SubmissionApiEnv, rawBundleSha256: string): Promise<RawBundleVerification> {
  const object = await env.SUBMISSIONS.get(rawBundleKey(rawBundleSha256));
  if (object === null) {
    return { code: "raw_bundle_missing", error: "raw bundle is not present in R2", kind: "error", status: 404 };
  }
  const digest = sha256DigestStream();
  const reader = object.body.getReader();
  const writer = digest.getWriter();
  let sizeBytes = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      sizeBytes += chunk.value.byteLength;
      if (sizeBytes > MAX_UPLOAD_BYTES) {
        await reader.cancel("bundle_too_large").catch(() => undefined);
        await writer.abort("bundle_too_large").catch(() => undefined);
        await digest.digest.catch(() => undefined);
        return {
          code: "bundle_too_large",
          error: "uploaded bundle exceeds the server upload limit",
          kind: "error",
          status: 413,
        };
      }
      await writer.write(chunk.value);
    }
    await writer.close();
  } catch (error) {
    await writer.abort(error).catch(() => undefined);
    await digest.digest.catch(() => undefined);
    throw error;
  }
  if (digestHex(await digest.digest) !== rawBundleSha256) {
    return { code: "raw_bundle_sha_mismatch", error: "raw bundle bytes do not match raw_bundle_sha256", kind: "error", status: 400 };
  }
  return { kind: "ok", sizeBytes };
}

export async function signedUploadUrl(env: SubmissionApiEnv, rawBundleSha256: string): Promise<
  | { readonly kind: "ok"; readonly bucketName: string; readonly r2Key: string; readonly uploadHeaders: Readonly<Record<string, string>>; readonly uploadUrl: string }
  | { readonly kind: "disabled" }
> {
  const signing = r2SigningConfig(env);
  if (signing === null) {
    return { kind: "disabled" };
  }
  const r2Key = rawBundleKey(rawBundleSha256);
  // R2's PutObject compatibility supports this conditional create header, but
  // not x-amz-checksum-sha256. Finalization hashes the uploaded object bytes.
  const uploadHeaders = {
    "if-none-match": "*",
  };
  const uploadUrl = await signedR2Url(signing, r2Key, uploadHeaders);
  return { bucketName: signing.bucketName, kind: "ok", r2Key, uploadHeaders, uploadUrl };
}

export function rawBundleKey(rawBundleSha256: string): string {
  return `submissions/raw/${rawBundleSha256}.json`;
}

export function projectionKey(projectionObjectSha256: string): string {
  return `projections/sha256/${projectionObjectSha256}.json`;
}

function r2SigningConfig(env: SubmissionApiEnv): R2SigningConfig | null {
  if (env.R2_ACCESS_KEY_ID === undefined || env.R2_ACCOUNT_ID === undefined || env.R2_SECRET_ACCESS_KEY === undefined) {
    return null;
  }
  return {
    accessKeyId: env.R2_ACCESS_KEY_ID,
    accountId: env.R2_ACCOUNT_ID,
    bucketName: env.R2_BUCKET_NAME ?? SUBMISSIONS_BUCKET_NAME,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  };
}

async function signedR2Url(config: R2SigningConfig, key: string, headers: Readonly<Record<string, string>>): Promise<string> {
  const r2 = new AwsClient({ accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey });
  const url = new URL(`https://${config.accountId}.r2.cloudflarestorage.com/${config.bucketName}/${key}`);
  url.searchParams.set("X-Amz-Expires", "3600");
  const signed = await r2.sign(new Request(url, { headers, method: "PUT" }), { aws: { signQuery: true } });
  return signed.url;
}
