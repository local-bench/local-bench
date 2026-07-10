import type { RouteParams, SubmissionApiEnv, SubmissionRow } from "./submission-contracts";
import { rowBySubmissionId } from "./submission-store";

export type RouteRowResult =
  | { readonly kind: "ok"; readonly value: SubmissionRow }
  | { readonly kind: "error"; readonly response: Response };

export async function routeRow(env: SubmissionApiEnv, params: RouteParams): Promise<RouteRowResult> {
  const submissionId = params.submissionId;
  if (submissionId === undefined || submissionId.length === 0) {
    return { kind: "error", response: jsonResponse(400, { code: "missing_submission_id", error: "submission id route param missing" }) };
  }
  const row = await rowBySubmissionId(env, submissionId);
  if (row === null) {
    return { kind: "error", response: jsonResponse(404, { code: "unknown_submission", error: "unknown submission" }) };
  }
  return { kind: "ok", value: row };
}

export function adminBlocked(request: Request, env: { readonly ADMIN_API_SECRET?: string }): Response | null {
  const expected = (env.ADMIN_API_SECRET ?? "").trim();
  if (expected.length === 0) {
    return jsonResponse(503, { code: "admin_api_disabled", error: "submission ticket issuance is disabled" });
  }
  const provided = (request.headers.get("x-localbench-admin-secret") ?? "").trim();
  if (provided.length === 0 || provided !== expected) {
    return jsonResponse(401, { code: "unauthorized", error: "unauthorized" });
  }
  return null;
}

export function hasValidAdminSecret(request: Request, env: { readonly ADMIN_API_SECRET?: string }): boolean {
  const expected = (env.ADMIN_API_SECRET ?? "").trim();
  const provided = (request.headers.get("x-localbench-admin-secret") ?? "").trim();
  return expected.length > 0 && provided === expected;
}

export type ErrorLogContext = {
  readonly error: unknown;
  readonly leg: string;
  readonly route: string;
  readonly submission_id: string;
};

export function logSubmissionError(message: string, context: ErrorLogContext): void {
  console.error(message, {
    error: errorDetails(context.error),
    leg: context.leg,
    route: context.route,
    submission_id: context.submission_id,
  });
}

export type TypedRejectionContext = {
  readonly bundleSha256?: string;
  readonly code: string;
  readonly origin: "project_anchor" | "community";
  readonly route: string;
  readonly status: number;
  readonly submitterId?: string;
};

export function logTypedRejection(context: TypedRejectionContext): void {
  console.warn("submission_typed_rejection", {
    bundle_sha256: truncateForLog(context.bundleSha256),
    code: context.code,
    origin: context.origin,
    route: context.route,
    status: context.status,
    submitter_id: truncateForLog(context.submitterId),
  });
}

export function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, {
    headers: { "cache-control": "no-store" },
    status,
  });
}

function truncateForLog(value: string | undefined): string | null {
  if (value === undefined) {
    return null;
  }
  return value.length <= 16 ? value : value.slice(0, 16);
}

function errorDetails(error: unknown): Record<string, string | null> {
  if (error instanceof Error) {
    return { message: error.message, name: error.name, stack: error.stack ?? null };
  }
  if (typeof error === "object" && error !== null) {
    return {
      message: "message" in error && typeof error.message === "string" ? error.message : String(error),
      name: "name" in error && typeof error.name === "string" ? error.name : "UnknownError",
      stack: "stack" in error && typeof error.stack === "string" ? error.stack : null,
    };
  }
  return { message: String(error), name: "UnknownError", stack: null };
}
