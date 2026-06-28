import { AwsClient } from "aws4fetch";
import { z } from "zod";
import { CORE_TEXT_SUITE, suiteById, type SuiteRecord } from "./suite-catalog";

type SqlValue = string | number | null;

type D1PreparedStatement = {
  bind(...values: readonly SqlValue[]): D1PreparedStatement;
  first(): Promise<Record<string, unknown> | null> | Record<string, unknown> | null;
  run(): Promise<{ readonly success: boolean }> | { readonly success: boolean };
  all(): Promise<{ readonly results: readonly Record<string, unknown>[] }> | { readonly results: readonly Record<string, unknown>[] };
};

export type D1DatabaseBinding = {
  prepare(query: string): D1PreparedStatement;
};

export type QueueBinding = {
  send(message: unknown): Promise<void> | void;
};

export type ApiEnv = {
  readonly ADMIN_API_SECRET?: string;
  readonly DB: D1DatabaseBinding;
  readonly LOCALBENCH_PUBLIC_BASE_URL?: string;
  readonly R2_ACCESS_KEY_ID: string;
  readonly R2_ACCOUNT_ID: string;
  readonly R2_BUCKET_NAME: string;
  readonly R2_SECRET_ACCESS_KEY: string;
  readonly VERIFICATION_QUEUE?: QueueBinding;
};

type RouteParams = {
  readonly suiteId?: string;
  readonly submissionId?: string;
};

type SubmissionRow = {
  readonly bundle_sha256: string | null;
  readonly manifest_payload_sha256: string | null;
  readonly r2_key: string;
  readonly size_bytes: number | null;
  readonly status: string;
  readonly submission_id: string;
};

const SubmissionRowSchema = z.object({
  bundle_sha256: z.string().nullable(),
  manifest_payload_sha256: z.string().nullable(),
  r2_key: z.string(),
  size_bytes: z.number().nullable(),
  status: z.string(),
  submission_id: z.string(),
});

const TicketRequestSchema = z.object({
  public_key: z.string().regex(/^[0-9a-f]{64}$/),
  suite_id: z.string().default(CORE_TEXT_SUITE.id),
});

const CompleteRequestSchema = z.object({
  bundle_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  manifest_payload_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  size: z.number().int().positive().max(104_857_600),
});

const DecisionRequestSchema = z.object({
  decision: z.enum(["accepted", "rejected"]),
  reason: z.string().min(1).max(2000),
});

export function handleHealth(env: ApiEnv): Response {
  return jsonResponse(200, {
    service: "localbench",
    status: "ok",
    storage: { d1: Boolean(env.DB), queue: Boolean(env.VERIFICATION_QUEUE), r2: Boolean(env.R2_BUCKET_NAME) },
  });
}

export function handleSuites(env: ApiEnv): Response {
  const baseUrl = publicBaseUrl(env);
  return jsonResponse(200, {
    suites: [
      {
        id: CORE_TEXT_SUITE.id,
        manifest_url: `${baseUrl}/api/suites/${CORE_TEXT_SUITE.id}/manifest`,
        suite_hash: CORE_TEXT_SUITE.suiteHash,
        version: CORE_TEXT_SUITE.version,
      },
    ],
  });
}

export function handleSuiteManifest(env: ApiEnv, requestUrl: URL, params: RouteParams): Response {
  const suiteId = params.suiteId ?? "";
  const suite = suiteById(suiteId);
  if (suite === null) {
    return jsonResponse(404, { error: "unknown suite" });
  }
  return jsonResponse(200, suiteManifest(suite, requestBaseUrl(env, requestUrl)));
}

export async function handleCreateTicket(request: Request, env: ApiEnv): Promise<Response> {
  const parsed = TicketRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { error: "invalid ticket request" });
  }
  const suite = suiteById(parsed.data.suite_id);
  if (suite === null) {
    return jsonResponse(404, { error: "unknown suite" });
  }
  const submissionId = `sub_${crypto.randomUUID().replaceAll("-", "")}`;
  const serverNonce = crypto.randomUUID().replaceAll("-", "");
  const r2Key = `submissions/${submissionId}/bundle.lbsub.zip`;
  const uploadUrl = await signedPutUrl(env, r2Key);
  await env.DB.prepare(
    `insert into submissions (
      submission_id, public_key, suite_id, suite_hash, status, server_nonce, r2_key, issued_at, updated_at
    ) values (?, ?, ?, ?, 'issued', ?, ?, datetime('now'), datetime('now'))`,
  )
    .bind(submissionId, parsed.data.public_key, suite.id, suite.suiteHash, serverNonce, r2Key)
    .run();
  return jsonResponse(201, {
    max_bytes: 104_857_600,
    server_nonce: serverNonce,
    site: publicBaseUrl(env),
    status: "issued",
    submission_id: submissionId,
    suite_hash: suite.suiteHash,
    upload_key: r2Key,
    upload_method: "r2-presigned-put",
    upload_url: uploadUrl,
  });
}

export async function handleCompleteSubmission(request: Request, env: ApiEnv, params: RouteParams): Promise<Response> {
  const submissionId = requiredSubmissionId(params);
  const parsed = CompleteRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { error: "invalid upload completion" });
  }
  const row = await submissionRow(env, submissionId);
  if (row === null) {
    return jsonResponse(404, { error: "unknown submission" });
  }
  if (row.status !== "issued") {
    return jsonResponse(409, { error: "submission is not awaiting upload", status: row.status });
  }
  await env.DB.prepare(
    `update submissions
      set status = 'uploaded', bundle_sha256 = ?, manifest_payload_sha256 = ?, size_bytes = ?, updated_at = datetime('now')
      where submission_id = ?`,
  )
    .bind(parsed.data.bundle_sha256, parsed.data.manifest_payload_sha256, parsed.data.size, submissionId)
    .run();
  await env.DB.prepare(
    `insert into verification_jobs (submission_id, status, created_at, updated_at)
      values (?, 'queued', datetime('now'), datetime('now'))`,
  )
    .bind(submissionId)
    .run();
  await env.VERIFICATION_QUEUE?.send({ submission_id: submissionId });
  return jsonResponse(200, { publishable: false, status: "uploaded", submission_id: submissionId });
}

export async function handleSubmissionStatus(env: ApiEnv, params: RouteParams): Promise<Response> {
  const row = await submissionRow(env, requiredSubmissionId(params));
  if (row === null) {
    return jsonResponse(404, { error: "unknown submission" });
  }
  return jsonResponse(200, publicSubmission(row));
}

export async function handleAdminListSubmissions(request: Request, env: ApiEnv): Promise<Response> {
  const unauthorized = adminUnauthorized(request, env);
  if (unauthorized !== null) {
    return unauthorized;
  }
  const url = new URL(request.url);
  const status = url.searchParams.get("status") ?? "uploaded";
  const requestedLimit = Number(url.searchParams.get("limit") ?? "20");
  const limit = Number.isFinite(requestedLimit) ? Math.min(Math.max(Math.floor(requestedLimit), 1), 100) : 20;
  const rows = await env.DB.prepare(
    `select submission_id, status, r2_key, bundle_sha256, manifest_payload_sha256, size_bytes
      from submissions where status = ? order by updated_at asc limit ?`,
  )
    .bind(status, limit)
    .all();
  const submissions = await Promise.all(
    rows.results.map(async (row) => {
      const parsed = SubmissionRowSchema.parse(row);
      return { ...publicSubmission(parsed), download_url: await signedR2Url(env, parsed.r2_key, "GET") };
    }),
  );
  return jsonResponse(200, { submissions });
}

export async function handleAdminDecision(request: Request, env: ApiEnv, params: RouteParams): Promise<Response> {
  const unauthorized = adminUnauthorized(request, env);
  if (unauthorized !== null) {
    return unauthorized;
  }
  const submissionId = requiredSubmissionId(params);
  const parsed = DecisionRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { error: "invalid admin decision" });
  }
  const row = await submissionRow(env, submissionId);
  if (row === null) {
    return jsonResponse(404, { error: "unknown submission" });
  }
  await env.DB.prepare(
    `insert into admin_decisions (submission_id, decision, reason, decided_at)
      values (?, ?, ?, datetime('now'))`,
  )
    .bind(submissionId, parsed.data.decision, parsed.data.reason)
    .run();
  await env.DB.prepare(`update submissions set status = ?, updated_at = datetime('now') where submission_id = ?`)
    .bind(parsed.data.decision, submissionId)
    .run();
  return jsonResponse(200, { publishable: false, status: parsed.data.decision, submission_id: submissionId });
}

const VerificationResultRequestSchema = z.object({
  error: z.string().max(4000).optional(),
  result_r2_key: z.string().min(1).max(500).optional(),
  status: z.enum(["verifying", "needs_review", "rejected"]),
});

export async function handleAdminVerificationResult(request: Request, env: ApiEnv, params: RouteParams): Promise<Response> {
  const unauthorized = adminUnauthorized(request, env);
  if (unauthorized !== null) {
    return unauthorized;
  }
  const submissionId = requiredSubmissionId(params);
  const parsed = VerificationResultRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { error: "invalid verification result" });
  }
  const row = await submissionRow(env, submissionId);
  if (row === null) {
    return jsonResponse(404, { error: "unknown submission" });
  }
  await env.DB.prepare(
    `update verification_jobs
      set status = ?, result_r2_key = ?, error = ?, updated_at = datetime('now')
      where submission_id = ?`,
  )
    .bind(parsed.data.status, parsed.data.result_r2_key ?? null, parsed.data.error ?? null, submissionId)
    .run();
  await env.DB.prepare(`update submissions set status = ?, updated_at = datetime('now') where submission_id = ?`)
    .bind(parsed.data.status, submissionId)
    .run();
  return jsonResponse(200, { publishable: false, status: parsed.data.status, submission_id: submissionId });
}

function suiteManifest(suite: SuiteRecord, baseUrl: string): Record<string, unknown> {
  return {
    files: suite.files.map((file) => ({
      path: file.path,
      sha256: file.sha256,
      size: file.size,
      url: `${baseUrl}/suites/${suite.id}/${file.path}`,
    })),
    schema_version: "localbench.suite-manifest.v1",
    suite_hash: suite.suiteHash,
    suite_id: suite.id,
    version: suite.version,
  };
}

async function signedPutUrl(env: ApiEnv, key: string): Promise<string> {
  return signedR2Url(env, key, "PUT");
}

async function signedR2Url(env: ApiEnv, key: string, method: "GET" | "PUT"): Promise<string> {
  const r2 = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  });
  const url = new URL(`https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.R2_BUCKET_NAME}/${key}`);
  url.searchParams.set("X-Amz-Expires", "3600");
  const signed = await r2.sign(new Request(url, { method }), { aws: { signQuery: true } });
  return signed.url;
}

async function submissionRow(env: ApiEnv, submissionId: string): Promise<SubmissionRow | null> {
  const row = await env.DB.prepare(
    `select submission_id, status, r2_key, bundle_sha256, manifest_payload_sha256, size_bytes
      from submissions where submission_id = ?`,
  )
    .bind(submissionId)
    .first();
  return row === null ? null : SubmissionRowSchema.parse(row);
}

function publicSubmission(row: SubmissionRow): Record<string, unknown> {
  return {
    bundle_sha256: row.bundle_sha256,
    manifest_payload_sha256: row.manifest_payload_sha256,
    publishable: false,
    r2_key: row.r2_key,
    size: row.size_bytes,
    status: row.status,
    submission_id: row.submission_id,
  };
}

function requestBaseUrl(env: ApiEnv, requestUrl: URL): string {
  return env.LOCALBENCH_PUBLIC_BASE_URL ?? requestUrl.origin;
}

function publicBaseUrl(env: ApiEnv): string {
  return env.LOCALBENCH_PUBLIC_BASE_URL ?? "https://local-bench.ai";
}

function requiredSubmissionId(params: RouteParams): string {
  if (params.submissionId === undefined || params.submissionId.length === 0) {
    throw new Error("submission id route param missing");
  }
  return params.submissionId;
}

function adminUnauthorized(request: Request, env: ApiEnv): Response | null {
  if (env.ADMIN_API_SECRET === undefined || request.headers.get("x-localbench-admin-secret") !== env.ADMIN_API_SECRET) {
    return jsonResponse(401, { error: "unauthorized" });
  }
  return null;
}

function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, {
    headers: { "cache-control": "no-store" },
    status,
  });
}
