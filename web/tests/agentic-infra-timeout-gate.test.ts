import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

type JsonObject = Record<string, unknown>;

const REPO_ROOT = join(__dirname, "..", "..");
const WEB_ROOT = join(REPO_ROOT, "web");
// Stable fixture selection by file path (not array index): the Gemma bounded-final run.
const FIXTURE_FILE_FRAGMENT = "gemma-4-12b-it-qat-ud-q4kxl-bounded-final-v2";
const WARNING_REASON = "agentic-infra-timeout-rate";
// Sentinel: remove infra_timeout_rate from the summary instead of assigning a value.
const OMIT: unknown = Symbol("omit-infra-timeout-rate");

function readJson(path: string): JsonObject {
  const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));
  return requireJsonObject(parsed, `${path} JSON`);
}

function isJsonObject(value: unknown): value is JsonObject {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function requireJsonObject(value: unknown, context: string): JsonObject {
  if (!isJsonObject(value)) {
    throw new Error(`${context} is not an object`);
  }
  return value;
}

function requireJsonObjectArray(value: unknown, context: string): JsonObject[] {
  if (!Array.isArray(value) || !value.every(isJsonObject)) {
    throw new Error(`${context} is not an object array`);
  }
  return value;
}

function setRate(summary: JsonObject, field: "infra_timeout_rate" | "infra_failure_rate", rate: unknown): void {
  if (rate === OMIT) {
    delete summary[field];
    return;
  }
  summary[field] = rate;
}

function buildWithInfraTimeoutRates(
  aggregateRate: unknown,
  runRates: readonly unknown[],
  aggregateFailureRate: unknown = OMIT,
  runFailureRates: readonly unknown[] = [],
  markNewFormat = false,
  cliVersion: unknown = undefined,
  aggregateSandboxRate: unknown = undefined,
  runSandboxRates: readonly unknown[] = [],
  stripAllInfraRates = false,
) {
  const workspace = mkdtempSync(join(tmpdir(), "local-bench-agentic-infra-"));
  const outDir = join(workspace, "out");
  try {
    const sources = requireJsonObjectArray(
      JSON.parse(readFileSync(join(WEB_ROOT, "data_sources.json"), "utf8")),
      "data_sources.json",
    );
    const fixture = sources.find(
      (entry) => typeof entry["file"] === "string" && entry["file"].includes(FIXTURE_FILE_FRAGMENT),
    );
    if (!fixture) {
      throw new Error(`no data source file matches ${FIXTURE_FILE_FRAGMENT}`);
    }
    const source = { ...fixture };
    const sourceFile = source["file"] as string;

    const run = readJson(join(REPO_ROOT, sourceFile));
    const agenticRun = requireJsonObject(run["agentic_run"], "bounded-final fixture agentic_run");
    const diagnostics = requireJsonObject(agenticRun["diagnostics"], "bounded-final fixture agentic_run.diagnostics");
    const runs = requireJsonObjectArray(agenticRun["runs"], "bounded-final fixture agentic_run.runs");
    const manifest = requireJsonObject(run["manifest"], "bounded-final fixture manifest");
    const provenance = requireJsonObject(manifest["provenance"], "bounded-final fixture manifest.provenance");

    if (cliVersion === OMIT) delete provenance["cli_version"];
    else if (cliVersion !== undefined) provenance["cli_version"] = cliVersion;

    setRate(diagnostics, "infra_timeout_rate", aggregateRate);
    setRate(diagnostics, "infra_failure_rate", aggregateFailureRate);
    if (aggregateSandboxRate !== undefined) diagnostics["infra_sandbox_rate"] = aggregateSandboxRate;
    if (markNewFormat) diagnostics["transport_failure_count"] = 0;
    runs.forEach((runEntry, index) => {
      setRate(runEntry, "infra_timeout_rate", index < runRates.length ? runRates[index] : 0.0);
      setRate(runEntry, "infra_failure_rate", index < runFailureRates.length ? runFailureRates[index] : aggregateFailureRate);
      if (aggregateSandboxRate !== undefined) {
        runEntry["infra_sandbox_rate"] = index < runSandboxRates.length ? runSandboxRates[index] : aggregateSandboxRate;
      }
      if (markNewFormat) runEntry["transport_failure_count"] = 0;
    });
    if (stripAllInfraRates) {
      [diagnostics, ...runs].forEach((summary) => {
        Object.keys(summary).filter((field) => field.startsWith("infra_") && field.endsWith("_rate")).forEach((field) => delete summary[field]);
      });
    }

    const runPath = join(workspace, "bounded-final-run.json");
    const sourcesPath = join(workspace, "sources.json");
    writeFileSync(runPath, JSON.stringify(run), "utf8");
    writeFileSync(sourcesPath, JSON.stringify([{ ...source, file: runPath }]), "utf8");

    const result = spawnSync("uv", ["run", "--project", join(REPO_ROOT, "cli"), "python", "build_data.py", "--sources", sourcesPath, "--out", outDir, "--iters", "1", "--allow-lineage-gaps"], {
      cwd: WEB_ROOT,
      encoding: "utf8",
    });
    expect(result.status, `${result.stdout}\n${result.stderr}`).toBe(0);

    const index = readJson(join(outDir, "index.json"));
    const models = requireJsonObjectArray(index["models"], "generated index.json models");
    const row = models.find((model) => model["slug"] === "gemma-4-12b-it");
    if (!row) {
      throw new Error("generated index did not contain the Gemma bounded-final row");
    }
    const runId = row["best_run_id"];
    if (typeof runId !== "string") {
      throw new Error("generated Gemma bounded-final row did not carry a run id");
    }
    const detail = readJson(join(outDir, "runs", `${runId}.json`));
    return { detail, row };
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
}

function expectRanked({ detail, row }: { detail: JsonObject; row: JsonObject }): void {
  expect(row["ranked"]).toBe(true);
  expect(detail["ranked"]).toBe(true);
  expect(detail["data_warnings"]).not.toContain(WARNING_REASON);
}

function expectDeranked({ detail, row }: { detail: JsonObject; row: JsonObject }): void {
  expect(row).toMatchObject({ ranked: false, score_status: "measured" });
  expect(detail).toMatchObject({ ranked: false });
  expect(detail["data_warnings"]).toContain(WARNING_REASON);
}

describe("agentic infrastructure timeout ranking gate", () => {
  it("gates canonical aggregate and scored-run infrastructure failure rates", () => {
    expectRanked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], 0.05, [0.05, 0.0]));
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], 0.06, [0.0, 0.0]));
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], 0.0, [0.06, 0.0]));
  });

  it("fails closed on malformed canonical infrastructure failure rates", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], "0.01", [0.0, 0.0]));
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], 0.0, [null, 0.0]));
  });

  it("retains timeout-only gating for older records without the canonical field", () => {
    expectRanked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0]));
  });

  it("gates every legacy infrastructure rate including sandbox failures", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], OMIT, [], false, "0.1.0", 0.06, [0.0, 0.0]));
  });

  it("rejects legacy summaries with no infrastructure rate field", () => {
    expectDeranked(buildWithInfraTimeoutRates(OMIT, [OMIT, OMIT], OMIT, [], false, "0.1.0", undefined, [], true));
  });

  it("fails closed when a new-format record omits the canonical field", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], OMIT, [], true));
  });

  it("does not let a 0.3.1 record stripped of new fields masquerade as legacy", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], OMIT, [], false, "0.3.1"));
  });

  it("fails closed when the legacy receipt version is missing or unparseable", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], OMIT, [], false, OMIT));
    expectDeranked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0], OMIT, [], false, "not-a-version"));
  });

  it("keeps zero-rate agentic rows ranked", () => {
    // Given a bounded-final row whose aggregate and scored runs have no infrastructure timeouts.
    expectRanked(buildWithInfraTimeoutRates(0.0, [0.0, 0.0]));
  });

  it("keeps the strict 5 percent boundary ranked", () => {
    // Only rates strictly above the threshold are excluded.
    expectRanked(buildWithInfraTimeoutRates(0.05, [0.05, 0.0]));
  });

  it("excludes elevated aggregate infrastructure timeouts from ranked rows", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.1, [0.0, 0.0]));
  });

  it("excludes elevated individual scored-run infrastructure timeouts from ranked rows", () => {
    // Aggregate acceptable but one scored run elevated: still quarantined from ranking.
    expectDeranked(buildWithInfraTimeoutRates(0.02, [0.08, 0.0]));
  });

  it("fails closed when the aggregate rate is omitted", () => {
    // A rank-eligible row must PROVE a healthy rate; omitting the field cannot rank.
    expectDeranked(buildWithInfraTimeoutRates(OMIT, [0.0, 0.0]));
  });

  it("fails closed when any scored run omits its rate", () => {
    expectDeranked(buildWithInfraTimeoutRates(0.0, [OMIT, 0.0]));
  });

  it("fails closed on a string rate", () => {
    expectDeranked(buildWithInfraTimeoutRates("0.99", [0.0, 0.0]));
  });

  it("fails closed on a null rate", () => {
    expectDeranked(buildWithInfraTimeoutRates(null, [0.0, 0.0]));
  });

  it("fails closed on a boolean rate", () => {
    // JSON true would satisfy a naive numeric check in Python (bool subclasses int).
    expectDeranked(buildWithInfraTimeoutRates(true, [0.0, 0.0]));
  });

  it("fails closed on an out-of-range rate", () => {
    // Rates are proportions; anything outside [0, 1] is malformed, not merely high.
    expectDeranked(buildWithInfraTimeoutRates(1.5, [0.0, 0.0]));
  });
});
