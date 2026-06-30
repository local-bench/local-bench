import { AwsClient } from "aws4fetch";
import { SUBMISSIONS_BUCKET_NAME, type SubmissionApiEnv } from "./submission-contracts";

type R2SigningConfig = {
  readonly accessKeyId: string;
  readonly accountId: string;
  readonly bucketName: string;
  readonly secretAccessKey: string;
};

export type RawBundleRead =
  | { readonly kind: "ok"; readonly text: string }
  | { readonly kind: "error"; readonly code: string; readonly error: string; readonly status: number };

export async function readRawBundle(env: SubmissionApiEnv, rawBundleSha256: string): Promise<RawBundleRead> {
  const object = await env.SUBMISSIONS.get(rawBundleKey(rawBundleSha256));
  if (object === null) {
    return { code: "raw_bundle_missing", error: "raw bundle is not present in R2", kind: "error", status: 404 };
  }
  const text = await object.text();
  if ((await sha256Hex(text)) !== rawBundleSha256) {
    return { code: "raw_bundle_sha_mismatch", error: "raw bundle bytes do not match raw_bundle_sha256", kind: "error", status: 400 };
  }
  return { kind: "ok", text };
}

export async function signedUploadUrl(env: SubmissionApiEnv, rawBundleSha256: string): Promise<
  | { readonly kind: "ok"; readonly bucketName: string; readonly r2Key: string; readonly uploadUrl: string }
  | { readonly kind: "disabled" }
> {
  const signing = r2SigningConfig(env);
  if (signing === null) {
    return { kind: "disabled" };
  }
  const r2Key = rawBundleKey(rawBundleSha256);
  const uploadUrl = await signedR2Url(signing, r2Key);
  return { bucketName: signing.bucketName, kind: "ok", r2Key, uploadUrl };
}

export function rawBundleKey(rawBundleSha256: string): string {
  return `submissions/raw/${rawBundleSha256}.json`;
}

export function projectionKey(submissionId: string, projectionSha256: string): string {
  return `projections/${submissionId}/${projectionSha256}.json`;
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

async function signedR2Url(config: R2SigningConfig, key: string): Promise<string> {
  const r2 = new AwsClient({ accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey });
  const url = new URL(`https://${config.accountId}.r2.cloudflarestorage.com/${config.bucketName}/${key}`);
  url.searchParams.set("X-Amz-Expires", "3600");
  const signed = await r2.sign(new Request(url, { method: "PUT" }), { aws: { signQuery: true } });
  return signed.url;
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
