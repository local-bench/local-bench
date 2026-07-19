import { describe, expect, it } from "vitest";
import { RUNTIME_PROFILES, buildRecipe, type OnrampCatalogModel, type OnrampCatalogQuant, type RuntimeId, type RuntimeProfile } from "../lib/onramp";

function model(overrides: Partial<OnrampCatalogModel> = {}): OnrampCatalogModel {
  return {
    id: "Qwen/Qwen3-8B",
    slug: "qwen3-8b",
    displayName: "Qwen3 8B",
    family: "Qwen3",
    org: "Qwen",
    paramsB: 8.2,
    reasoningCapable: true,
    license: "apache-2.0",
    ggufRepo: "MaziyarPanahi/Qwen3-8B-GGUF",
    downloads: 11_000_000,
    likes: 420,
    trending: 31,
    modelKind: "base",
    baseModelIds: [],
    baseModelId: null,
    baseModelSlug: null,
    baseModelDisplayName: null,
    quants: [
      {
        label: "Q8_0",
        vramGb8k: 10.1,
        fileGb: 8.7,
        bpw: 8.5,
        filename: "Qwen3-8B.Q8_0.gguf",
        revision: "ac6dd95cf227fe9138362c0536fe3c3802008ccf",
        fileSha256: "a".repeat(64),
      },
      {
        label: "Q6_K",
        vramGb8k: 8.2,
        fileGb: 6.8,
        bpw: 6.6,
        filename: "Qwen3-8B.Q6_K.gguf",
        revision: "ac6dd95cf227fe9138362c0536fe3c3802008ccf",
        fileSha256: "b".repeat(64),
      },
      {
        label: "Q4_K_M",
        vramGb8k: 6.0,
        fileGb: 5.0,
        bpw: 4.8,
        filename: "Qwen3-8B.Q4_K_M.gguf",
        revision: "ac6dd95cf227fe9138362c0536fe3c3802008ccf",
        fileSha256: "c".repeat(64),
      },
    ],
    ...overrides,
  };
}

function runtimeProfile(id: RuntimeId): RuntimeProfile {
  const profile = RUNTIME_PROFILES.find((candidate) => candidate.id === id);
  if (profile === undefined) {
    throw new Error(`Missing runtime profile: ${id}`);
  }
  return profile;
}

function quantAt(entry: OnrampCatalogModel, index: number): OnrampCatalogQuant {
  const quant = entry.quants[index];
  if (quant === undefined) {
    throw new Error(`Missing quant at index ${index}`);
  }
  return quant;
}

describe("buildRecipe", () => {
  const llamacpp = runtimeProfile("llamacpp");
  const vllm = runtimeProfile("vllm");
  const lmstudio = runtimeProfile("lmstudio");

  it("emits a board-comparable bounded-final recipe for a Qwen model on llama.cpp", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.lead).toEqual({
      kind: "publishable",
      command: "localbench bench qwen3-8b --quant Q4_K_M --allow-untrusted-code",
    });
    expect(recipe.ggufRepo).toBe("MaziyarPanahi/Qwen3-8B-GGUF");
    expect(recipe.model).toBe(selected);
    expect(recipe.setupCommand).toBe(
      'pip install "local-bench-ai[hf]"\nlocalbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms\nlocalbench cache-tokenizer Qwen/Qwen3-8B',
    );
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/qwen3-8b-q4-k-m.json");
    expect(recipe.servedModelName).toBe("MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe(
      "llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --ctx-size 32768 --parallel 1 --alias MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080",
    );
    expect(recipe.identityMode).toBe("full");
    expect(recipe.benchCommand).toBe(
      [
        "localbench run",
        "--endpoint http://localhost:8080/v1",
        "--model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M",
        "--hf-model-id Qwen/Qwen3-8B",
        "--lane bounded-final-v2",
        "--profile auto",
        "--tier standard",
        "--publishable",
        "--sampler-temperature 0",
        "--sampler-top-k 1",
        "--sampler-seed 1234",
        "--determinism-policy gpu-greedy-single-slot-v1",
        "--model-file <path-to-qwen3-8b-q4-k-m.gguf>",
        "--model-family Qwen3",
        "--quant-label Q4_K_M",
        "--model-format gguf",
        "--tokenizer-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer.json",
        "--chat-template-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer_config.json",
        "--runtime-name llama.cpp",
        "--runtime-version <llama.cpp-build>",
        "--kv-cache-quant f16",
        "--ctx-len-configured 32768",
        "--parallel-slots 1",
        "--out runs/qwen3-8b-q4-k-m.json",
      ].join(" \\\n  "),
    );
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).not.toContain("--suite-dir");
    expect(recipe.benchCommand).toContain(" \\\n  --endpoint");
  });

  it("emits a basic identity recipe for pasted GGUF repos without an HF identity repo", () => {
    const pasted = model({
      id: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      slug: "deepseek-r1-distill-qwen-7b-gguf",
      displayName: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      family: "",
      ggufRepo: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      quants: [{ label: "Q4_K_M", vramGb8k: null, fileGb: null, bpw: null }],
    });
    const recipe = buildRecipe({ model: pasted, quant: quantAt(pasted, 0), runtime: llamacpp, hfModelId: null, source: "paste" });

    expect(recipe.lead).toEqual({
      kind: "local-only",
      command: "localbench bench bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF --quant Q4_K_M --allow-untrusted-code",
    });
    expect(recipe.identityMode).toBe("basic");
    expect(recipe.setupCommand).not.toContain("cache-tokenizer");
    expect(recipe.benchCommand).not.toContain("--hf-model-id");
    expect(recipe.benchCommand).not.toContain("--tokenizer-file");
    expect(recipe.benchCommand).not.toContain("--chat-template-file");
    expect(recipe.benchCommand).toBe(
      [
        "localbench run",
        "--endpoint http://localhost:8080/v1",
        "--model bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF:Q4_K_M",
        "--gguf-repo-only",
        "--lane bounded-final-v2",
        "--profile auto",
        "--tier standard",
        "--publishable",
        "--sampler-temperature 0",
        "--sampler-top-k 1",
        "--sampler-seed 1234",
        "--determinism-policy gpu-greedy-single-slot-v1",
        "--model-file <path-to-deepseek-r1-distill-qwen-7b-gguf-q4-k-m.gguf>",
        "--model-family <model-family>",
        "--quant-label Q4_K_M",
        "--model-format gguf",
        "--runtime-name llama.cpp",
        "--runtime-version <llama.cpp-build>",
        "--kv-cache-quant f16",
        "--ctx-len-configured 32768",
        "--parallel-slots 1",
        "--out runs/deepseek-r1-distill-qwen-7b-gguf-q4-k-m.json",
      ].join(" \\\n  "),
    );
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/deepseek-r1-distill-qwen-7b-gguf-q4-k-m.json");
  });

  it("emits a full identity recipe for pasted GGUF repos with an exact HF identity repo", () => {
    const pasted = model({
      id: "bartowski/QwQ-32B-GGUF",
      slug: "qwq-32b-gguf",
      displayName: "bartowski/QwQ-32B-GGUF",
      family: "",
      ggufRepo: "bartowski/QwQ-32B-GGUF",
      quants: [{ label: "Q5_K_M", vramGb8k: null, fileGb: null, bpw: null }],
    });
    const recipe = buildRecipe({ model: pasted, quant: quantAt(pasted, 0), runtime: llamacpp, hfModelId: "Qwen/QwQ-32B", source: "paste" });

    expect(recipe.lead).toEqual({
      kind: "local-only",
      command: "localbench bench bartowski/QwQ-32B-GGUF --quant Q5_K_M --allow-untrusted-code",
    });
    expect(recipe.identityMode).toBe("full");
    expect(recipe.setupCommand).toContain("localbench cache-tokenizer Qwen/QwQ-32B");
    expect(recipe.benchCommand).not.toContain("--gguf-repo-only");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/QwQ-32B");
    expect(recipe.benchCommand).toContain("--model-family <model-family>");
    expect(recipe.benchCommand).toContain(
      "--tokenizer-file ~/.cache/huggingface/hub/models--Qwen--QwQ-32B/snapshots/<revision>/tokenizer.json",
    );
    expect(recipe.benchCommand).toContain(
      "--chat-template-file ~/.cache/huggingface/hub/models--Qwen--QwQ-32B/snapshots/<revision>/tokenizer_config.json",
    );
    expect(recipe.benchCommand).toContain("--out runs/qwq-32b-gguf-q5-k-m.json");
  });

  it("uses the documented immutable-snapshot command for the vLLM maintainer lane", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000 --generation-config vllm");
    expect(recipe.runtimeId).toBe("vllm");
    expect(recipe.lead).toEqual({
      kind: "maintainer",
      command: expect.stringContaining(
        "localbench bench \\\n  --runtime vllm \\\n  --model-ref hf://Qwen/Qwen3-8B@<full-40-character-revision>",
      ),
    });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--determinism-canary") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--model-id qwen3-8b") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--seed 1234") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--wsl-distro <wsl-distro>") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--vllm-venv <absolute-wsl-vllm-venv>") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--wsl-venv-python <absolute-wsl-appworld-python>") });
    expect(recipe.lead).toEqual({ kind: "maintainer", command: expect.stringContaining("--appworld-root <absolute-wsl-appworld-root>") });
    expect(recipe.serveNote).toContain("full-precision");
    expect(recipe.serveNote).not.toContain("pass --generation-config vllm");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
    expect(recipe.serveNote).toContain("curl http://localhost:1234/v1/models");
  });

  it("gives a non-reasoning model the same ranked bounded-final recipe (profile auto)", () => {
    const selected = model({ reasoningCapable: false });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/qwen3-8b-q4-k-m.json");
    expect(recipe.benchCommand).toContain("--lane bounded-final-v2");
    expect(recipe.benchCommand).toContain("--profile auto");
  });

  it("gives a reasoning model outside Qwen3/Gemma the same ranked bounded-final recipe", () => {
    const selected = model({ family: "Granite 3", org: "IBM" });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.benchCommand).toContain("--profile auto");
  });

  it("carries fine-tune lineage through the recipe model payload", () => {
    const selected = model({
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      displayName: "Qwopus3.6 27B v2 MTP",
    });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.model.baseModelDisplayName).toBe("Qwen3.6 27B");
    expect(recipe.model.baseModelSlug).toBe("qwen3-6-27b");
  });

  it("falls back to the classic recipe when the selected catalog quant has no artifact pin", () => {
    const selected = model({
      quants: [{ label: "Q4_K_M", vramGb8k: 6.0, fileGb: 5.0, bpw: 4.8 }],
    });

    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 0), runtime: llamacpp });

    expect(recipe.lead).toEqual({
      kind: "unavailable",
      reason: "This catalog quant is missing artifact pins, so the one-command flow fails closed.",
    });
    expect(recipe.benchCommand).toContain("localbench run");
    expect(recipe.setupCommand).toContain('local-bench-ai[hf]');
  });
});
