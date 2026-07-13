import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import MethodologyPage from "../app/methodology/page";

const WEB_ROOT = process.cwd();
const REPO_ROOT = path.resolve(WEB_ROOT, "..");

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ");
}

function staticWeights(): Record<string, number> {
  const source = readFileSync(path.join(REPO_ROOT, "cli", "src", "localbench", "scoring", "axes.py"), "utf8");
  const body = /STATIC_SUITE_WEIGHTS: Final\[dict\[str, float\]\] = \{([\s\S]*?)\n\}/.exec(source)?.[1] ?? "";
  const weights: Record<string, number> = {};
  for (const match of body.matchAll(/"([^"]+)":\s*([0-9.]+)/g)) {
    weights[match[1] ?? ""] = Number(match[2]);
  }
  return weights;
}

function percent(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

function requiredWeight(weights: Record<string, number>, key: string): number {
  const value = weights[key];
  if (value === undefined) {
    throw new Error(`missing ${key} axis weight`);
  }
  return value;
}

function webTextFiles(dir: string): readonly string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    if (entry === "node_modules" || entry === ".next" || entry === "out") {
      continue;
    }
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      files.push(...webTextFiles(fullPath));
    } else if (/\.(css|json|md|mjs|ts|tsx|txt)$/.test(entry)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("MethodologyPage", () => {
  it("describes execution/re-execution, current axes, and coding trust", async () => {
    const text = normalizeText(renderToStaticMarkup(await MethodologyPage()));
    const stat = staticWeights();

    expect(text).toContain("execution");
    expect(text).toContain("re-execution");
    expect(text).toContain(
      "40% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, 15% Coding, and 5% Math",
    );
    expect(text).toContain(
      `${percent(requiredWeight(stat, "knowledge"))} Knowledge, ${percent(
        requiredWeight(stat, "instruction_following"),
      )} Instruction-Following, ${percent(requiredWeight(stat, "tool_calling"))} Tool calling, ${percent(
        requiredWeight(stat, "coding"),
      )} Coding, and ${percent(requiredWeight(stat, "math"))} Math`,
    );
    expect(text).toContain("BigCodeBench-Hard Instruct execution pass rate");
    expect(text).toContain(
      "Every ranked bundle must include code artifacts; the ranked Coding score is produced by maintainer project re-execution in a hardened rootless sandbox, so submitters do not need Docker and self-reported execution verdicts never rank.",
    );
    expect(text).toContain("141 sandbox-scoreable BigCodeBench-Hard items");
    expect(text).toContain("lcb, the old LiveCodeBench output-prediction proxy, is legacy diagnostic data");
    expect(text).toContain("Static-Core");
    expect(text).toContain("unranked diagnostic release");
    expect(text).toContain("Serving engine lanes");
    expect(text).toContain("snapshot Merkle identity and per-file hashes");
    expect(text).toContain("localbench bench --runtime vllm --model-ref hf://");
    expect(text).toContain("&lt;repo&gt;@&lt;revision&gt;");
  });

  it("does not retain the old Qwen/Gemma-only eligibility sentence anywhere under web", () => {
    const forbidden = "Only " + "Qwen3-";
    for (const file of webTextFiles(WEB_ROOT)) {
      expect(readFileSync(file, "utf8"), file).not.toContain(forbidden);
    }
  });

  it("documents the season-2 macro-axis, diagnostics, Option-D anchors, and bridge guard", async () => {
    const text = normalizeText(renderToStaticMarkup(await MethodologyPage()));

    expect(text).toContain("Season 2 · index-v4.0");
    expect(text).toContain("bench-normalized weighted mean");
    expect(text).toContain("not item-count pooling");
    expect(text).toContain("AppWorld Test-Normal");
    expect(text).toContain("BFCL single-turn, BFCL multi-turn long-context, RULER 32K");
    expect(text).toContain("never weighted, never required for coverage, and never used for ranking");
    expect(text).toContain("the only sanctioned pairing");
    expect(text).toContain("A partial v4 composite is never displayed or ranked");
  });
});
