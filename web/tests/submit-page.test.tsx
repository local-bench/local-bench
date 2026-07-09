import { readFileSync } from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import SubmitPage from "../app/submit/page";

const REPO_ROOT = path.resolve(process.cwd(), "..");

function suiteResolverConstant(name: string): string {
  const source = readFileSync(path.join(REPO_ROOT, "cli", "src", "localbench", "suite_resolver.py"), "utf8");
  const match = new RegExp(`${name}: Final = "([^"]+)"`).exec(source);
  if (match === null) {
    throw new Error(`missing suite resolver constant ${name}`);
  }
  return match[1] ?? "";
}

function htmlEscapedText(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#x27;");
}

describe("SubmitPage", () => {
  it("renders release guidance from the landed suite resolver constants", () => {
    const full = suiteResolverConstant("DEFAULT_SUITE_ID");
    const staticExec = suiteResolverConstant("STATIC_EXEC_SUITE_ID");
    const staticCore = suiteResolverConstant("STATIC_CORE_DIAG_SUITE_ID");
    const advancedRunCommand = [
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
    ].join(" \\\n  ");
    const html = renderToStaticMarkup(createElement(SubmitPage));

    expect(html).toContain(full);
    expect(html).toContain(staticExec);
    expect(html).toContain(staticCore);
    expect(html).toContain("no submitter Docker requirement");
    expect(html).toContain("project re-execution");
    expect(html).toContain("local-bench.ai/submission?id=");
    expect(html).toContain("signed bundle");
    expect(html).toContain("Nothing auto-publishes");
    expect(html).toContain('pip install &quot;local-bench-ai[hf]==0.3.0&quot;');
    expect(html).toContain("localbench bench qwen3-8b --quant Q4_K_M");
    expect(html).toContain("offers submission at the end");
    expect(html).toContain("Advanced route: bring your own server");
    expect(html).toContain(htmlEscapedText(advancedRunCommand));
    expect(html).toContain("localbench submit run --run runs/qwen3-8b-q4-k-m.json");
  });
});
