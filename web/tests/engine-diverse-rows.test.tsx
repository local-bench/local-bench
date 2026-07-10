import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EngineProvenance } from "../components/engine-provenance";
import { HomeLeaderboard } from "../components/home-leaderboard";
import { ModelVariantBoard } from "../components/model-variant-board";
import { IndexDataSchema, ModelDataSchema, RunDetailSchema, RuntimeSchema } from "../lib/schemas";

const WEB_ROOT = process.cwd();
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("engine-diverse build projection", () => {
  it("carries a synthetic vLLM lane through build_data, schemas, and page surfaces", () => {
    const work = mkdtempSync(path.join(tmpdir(), "localbench-vllm-web-"));
    temporaryDirectories.push(work);
    const sourceRows = JSON.parse(readFileSync(path.join(WEB_ROOT, "data_sources.json"), "utf8")) as Array<Record<string, unknown>>;
    const baseSource = sourceRows[0];
    if (baseSource === undefined || typeof baseSource["file"] !== "string") throw new Error("missing base run fixture");
    const run = JSON.parse(readFileSync(path.join(REPO_ROOT, baseSource["file"]), "utf8")) as Record<string, any>;
    const revision = "a".repeat(40);
    const merkle = "b".repeat(64);
    const fileHash = "c".repeat(64);

    run["manifest"].runtime = {
      name: "vllm",
      version: "0.24.0",
      kv_cache_quant: "bfloat16",
      ctx_len_configured: 8192,
      parallel_slots: 1,
    };
    run["manifest"].model = {
      ...run["manifest"].model,
      file_name: "snapshot",
      file_sha256: merkle,
      file_size_bytes: 18_000_000_000,
      format: "safetensors",
      quant_label: "NVFP4",
    };
    run["perf"] = {
      timings_source: "vllm",
      timings_coverage: 1,
      prefill_tps: 900,
      decode_tps: 80,
      prompt_ms_median: 10,
      prompt_ms_p95: 20,
      predicted_ms_median: 100,
      predicted_ms_p95: 200,
      ttft_proxy_ms_median: 12,
      per_bench: {},
    };
    run["serving"] = {
      runtime: "vllm",
      artifact: {
        server_reported_package_version: "0.24.0",
        version_stdout: "0.24.0",
        venv_dependency_lock_sha256: "d".repeat(64),
        runtime_identity_sha256: "e".repeat(64),
      },
      resolved_runtime: {
        dtype: "bfloat16",
        kv_cache_quant: "bfloat16",
        mamba_ssm_cache_dtype: "float32",
        model_config_mamba_ssm_dtype: "float32",
        quantization: "compressed-tensors",
      },
      model_snapshot: {
        requested_repo: "unsloth/Qwen3.6-35B-A3B-NVFP4-Fast",
        requested_revision: revision,
        snapshot_merkle_sha256: merkle,
        files: [{ path: "model-00001-of-00002.safetensors", sha256: fileHash, size_bytes: 9_000_000_000 }],
      },
      determinism: {
        engine_log_evidence: ["VLLM_BATCH_INVARIANT deterministic execution"],
        engine_log_semantic_verdict: true,
        two_start_canary_passed: true,
      },
    };

    const runPath = path.join(work, "vllm-lane-fixture.json");
    const sourcesPath = path.join(work, "sources.json");
    const outPath = path.join(work, "data");
    writeFileSync(runPath, `${JSON.stringify(run)}\n`);
    writeFileSync(
      sourcesPath,
      `${JSON.stringify([{ ...baseSource, file: runPath, quant_label: "NVFP4", reasoning_lane: "bounded-final-v2", vram_footprint_gb: 18 }])}\n`,
    );

    const built = spawnSync(
      "uv",
      ["run", "--project", path.join(REPO_ROOT, "cli"), "python", "build_data.py", "--sources", sourcesPath, "--out", outPath, "--iters", "1", "--benches", "knowledge", "--allow-lineage-gaps"],
      { cwd: WEB_ROOT, encoding: "utf8" },
    );
    expect(built.status, built.stderr || built.stdout).toBe(0);

    const index = IndexDataSchema.parse(readJson(path.join(outPath, "index.json")));
    const model = ModelDataSchema.parse(readJson(path.join(outPath, "models", "gemma-4-12b-it.json")));
    const detail = RunDetailSchema.parse(readJson(path.join(outPath, "runs", "gemma-4-12b-it__vllm-lane-fixture.json")));
    expect(detail.manifest_summary.model.format).toBe("safetensors");
    expect(detail.manifest_summary.quant).toBe("NVFP4");
    expect(detail.perf?.timings_source).toBe("vllm");
    expect(detail.serving_provenance?.snapshot).toMatchObject({
      repo: "unsloth/Qwen3.6-35B-A3B-NVFP4-Fast",
      revision,
      merkle_sha256: merkle,
    });

    const variantHtml = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));
    const boardHtml = renderToStaticMarkup(createElement(HomeLeaderboard, { models: index.models }));
    const provenanceHtml = renderToStaticMarkup(createElement(EngineProvenance, { provenance: detail.serving_provenance }));
    expect(variantHtml).toContain("NVFP4");
    expect(variantHtml).toContain("vLLM");
    expect(variantHtml).toContain(`hf://unsloth/Qwen3.6-35B-A3B-NVFP4-Fast@${revision}`);
    expect(boardHtml).toContain("vLLM");
    expect(provenanceHtml).toContain("determinism canary: passed");
    expect(provenanceHtml).toContain("SSM cache: float32");
    expect(provenanceHtml).toContain(merkle);
    expect(provenanceHtml).toContain(fileHash);
    expect(provenanceHtml).toContain("dependency lock");
  }, 30_000);

  it("rejects unknown runtime literals", () => {
    expect(() => RuntimeSchema.parse({ name: "unknown-engine", version: null, kv_cache_quant: null, ctx_len_configured: null, parallel_slots: null })).toThrow();
  });
});

function readJson(file: string): unknown {
  return JSON.parse(readFileSync(file, "utf8"));
}
