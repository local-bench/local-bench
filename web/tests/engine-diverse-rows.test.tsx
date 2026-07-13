import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { ServingPerformanceCard } from "../app/run/[runId]/page";
import { EngineProvenance } from "../components/engine-provenance";
import { HomeLeaderboard } from "../components/home-leaderboard";
import { ModelVariantBoard } from "../components/model-variant-board";
import { IndexDataSchema, ModelDataSchema, PerfSchema, RunDetailSchema, RuntimeSchema } from "../lib/schemas";

const WEB_ROOT = process.cwd();
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("engine-diverse build projection", () => {
  it("projects a vLLM receipt emitted by the real CLI writers and rejects blocked ranking", () => {
    const work = temporaryDirectory("localbench-vllm-web-");
    const { baseSource, baseRunPath } = firstSource();
    const runPath = path.join(work, "vllm-lane-fixture.json");
    const emitted = spawnSync(
      "uv",
      [
        "run",
        "--project",
        path.join(REPO_ROOT, "cli"),
        "python",
        path.join(WEB_ROOT, "tests", "fixtures", "emit_vllm_receipt.py"),
        "--base",
        baseRunPath,
        "--out",
        runPath,
      ],
      { cwd: WEB_ROOT, encoding: "utf8" },
    );
    expect(emitted.status, emitted.stderr || emitted.stdout).toBe(0);

    const receipt = readJson(runPath) as Record<string, any>;
    expect(receipt["serving_mode"]).toBe("orchestrated_vllm");
    expect(receipt["manifest"].scorecard.scorecard_version).toBe("4");
    expect(receipt["manifest"].integrity).toMatchObject({ publishable: true, blocking_reasons: [] });
    expect(receipt["perf"].timings_source).toBeNull();
    expect(receipt["perf"].prefill_tps).toBeNull();

    const source = { ...baseSource, file: runPath, quant_label: "NVFP4", reasoning_lane: "bounded-final-v2", vram_footprint_gb: 18 };
    const acceptedOut = path.join(work, "accepted-data");
    buildData(work, [source], acceptedOut);

    const index = IndexDataSchema.parse(readJson(path.join(acceptedOut, "index.json")));
    const model = ModelDataSchema.parse(readJson(path.join(acceptedOut, "models", "gemma-4-12b-it.json")));
    const rawDetail = readJson(path.join(acceptedOut, "runs", "gemma-4-12b-it__vllm-lane-fixture.json")) as Record<string, any>;
    const detail = RunDetailSchema.parse(rawDetail);
    const rankingDiagnostic = JSON.stringify({ axes: Object.keys(detail.axes), conformance: rawDetail["conformance"], data_warnings: detail.data_warnings, integrity: receipt["manifest"].integrity, serving_mode: receipt["serving_mode"], tier: detail.tier });
    expect(index.models.find((row) => row.slug === "gemma-4-12b-it")?.ranked, rankingDiagnostic).toBe(true);
    expect(model.runs.find((row) => row.run_id === detail.run_id)?.ranked, rankingDiagnostic).toBe(true);
    expect(detail.ranked, rankingDiagnostic).toBe(true);
    expect(detail.manifest_summary.model.format).toBe("safetensors");
    expect(detail.manifest_summary.quant).toBe("NVFP4");
    expect(detail.perf?.timings_source).toBeNull();
    expect(detail.serving_provenance).toMatchObject({
      runtime: "vllm",
      engine_version: "0.24.0",
      engine_executable_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      dependency_lock_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      runtime_identity_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      snapshot: {
        repo: "unsloth/Qwen3.6-35B-A3B-NVFP4-Fast",
        revision: "a".repeat(40),
        merkle_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      },
      determinism: {
        engine_log_semantic_verdict: true,
        two_start_canary_passed: true,
      },
      numerics: {
        mamba_ssm_cache_dtype: "float32",
        model_config_mamba_ssm_dtype: "float32",
      },
    });
    const malformedIndex = structuredClone(readJson(path.join(acceptedOut, "index.json"))) as Record<string, any>;
    delete malformedIndex["models"].find((row: any) => row.slug === "gemma-4-12b-it").serving_provenance;
    expect(() => IndexDataSchema.parse(malformedIndex)).toThrow();
    const malformedModel = structuredClone(readJson(path.join(acceptedOut, "models", "gemma-4-12b-it.json"))) as Record<string, any>;
    delete malformedModel["runs"].find((row: any) => row.run_id === detail.run_id).serving_provenance;
    expect(() => ModelDataSchema.parse(malformedModel)).toThrow();

    const variantHtml = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));
    const boardHtml = renderToStaticMarkup(createElement(HomeLeaderboard, { models: index.models }));
    const provenanceHtml = renderToStaticMarkup(createElement(EngineProvenance, { provenance: detail.serving_provenance }));
    const performanceHtml = renderToStaticMarkup(createElement(ServingPerformanceCard, { run: detail }));
    expect(variantHtml).toContain("NVFP4");
    expectRuntimeBadge(variantHtml, "vLLM", "0.24.0");
    expect(variantHtml).toContain("--model-id &lt;model-id&gt;");
    expect(variantHtml).toContain("--wsl-distro &lt;wsl-distro&gt;");
    expect(variantHtml).toContain("--vllm-venv &lt;absolute-wsl-vllm-venv&gt;");
    expect(variantHtml).toContain("--wsl-venv-python &lt;absolute-wsl-appworld-python&gt;");
    expect(variantHtml).toContain("--appworld-root &lt;absolute-wsl-appworld-root&gt;");
    expectRuntimeBadge(boardHtml, "vLLM", "0.24.0");
    expect(provenanceHtml).toContain("determinism canary: passed");
    expect(provenanceHtml).toContain("SSM cache: float32");
    expect(provenanceHtml).toContain(detail.serving_provenance?.snapshot?.merkle_sha256);
    expect(provenanceHtml).toContain("dependency lock");
    expect(performanceHtml).toContain("Server timings: not measured.");
    expect(performanceHtml).not.toContain("Source: vllm");
    expect(performanceHtml).not.toContain("Source: llama.cpp");

    const blockedReceipt = structuredClone(receipt);
    blockedReceipt["manifest"].integrity.publishable = false;
    blockedReceipt["manifest"].integrity.blocking_reasons = ["runtime.two_start_canary_missing"];
    const blockedPath = path.join(work, "blocked-vllm-lane-fixture.json");
    writeFileSync(blockedPath, `${JSON.stringify(blockedReceipt)}\n`);
    const blockedOut = path.join(work, "blocked-data");
    buildData(work, [{ ...source, file: blockedPath }], blockedOut);
    const blockedDetail = RunDetailSchema.parse(readJson(path.join(blockedOut, "runs", "gemma-4-12b-it__blocked-vllm-lane-fixture.json")));
    expect(blockedDetail.ranked).toBe(false);
  }, 60_000);

  it("fails closed on every required vLLM provenance invariant", () => {
    const valid = validVllmRow();
    expect(() => RunDetailSchema.parse(valid)).not.toThrow();
    for (const mutate of [
      (row: any) => { delete row.serving_provenance; },
      (row: any) => { row.serving_provenance.runtime = "llama.cpp"; },
      (row: any) => { row.serving_provenance.snapshot = null; },
      (row: any) => { row.serving_provenance.engine_version = null; },
      (row: any) => { row.serving_provenance.engine_executable_sha256 = null; },
      (row: any) => { row.serving_provenance.dependency_lock_sha256 = null; },
      (row: any) => { row.serving_provenance.runtime_identity_sha256 = null; },
      (row: any) => { row.serving_provenance.determinism.engine_log_evidence = []; },
      (row: any) => { row.serving_provenance.determinism.engine_log_semantic_verdict = false; },
      (row: any) => { row.serving_provenance.determinism.two_start_canary_passed = false; },
    ]) {
      const malformed = structuredClone(valid);
      mutate(malformed);
      expect(() => RunDetailSchema.parse(malformed)).toThrow();
    }
  });

  it("keeps a real llama.cpp receipt free of vLLM provenance rendering", () => {
    const work = temporaryDirectory("localbench-llama-web-");
    const { baseSource, baseRunPath } = firstSource();
    const out = path.join(work, "data");
    buildData(work, [baseSource], out, ["--benches", "knowledge"]);
    const receiptName = path.basename(baseRunPath, path.extname(baseRunPath));
    const index = IndexDataSchema.parse(readJson(path.join(out, "index.json")));
    const model = ModelDataSchema.parse(readJson(path.join(out, "models", "gemma-4-12b-it.json")));
    const detail = RunDetailSchema.parse(readJson(path.join(out, "runs", `gemma-4-12b-it__${receiptName}.json`)));
    const indexRow = index.models.find((row) => row.slug === "gemma-4-12b-it");
    const modelRow = model.runs.find((row) => row.run_id === detail.run_id);
    expect(indexRow).toBeDefined();
    expect(modelRow).toBeDefined();
    expect(detail.manifest_summary.runtime.name).toBe("llama.cpp");
    for (const row of [indexRow, modelRow, detail]) expectNoVllmProvenanceFields(row);

    const variantHtml = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));
    const boardHtml = renderToStaticMarkup(createElement(HomeLeaderboard, { models: index.models }));
    const provenanceHtml = renderToStaticMarkup(createElement(EngineProvenance, { provenance: detail.serving_provenance }));
    expectRuntimeBadge(variantHtml, "llama.cpp", detail.manifest_summary.runtime.version);
    expectRuntimeBadge(boardHtml, "llama.cpp", detail.manifest_summary.runtime.version);
    expect(provenanceHtml).toBe("");
    for (const html of [variantHtml, boardHtml, provenanceHtml]) {
      expect(html).not.toContain("determinism canary");
      expect(html).not.toContain("SSM cache");
      expect(html).not.toContain("snapshot:");
    }
  }, 30_000);

  it("rejects unknown runtime literals", () => {
    expect(() => RuntimeSchema.parse({ name: "unknown-engine", version: null, kv_cache_quant: null, ctx_len_configured: null, parallel_slots: null })).toThrow();
    expect(() => PerfSchema.parse({ timings_source: "vllm" })).toThrow();
  });
});

function firstSource(): { baseSource: Record<string, unknown>; baseRunPath: string } {
  const rows = readJson(path.join(WEB_ROOT, "data_sources.json")) as Array<Record<string, unknown>>;
  // Current bounded-final-v2 receipt: unlike the retired first row, this path is
  // rank-eligible before the engine-specific assertions in these tests.
  const baseSource = rows[1];
  if (baseSource === undefined || typeof baseSource["file"] !== "string") throw new Error("missing base run fixture");
  return { baseSource, baseRunPath: path.join(REPO_ROOT, baseSource["file"]) };
}

function buildData(work: string, sources: Array<Record<string, unknown>>, out: string, extraArgs: string[] = []): void {
  const sourcesPath = path.join(work, `${path.basename(out)}-sources.json`);
  writeFileSync(sourcesPath, `${JSON.stringify(sources)}\n`);
  const built = spawnSync(
    "uv",
    ["run", "--project", path.join(REPO_ROOT, "cli"), "python", "build_data.py", "--sources", sourcesPath, "--out", out, "--iters", "1", "--allow-lineage-gaps", ...extraArgs],
    { cwd: WEB_ROOT, encoding: "utf8" },
  );
  expect(built.status, built.stderr || built.stdout).toBe(0);
}

function validVllmRow(): Record<string, any> {
  return {
    axes: {}, composite: { hi: 1, lo: 0, point: 0.5 }, demo: false, est_cost_usd: null, index_version: "index-v3.0",
    item_set_hashes: {}, kind: "community", model_label: "Fixture", ranked: true, run_id: "fixture", score_status: "measured",
    suite_version: "suite-v1", tier: "standard", tokens_to_answer_median: null, tokens_to_answer_p95: null,
    totals: { completion_tokens: 0, completion_tokens_per_second: null, n_errors: 0, n_items: 0, prompt_tokens: 0, total_tokens: 0, wall_time_seconds: 0 },
    worst_axis: { bench: "knowledge", point: 0, point_raw: 0 },
    manifest_summary: {
      caps: {}, hardware: { cpu: null, gpu: null, os: null, ram_gb: null }, lane: "bounded-final-v2",
      model: { family: "Fixture", file_name: "snapshot", file_sha256: "b".repeat(64), file_size_bytes: 1, format: "safetensors", runtime_reported_model: "fixture" },
      quant: "NVFP4", runtime: { ctx_len_configured: 32768, kv_cache_quant: "bfloat16", name: "vllm", parallel_slots: 1, version: "0.24.0" },
      sampling: { by_bench: {}, temperature: 0, thinking_mode: "bounded" }, thinking_mode: "bounded",
    },
    serving_provenance: {
      runtime: "vllm", engine_version: "0.24.0", engine_executable_sha256: "f".repeat(64), dependency_lock_sha256: "c".repeat(64), runtime_identity_sha256: "d".repeat(64),
      snapshot: { repo: "org/model", revision: "a".repeat(40), merkle_sha256: "b".repeat(64), files: [{ path: "model.safetensors", sha256: "e".repeat(64), size_bytes: 1 }] },
      determinism: { engine_log_evidence: ["verified"], engine_log_semantic_verdict: true, two_start_canary_passed: true },
      numerics: { dtype: "bfloat16", kv_cache_quant: "bfloat16", mamba_ssm_cache_dtype: null, model_config_mamba_ssm_dtype: null, quantization: "compressed-tensors" },
    },
  };
}

function temporaryDirectory(prefix: string): string {
  const directory = mkdtempSync(path.join(tmpdir(), prefix));
  temporaryDirectories.push(directory);
  return directory;
}

function expectNoVllmProvenanceFields(row: unknown): void {
  expect(row).not.toHaveProperty("serving_provenance.determinism.two_start_canary_passed");
  expect(row).not.toHaveProperty("serving_provenance.numerics.mamba_ssm_cache_dtype");
  expect(row).not.toHaveProperty("serving_provenance.numerics.model_config_mamba_ssm_dtype");
  expect(row).not.toHaveProperty("serving_provenance.snapshot");
}

function expectRuntimeBadge(html: string, label: "llama.cpp" | "vLLM", version: string | null): void {
  const title = version === null ? `Serving engine: ${label}` : `Serving engine: ${label} ${version}`;
  const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  expect(html).toMatch(new RegExp(`title="${escapedTitle}"[^>]*>${escapedLabel}</span>`));
}

function readJson(file: string): unknown {
  return JSON.parse(readFileSync(file, "utf8"));
}
