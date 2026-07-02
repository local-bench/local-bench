import type { ResultBundle, RouteParams, SubmissionApiEnv, SubmissionRow } from "./submission-contracts";
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

export function adminBlocked(request: Request, env: SubmissionApiEnv): Response | null {
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

export function suiteMismatches(row: SubmissionRow, bundle: ResultBundle): boolean {
  const suite = bundle.manifest.suite;
  if (row.suite_release_id !== null && row.suite_release_id !== suite.suite_release_id) {
    return true;
  }
  return row.suite_manifest_sha256 !== null && row.suite_manifest_sha256 !== suite.suite_manifest_sha256;
}

export type ErrorLogContext = {
  readonly error: unknown;
  readonly leg: string;
  readonly route: string;
  readonly submissionId: string;
};

export function logSubmissionError(message: string, context: ErrorLogContext): void {
  console.error(message, {
    error: errorDetails(context.error),
    leg: context.leg,
    route: context.route,
    submission_id: context.submissionId,
  });
}

export function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, {
    headers: { "cache-control": "no-store" },
    status,
  });
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
