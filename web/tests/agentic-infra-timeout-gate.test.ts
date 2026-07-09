import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

type JsonObject = Record<string, unknown>;

const REPO_ROOT = join(__dirname, "..", "..");
const WEB_ROOT = join(REPO_ROOT, "web");
const SOURCE_INDEX = 1;
const WARNING_REASON = "agentic-infra-timeout-rate";

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

function buildWithInfraTimeoutRates(aggregateRate: number, runRates: readonly number[]) {
  const workspace = mkdtempSync(join(tmpdir(), "local-bench-agentic-infra-"));
  const outDir = join(workspace, "out");
  try {
    const sources = requireJsonObjectArray(
      JSON.parse(readFileSync(join(WEB_ROOT, "data_sources.json"), "utf8")),
      "data_sources.json",
    );
    const source = { ...sources[SOURCE_INDEX] };
    const sourceFile = source["file"];
    if (typeof sourceFile !== "string") {
      throw new Error("bounded-final fixture source is missing a file path");
    }

    const run = readJson(join(REPO_ROOT, sourceFile));
    const agenticRun = requireJsonObject(run["agentic_run"], "bounded-final fixture agentic_run");
    const diagnostics = requireJsonObject(agenticRun["diagnostics"], "bounded-final fixture agentic_run.diagnostics");
    const runs = requireJsonObjectArray(agenticRun["runs"], "bounded-final fixture agentic_run.runs");

    diagnostics["infra_timeout_rate"] = aggregateRate;
    runs.forEach((runEntry, index) => {
      runEntry["infra_timeout_rate"] = runRates[index] ?? 0.0;
    });

    const runPath = join(workspace, "bounded-final-run.json");
    const sourcesPath = join(workspace, "sources.json");
    writeFileSync(runPath, JSON.stringify(run), "utf8");
    writeFileSync(sourcesPath, JSON.stringify([{ ...source, file: runPath }]), "utf8");

    const result = spawnSync("python", ["build_data.py", "--sources", sourcesPath, "--out", outDir, "--iters", "1", "--allow-lineage-gaps"], {
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

describe("agentic infrastructure timeout ranking gate", () => {
  it("keeps zero-rate agentic rows ranked", () => {
    // Given a bounded-final row whose aggregate and scored runs have no infrastructure timeouts.
    // When the real data builder projects the row.
    const { detail, row } = buildWithInfraTimeoutRates(0.0, [0.0, 0.0]);

    // Then it remains eligible for the ranked leaderboard.
    expect(row["ranked"]).toBe(true);
    expect(detail["ranked"]).toBe(true);
    expect(detail["data_warnings"]).not.toContain(WARNING_REASON);
  });

  it("keeps the strict 5 percent boundary ranked", () => {
    // Given a bounded-final row exactly at the infrastructure timeout threshold.
    // When the real data builder projects the row.
    const { detail, row } = buildWithInfraTimeoutRates(0.05, [0.05, 0.0]);

    // Then it remains ranked because only rates strictly above the threshold are excluded.
    expect(row["ranked"]).toBe(true);
    expect(detail["ranked"]).toBe(true);
    expect(detail["data_warnings"]).not.toContain(WARNING_REASON);
  });

  it("excludes elevated aggregate infrastructure timeouts from ranked rows", () => {
    // Given a bounded-final row with an elevated aggregate agentic infrastructure timeout rate.
    // When the real data builder projects the row.
    const { detail, row } = buildWithInfraTimeoutRates(0.1, [0.0, 0.0]);

    // Then the row keeps measured diagnostics but is quarantined from ranked output.
    expect(row).toMatchObject({ ranked: false, score_status: "measured" });
    expect(detail).toMatchObject({ ranked: false });
    expect(detail["data_warnings"]).toContain(WARNING_REASON);
  });

  it("excludes elevated individual scored-run infrastructure timeouts from ranked rows", () => {
    // Given a bounded-final row whose aggregate rate is acceptable but one scored run is elevated.
    // When the real data builder projects the row.
    const { detail, row } = buildWithInfraTimeoutRates(0.02, [0.08, 0.0]);

    // Then the individual scored-run timeout is enough to quarantine the row from ranking.
    expect(row).toMatchObject({ ranked: false, score_status: "measured" });
    expect(detail).toMatchObject({ ranked: false });
    expect(detail["data_warnings"]).toContain(WARNING_REASON);
  });
});
