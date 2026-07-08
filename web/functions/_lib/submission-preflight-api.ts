import {
  PublishabilityPreflightRequestSchema,
  type PublishabilityPreflightRequest,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { suiteByReleasePair } from "./suite-catalog";

export async function handlePublishabilityPreflight(request: Request, env: SubmissionApiEnv): Promise<Response> {
  void env;
  let requestBody: unknown;
  try {
    requestBody = await request.json();
  } catch {
    return invalidPreflight();
  }
  const parsed = PublishabilityPreflightRequestSchema.safeParse(requestBody);
  if (!parsed.success) {
    return invalidPreflight();
  }
  const reasons = publishabilityReasons(parsed.data);
  return jsonResponse(200, {
    contract: {
      route: "POST /api/submissions/preflight",
      schema_version: parsed.data.schema_version,
      source: parsed.data.source,
    },
    publishable: reasons.length === 0,
    reasons,
    suite: {
      suite_manifest_sha256: parsed.data.suite_manifest_sha256,
      suite_release_id: parsed.data.suite_release_id,
    },
  });
}

function publishabilityReasons(request: PublishabilityPreflightRequest): readonly string[] {
  const reasons: string[] = [];
  if (suiteByReleasePair(request.suite_release_id, request.suite_manifest_sha256) === null) {
    reasons.push("unknown_suite_release");
  }
  if (request.identity_envelope.publishable !== true) {
    reasons.push("identity_envelope_not_publishable");
  }
  if (request.result_bundle !== undefined && request.result_bundle.manifest.integrity.publishable !== true) {
    reasons.push("result_bundle_not_publishable");
  }
  return reasons;
}

function invalidPreflight(): Response {
  return jsonResponse(400, {
    code: "invalid_preflight",
    error: "invalid publishability preflight",
  });
}
