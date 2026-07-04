import { jsonResponse, logTypedRejection } from "./submission-api-support";

export type SubmissionOrigin = "project_anchor" | "community";

export function reject(
  status: number,
  code: string,
  origin: SubmissionOrigin,
  route: string,
  body: Record<string, unknown>,
  bundleSha256?: string,
  submitterId?: string,
): Response {
  logTypedRejection({
    code,
    origin,
    route,
    status,
    ...(bundleSha256 === undefined ? {} : { bundleSha256 }),
    ...(submitterId === undefined ? {} : { submitterId }),
  });
  return jsonResponse(status, body);
}

export function clientIp(request: Request): string {
  return (request.headers.get("CF-Connecting-IP") ?? "unknown").trim() || "unknown";
}

export function ticketExpired(status: string, expiresAt: string | null): boolean {
  return status === "ticketed" && expiresAt !== null && Date.parse(expiresAt) < Date.now();
}

export function parseJson(text: string): unknown | null {
  try {
    const value: unknown = JSON.parse(text);
    return value;
  } catch (error) {
    if (isSyntaxError(error)) {
      return null;
    }
    throw error;
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isSyntaxError(error: unknown): boolean {
  if (error instanceof SyntaxError) {
    return true;
  }
  return error instanceof Error && error.name === "SyntaxError";
}
