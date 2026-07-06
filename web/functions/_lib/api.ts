import { PUBLIC_SUITES, suiteById, type SuiteRecord } from "./suite-catalog";

export type ApiEnv = {
  readonly DB: unknown;
  readonly LOCALBENCH_PUBLIC_BASE_URL?: string;
  readonly R2_BUCKET_NAME?: string;
};

type RouteParams = {
  readonly suiteId?: string;
};

export function handleHealth(env: ApiEnv): Response {
  return jsonResponse(200, {
    service: "localbench",
    status: "ok",
    storage: { d1: Boolean(env.DB), queue: false, r2: Boolean(env.R2_BUCKET_NAME) },
  });
}

export function handleSuites(env: ApiEnv): Response {
  const baseUrl = publicBaseUrl(env);
  return jsonResponse(200, {
    suites: PUBLIC_SUITES.map((suite) => ({
      id: suite.id,
      legacy: suite.legacy ?? false,
      manifest_url: `${baseUrl}/api/suites/${suite.id}/manifest`,
      suite_hash: suite.suiteHash,
      suite_manifest_sha256: suite.suiteManifestSha256,
      version: suite.version,
    })),
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

function requestBaseUrl(env: ApiEnv, requestUrl: URL): string {
  return env.LOCALBENCH_PUBLIC_BASE_URL ?? requestUrl.origin;
}

function publicBaseUrl(env: ApiEnv): string {
  return env.LOCALBENCH_PUBLIC_BASE_URL ?? "https://local-bench.ai";
}

function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, {
    headers: { "cache-control": "no-store" },
    status,
  });
}
