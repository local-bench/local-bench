import { canonicalPayloadJson } from "./submission-canonical";
import type { ResultBundle, SubmissionRow } from "./submission-contracts";
import { verifyEd25519 } from "./submission-pop";
import { suiteByReleasePair } from "./suite-catalog";

type SemanticResult =
  | { readonly kind: "ok"; readonly modelFileSha256: string }
  | { readonly kind: "error"; readonly code: string; readonly error: string };

type SuiteShape = {
  readonly expectedStaticItems: number;
  readonly requiredAxes: readonly string[];
  readonly requiredBenches: Readonly<Record<string, number>>;
};

const SUITE_SHAPES: Readonly<Record<string, SuiteShape>> = {
  "core-text-v1": shape({ ifbench: 294, mmlu_pro: 400, tc_json_v1: 330 }, ["instruction_following", "knowledge", "tool_calling"]),
  "suite-v1-partial-text-code-4axis-v1": shape({ ifbench: 294, lcb: 129, mmlu_pro: 400, tc_json_v1: 330 }, ["coding", "instruction_following", "knowledge", "tool_calling"]),
  "suite-v1-text-code-agentic-5axis-v1": shape({ appworld_c: 96, ifbench: 294, lcb: 129, mmlu_pro: 400, tc_json_v1: 330 }, ["agentic", "coding", "instruction_following", "knowledge", "tool_calling"], 1153),
  "suite-v1-full-exec-6axis-v1": shape({ amo: 39, appworld_c: 96, bigcodebench_hard: 148, ifbench: 294, mmlu_pro: 400, olymmath_hard: 100, tc_json_v1: 330 }, ["agentic", "coding", "instruction_following", "knowledge", "math", "tool_calling"], 1311),
  "suite-v1-static-exec-5axis-v1": shape({ amo: 39, bigcodebench_hard: 148, ifbench: 294, mmlu_pro: 400, olymmath_hard: 100, tc_json_v1: 330 }, ["coding", "instruction_following", "knowledge", "math", "tool_calling"]),
  "suite-v1-static-core-diag-v1": shape({ amo: 39, ifbench: 294, mmlu_pro: 400, olymmath_hard: 100, tc_json_v1: 330 }, ["instruction_following", "knowledge", "math", "tool_calling"]),
};

export async function validatePendingAdmission(
  row: SubmissionRow,
  rawBundle: unknown,
  bundle: ResultBundle,
): Promise<SemanticResult> {
  const releaseId = bundle.manifest.suite.suite_release_id;
  const manifestSha = bundle.manifest.suite.suite_manifest_sha256;
  if (suiteByReleasePair(releaseId, manifestSha) === null) {
    return failure("semantic_suite_unknown", "bundle does not target a current public suite release");
  }
  const shape = SUITE_SHAPES[releaseId];
  if (shape === undefined || bundle.tier !== "standard") {
    return failure("semantic_coverage_invalid", "pending admission requires a Standard public-suite run");
  }
  const integrity = bundle.manifest.integrity;
  if (integrity.publishable !== true || nonEmptyArray(integrity["blocking_reasons"]) || nonEmptyArray(integrity["missing_required_fields"])) {
    return failure("semantic_integrity_invalid", "bundle manifest is not publishable");
  }
  if (!coverageMatches(bundle, shape)) {
    return failure("semantic_coverage_invalid", "bundle does not contain the complete declared suite coverage");
  }
  const modelFileSha256 = modelSha256(bundle);
  if (modelFileSha256 === null) {
    return failure("semantic_model_identity_invalid", "bundle is missing an exact GGUF SHA-256 identity");
  }
  const expectedPublicKey = publicKeyFromSubmitterId(row.submitter_id);
  if (expectedPublicKey !== null && !await validBundleSignature(rawBundle, expectedPublicKey)) {
    return failure("bundle_signature_invalid", "bundle signature is missing, mismatched, or invalid");
  }
  return { kind: "ok", modelFileSha256 };
}

function coverageMatches(bundle: ResultBundle, suite: SuiteShape): boolean {
  const axisStatuses = record(bundle.axis_status["axes"]);
  if (axisStatuses === null || suite.requiredAxes.some((axis) => record(axisStatuses[axis])?.["status"] !== "measured")) return false;
  const expectedTotal = Object.values(suite.requiredBenches).reduce((sum, count) => sum + count, 0);
  const itemsByBench = new Map<string, Set<string>>();
  for (const rawItem of bundle.items) {
    const item = record(rawItem);
    if (item === null || typeof item["bench"] !== "string" || (typeof item["id"] !== "string" && typeof item["id"] !== "number")) return false;
    const ids = itemsByBench.get(item["bench"]) ?? new Set<string>();
    ids.add(String(item["id"]));
    itemsByBench.set(item["bench"], ids);
  }
  if (bundle.items.length !== expectedTotal) return false;
  for (const [bench, count] of Object.entries(suite.requiredBenches)) {
    const aggregate = record(bundle.benches[bench]);
    if (itemsByBench.get(bench)?.size !== count || aggregate?.["n"] !== count) return false;
  }
  const totals = record(bundle.totals);
  const coverage = record((bundle as Record<string, unknown>)["suite_coverage"]);
  return (
    totals?.["n_items"] === expectedTotal &&
    coverage?.["status"] === "complete" &&
    coverage?.["expected_items"] === suite.expectedStaticItems &&
    coverage?.["observed_items"] === suite.expectedStaticItems &&
    coverage?.["missing_items"] instanceof Array &&
    coverage["missing_items"].length === 0
  );
}

async function validBundleSignature(rawBundle: unknown, expectedPublicKey: string): Promise<boolean> {
  const top = record(rawBundle);
  const signature = top === null ? null : record(top["signature"]);
  if (
    signature?.["algorithm"] !== "Ed25519" ||
    signature["public_key"] !== expectedPublicKey ||
    typeof signature["signature"] !== "string" ||
    !/^[0-9a-f]{128}$/.test(signature["signature"])
  ) return false;
  return verifyEd25519(expectedPublicKey, signature["signature"], canonicalPayloadJson(rawBundle));
}

function modelSha256(bundle: ResultBundle): string | null {
  const model = record(bundle.model);
  const manifestModel = record((bundle.manifest as Record<string, unknown>)["model"]);
  const first = typeof model?.["file_sha256"] === "string" ? model["file_sha256"] : null;
  const second = typeof manifestModel?.["file_sha256"] === "string" ? manifestModel["file_sha256"] : null;
  const value = first ?? second;
  if (value === null || !/^[0-9a-f]{64}$/.test(value)) return null;
  return first !== null && second !== null && first !== second ? null : value;
}

function publicKeyFromSubmitterId(value: string | null): string | null {
  return value?.startsWith("public_key:") === true ? value.slice("public_key:".length) : null;
}

function shape(requiredBenches: Readonly<Record<string, number>>, requiredAxes: readonly string[], expectedStaticItems?: number): SuiteShape {
  return {
    expectedStaticItems: expectedStaticItems ?? Object.values(requiredBenches).reduce((sum, count) => sum + count, 0),
    requiredAxes,
    requiredBenches,
  };
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function nonEmptyArray(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0;
}

function failure(code: string, error: string): SemanticResult {
  return { code, error, kind: "error" };
}
