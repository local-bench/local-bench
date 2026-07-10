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

function axisWeights(): Record<string, number> {
  const source = readFileSync(path.join(REPO_ROOT, "cli", "src", "localbench", "scoring", "axes.py"), "utf8");
  const weights: Record<string, number> = {};
  for (const block of source.split(/\n\s*Axis\(/).slice(1)) {
    const key = /^\s*"([^"]+)"/.exec(block)?.[1];
    const weight = /"headline",\s*\n\s*([0-9.]+),/.exec(block)?.[1];
    if (key !== undefined && weight !== undefined) {
      weights[key] = Number(weight);
    }
  }
  return weights;
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
    const full = axisWeights();
    const stat = staticWeights();

    expect(text).toContain("execution");
    expect(text).toContain("re-execution");
    expect(text).toContain(
      `${percent(requiredWeight(full, "agentic"))} Agentic, ${percent(
        requiredWeight(full, "knowledge"),
      )} Knowledge, ${percent(
        requiredWeight(full, "instruction_following"),
      )} Instruction-Following, ${percent(requiredWeight(full, "tool_calling"))} Tool calling, ${percent(
        requiredWeight(full, "coding"),
      )} Coding, and ${percent(requiredWeight(full, "math"))} Math`,
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
});
