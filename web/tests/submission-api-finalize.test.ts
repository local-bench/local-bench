import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { handleFinalizeSubmission } from "../functions/_lib/submission-api";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import type { D1DatabaseBinding, D1PreparedStatement, SqlValue, SubmissionApiEnv } from "../functions/_lib/submission-contracts";

const TICKET_ID = "ticket_unit_finalize";
const SUITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1";
const SUITE_MANIFEST_SHA = "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7";
const RESULT_BUNDLE_JSON = JSON.stringify(resultBundle());
const RAW_BUNDLE_SHA = sha256Hex(RESULT_BUNDLE_JSON);

describe("handleFinalizeSubmission", () => {
  it("returns the complete-request JSON error when the request body is malformed JSON", async () => {
    // Given: the complete route receives syntactically invalid JSON.
    const request = new Request(`https://local-bench.ai/api/submissions/${TICKET_ID}/complete`, {
      body: `{raw_bundle_sha256:"${RAW_BUNDLE_SHA}"}`,
      headers: { "content-type": "application/json" },
      method: "POST",
    });

    // When: the handler reads the request body.
    const response = await handleFinalizeSubmission(request, fakeEnv({}), { submissionId: TICKET_ID });

    // Then: the route returns the same contract error as other invalid complete requests.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      code: "invalid_complete_request",
      error: "invalid upload completion request",
    });
  });

  it("returns a JSON error when D1 throws SyntaxError after reading a valid result bundle", async () => {
    // Given: the ticketed row matches the uploaded bundle sha and R2 returns valid result_bundle_v1 JSON.
    const env = fakeEnv({
      runErrorMessage: "Expected property name or '}' in JSON at position 1",
    });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    try {
      // When: finalization reaches the D1 pending-verification update.
      const response = await handleFinalizeSubmission(
        jsonRequest(`/api/submissions/${TICKET_ID}/complete`, {
          raw_bundle_sha256: RAW_BUNDLE_SHA,
          size_bytes: RESULT_BUNDLE_JSON.length,
        }),
        env,
        { submissionId: TICKET_ID },
      );

      // Then: the Worker returns a structured JSON failure and emits a safe breadcrumb.
      expect(response.status).toBe(500);
      expect(await response.json()).toMatchObject({
        code: "submission_finalize_failed",
        error: "submission finalization failed",
      });
      expect(errorSpy).toHaveBeenCalledWith(
        "submission_finalize_failed",
        expect.objectContaining({
          leg: "mark_pending_verification",
          route: "POST /api/submissions/:submissionId/complete",
          submission_id: TICKET_ID,
        }),
      );
    } finally {
      errorSpy.mockRestore();
    }
  });
});

type FakeEnvOptions = {
  readonly runErrorMessage?: string;
};

function fakeEnv(options: FakeEnvOptions): SubmissionApiEnv {
  return {
    DB: new FakeD1Database(options),
    SUBMISSIONS: {
      get: async (key: string) => {
        if (key !== rawBundleKey(RAW_BUNDLE_SHA)) {
          return null;
        }
        return { text: async () => RESULT_BUNDLE_JSON };
      },
      put: async () => undefined,
    },
  };
}

class FakeD1Database implements D1DatabaseBinding {
  private readonly row = ticketRow();

  constructor(private readonly options: FakeEnvOptions) {}

  async exec(): Promise<unknown> {
    return undefined;
  }

  prepare(query: string): D1PreparedStatement {
    return new FakeD1Statement(query, this.row, this.options);
  }
}

class FakeD1Statement implements D1PreparedStatement {
  private values: readonly SqlValue[] = [];

  constructor(
    private readonly query: string,
    private readonly row: Record<string, unknown>,
    private readonly options: FakeEnvOptions,
  ) {}

  bind(...values: readonly SqlValue[]): D1PreparedStatement {
    this.values = values;
    return this;
  }

  async first(): Promise<Record<string, unknown> | null> {
    const value = this.values[0];
    if (this.query.includes("where raw_bundle_sha256 = ?")) {
      return value === RAW_BUNDLE_SHA ? this.row : null;
    }
    if (this.query.includes("where submission_id = ?")) {
      return value === TICKET_ID ? this.row : null;
    }
    return null;
  }

  async run(): Promise<{ readonly success: boolean }> {
    if (this.query.includes("update submissions set") && this.options.runErrorMessage !== undefined) {
      throw new SyntaxError(this.options.runErrorMessage);
    }
    return { success: true };
  }

  async all(): Promise<{ readonly results: readonly Record<string, unknown>[] }> {
    return { results: [] };
  }
}

function ticketRow(): Record<string, unknown> {
  return {
    bundle_schema_version: "localbench.result_bundle.v1",
    duplicate_of: null,
    expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    origin: "project_anchor",
    projection_sha256: null,
    publish_state: "hidden",
    raw_bundle_r2_key: rawBundleKey(RAW_BUNDLE_SHA),
    raw_bundle_sha256: RAW_BUNDLE_SHA,
    raw_bundle_size_bytes: null,
    run_payload_sha256: null,
    status: "ticketed",
    status_reason: null,
    submission_id: TICKET_ID,
    submitter_display_name: null,
    submitter_id: "project-anchor",
    suite_manifest_sha256: SUITE_MANIFEST_SHA,
    suite_release_id: SUITE_RELEASE_ID,
    ticket_id: TICKET_ID,
    uploaded_at: null,
  };
}

function jsonRequest(path: string, body: unknown): Request {
  return new Request(`https://local-bench.ai${path}`, {
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
}

function resultBundle(): Record<string, unknown> {
  return {
    axis_status: {},
    benches: {},
    conformance: {},
    headline_complete: false,
    items: [],
    manifest: {
      integrity: { publishable: true },
      provenance: { localbench_repo_commit: "440f540" },
      suite: {
        coverage_profile_id: "partial-text-code-4axis-v1",
        suite_manifest_sha256: SUITE_MANIFEST_SHA,
        suite_release_id: SUITE_RELEASE_ID,
      },
    },
    model: {},
    producer: "localbench-cli",
    run_finished_at: "2026-06-30T00:00:01Z",
    run_started_at: "2026-06-30T00:00:00Z",
    schema_version: "localbench.result_bundle.v1",
    scores: {
      headline_score: null,
      known_headline_contribution: 0.3737,
      measured_headline_weight: 0.5,
      missing_headline_weight: 0.5,
      partial_composite: 0.7473,
      partial_composite_scope: "measured_headline_axes",
      rank_scope: "partial-text-code-4axis-v1",
    },
    serving_mode: "external_openai_compatible_endpoint",
    tier: "standard",
    totals: {},
    warnings: [],
  };
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
