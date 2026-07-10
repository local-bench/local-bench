import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BenchmarkRecipe, copyableCommand } from "../components/benchmark-recipe";
import type { BenchmarkRecipe as Recipe, OnrampCatalogModel } from "../lib/onramp";

const baseModel: OnrampCatalogModel = {
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
  quants: [{ label: "Q4_K_M", vramGb8k: 6, fileGb: 5, bpw: 4.8 }],
};

function recipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    installCommand: 'pip install "local-bench-ai[hf]==0.3.1"',
    lead: {
      kind: "publishable",
      command: "localbench bench qwen3-8b --quant Q4_K_M --static-only",
    },
    setupCommand:
      'pip install "local-bench-ai[hf]==0.3.1"\nlocalbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms\nlocalbench cache-tokenizer Qwen/Qwen3-8B',
    serveCommand:
      "llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --ctx-size 32768 --parallel 1 --alias MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080",
    serveNote: null,
    benchCommand:
      "localbench run \\\n  --endpoint http://localhost:8080/v1 \\\n  --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M \\\n  --hf-model-id Qwen/Qwen3-8B \\\n  --lane bounded-final-v2 \\\n  --profile auto \\\n  --tier standard \\\n  --publishable \\\n  --sampler-temperature 0 \\\n  --sampler-top-k 1 \\\n  --sampler-seed 1234 \\\n  --determinism-policy gpu-greedy-single-slot-v1 \\\n  --model-file <path-to-qwen3-8b-q4-k-m.gguf> \\\n  --model-family Qwen3 \\\n  --quant-label Q4_K_M \\\n  --model-format gguf \\\n  --tokenizer-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer.json \\\n  --chat-template-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer_config.json \\\n  --runtime-name llama.cpp \\\n  --runtime-version <llama.cpp-build> \\\n  --kv-cache-quant f16 \\\n  --ctx-len-configured 32768 \\\n  --parallel-slots 1 \\\n  --out runs/qwen3-8b-q4-k-m.json",
    submitCommand: "localbench submit run --run runs/qwen3-8b-q4-k-m.json",
    lane: "bounded-final-v2",
    servedModelName: "MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M",
    ggufRepo: "MaziyarPanahi/Qwen3-8B-GGUF",
    identityMode: "full",
    model: baseModel,
    runtimeId: "llamacpp",
    ...overrides,
  };
}

describe("BenchmarkRecipe", () => {
  it("renders the vLLM maintainer recipe and community-lane caveat", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe({
      runtimeId: "vllm",
      lead: { kind: "maintainer", command: "localbench bench --runtime vllm --model-ref hf://Qwen/Qwen3-8B@<full-40-character-revision> --model-id qwen3-8b --seed 1234 --wsl-distro <wsl-distro> --vllm-venv <absolute-wsl-vllm-venv> --wsl-venv-python <absolute-wsl-appworld-python> --appworld-root <absolute-wsl-appworld-root>" },
    }) }));

    expect(html).toContain("vLLM maintainer lane");
    expect(html).toContain("--runtime vllm --model-ref hf://Qwen/Qwen3-8B@");
    expect(html).toContain("community path remains llama.cpp/GGUF until the appliance ships");
    expect(html).toContain("--wsl-distro &lt;wsl-distro&gt;");
    expect(html).toContain("--vllm-venv &lt;absolute-wsl-vllm-venv&gt;");
    expect(html).toContain("--wsl-venv-python &lt;absolute-wsl-appworld-python&gt;");
    expect(html).toContain("--appworld-root &lt;absolute-wsl-appworld-root&gt;");
    expect(html).toContain("Replace every &lt;placeholder&gt;");
  });

  it("leads pinned catalog models with the one-command flow and keeps classic commands collapsed", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe() }));

    expect(html).toContain('pip install &quot;local-bench-ai[hf]==0.3.1&quot;');
    expect(html).toContain("localbench bench qwen3-8b --quant Q4_K_M --static-only");
    expect(html).toContain("Python 3.11+");
    expect(html).toContain("llama-server on PATH");
    expect(html).toContain("github.com/ggerganov/llama.cpp/releases");
    expect(html).toContain("verifies downloads against pinned hashes");
    expect(html).toContain("checks publishability before starting");
    expect(html).toContain("asks before submitting");
    expect(html).toContain("Public path");
    expect(html).toContain("--wsl-venv-python");
    expect(html).toContain("--appworld-root");
    expect(html).toContain("Advanced: bring your own server (vLLM, custom rigs)");
    expect(html).toContain("Identity: full");
    expect(html).toContain("HF tokenizer/template cached");
    expect(html).toContain("Gated repo");
    expect(html).toContain("hf auth login");
    expect(html).toContain("HF_TOKEN");
    expect(html).toContain("This is a full ranked run");
    expect(html).toContain("Preflight fails fast");
    expect(html).toContain("copies as one line");
  });

  it("leads with the classic recipe when artifact pins are missing", () => {
    const html = renderToStaticMarkup(
      createElement(BenchmarkRecipe, {
        recipe: recipe({
          lead: {
            kind: "unavailable",
            reason: "This catalog quant is missing artifact pins, so the one-command flow fails closed.",
          },
        }),
      }),
    );

    expect(html).toContain("This catalog quant is missing artifact pins");
    expect(html).toContain("localbench run");
    expect(html).not.toContain("localbench bench qwen3-8b --quant Q4_K_M --static-only");
    expect(html).not.toContain("Advanced: bring your own server");
  });

  it("labels pasted HF repo one-command recipes as local-only", () => {
    const html = renderToStaticMarkup(
      createElement(BenchmarkRecipe, {
        recipe: recipe({
          lead: {
            kind: "local-only",
            command: "localbench bench bartowski/QwQ-32B-GGUF --quant Q5_K_M --static-only",
          },
        }),
      }),
    );

    expect(html).toContain("LOCAL-ONLY");
    expect(html).toContain("localbench bench bartowski/QwQ-32B-GGUF --quant Q5_K_M --static-only");
    expect(html).toContain("managed path below is publishable");
  });

  it("states original-release lineage in the recipe header", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe() }));

    expect(html).toContain("Benchmarking Qwen3 8B — Original release");
  });

  it("states variant lineage with kind and creator in the recipe header", () => {
    const fineTune = {
      ...baseModel,
      slug: "qwopus3-6-27b-v2-mtp",
      displayName: "Qwopus3.6 27B v2 MTP",
      org: "Jackrong",
      modelKind: "finetune",
      baseModelIds: ["Qwen/Qwen3.6-27B"],
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6-27B",
    } satisfies OnrampCatalogModel;
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe({ model: fineTune }) }));

    expect(html).toContain("Benchmarking Qwopus3.6 27B v2 MTP — fine-tune of Qwen3.6-27B · by Jackrong");
  });

  it("treats an out-of-catalog pretrain base_model as an original release, not a variant", () => {
    const instructTuneOfOwnPretrain = {
      ...baseModel,
      baseModelIds: ["Qwen/Qwen3-8B-Base"],
      baseModelId: "Qwen/Qwen3-8B-Base",
      baseModelSlug: null,
      baseModelDisplayName: "Qwen/Qwen3-8B-Base",
    } satisfies OnrampCatalogModel;
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe({ model: instructTuneOfOwnPretrain }) }));

    expect(html).toContain("Benchmarking Qwen3 8B — Original release");
    expect(html).not.toContain("official variant");
  });

  it("shows a loud basic identity badge when tokenizer provenance is absent", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe({ identityMode: "basic" }) }));

    expect(html).toContain("Identity: basic");
    expect(html).toContain("tokenizer/chat-template digests will be null");
    expect(html).toContain("Add the model");
    expect(html).toContain("exact non-GGUF HF repo");
  });

  it("copies multi-line command blocks as one shell line", () => {
    expect(
      copyableCommand(
        "localbench run \\\n  --endpoint http://localhost:8080/v1 \\\n  --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M",
      ),
    ).toBe("localbench run --endpoint http://localhost:8080/v1 --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
  });

  it("copies the expanded run recipe as one shell line", () => {
    expect(copyableCommand(recipe().benchCommand)).toBe(
      "localbench run --endpoint http://localhost:8080/v1 --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --hf-model-id Qwen/Qwen3-8B --lane bounded-final-v2 --profile auto --tier standard --publishable --sampler-temperature 0 --sampler-top-k 1 --sampler-seed 1234 --determinism-policy gpu-greedy-single-slot-v1 --model-file <path-to-qwen3-8b-q4-k-m.gguf> --model-family Qwen3 --quant-label Q4_K_M --model-format gguf --tokenizer-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer.json --chat-template-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer_config.json --runtime-name llama.cpp --runtime-version <llama.cpp-build> --kv-cache-quant f16 --ctx-len-configured 32768 --parallel-slots 1 --out runs/qwen3-8b-q4-k-m.json",
    );
  });
});
