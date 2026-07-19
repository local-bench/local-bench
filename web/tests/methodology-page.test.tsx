import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import MethodologyPage from "../app/methodology/page";
import { SEASON_2_AXIS_WEIGHTS } from "../lib/axis-contributions";

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
  // Keep one decimal when the weight is not a whole percent (22.5%, 7.5%),
  // matching the index-v4.2 methodology copy; whole percents stay bare (25%).
  return `${Math.round(weight * 1000) / 10}%`;
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
  it("describes execution, current axes, and honest publication trust", async () => {
    const text = normalizeText(renderToStaticMarkup(await MethodologyPage()));
    const stat = staticWeights();

    expect(text).toContain("execution");
    // The intro must describe the CURRENT (season-2) sortable number, derived from the same
    // weight constants the contribution rail uses so intro copy can never drift from scoring.
    expect(text).toContain(
      `${percent(SEASON_2_AXIS_WEIGHTS.tool_use)} Agentic, ${percent(SEASON_2_AXIS_WEIGHTS.knowledge)} Knowledge, ${percent(
        SEASON_2_AXIS_WEIGHTS.instruction,
      )} Instruction-Following, ${percent(SEASON_2_AXIS_WEIGHTS.coding)} Coding, and ${percent(SEASON_2_AXIS_WEIGHTS.math)} Math`,
    );
    // Season-1 weights stay documented as history in the "What index-v3.0 measures" section.
    expect(text).toContain(
      "Season-1 headline weights were 40% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, 15% Coding, and 5% Math",
    );
    expect(text).toContain(
      `${percent(requiredWeight(stat, "knowledge"))} Knowledge, ${percent(
        requiredWeight(stat, "instruction_following"),
      )} Instruction-Following, ${percent(requiredWeight(stat, "tool_calling"))} Tool calling, ${percent(
        requiredWeight(stat, "coding"),
      )} Coding, and ${percent(requiredWeight(stat, "math"))} Math`,
    );
    expect(text).toContain("BigCodeBench-Hard Instruct execution pass rate");
    expect(text).toContain("Coding and Agentic evidence travel with the bundle");
    expect(text).toContain("not independently reproduced by default");
    expect(text).toContain("141 sandbox-scoreable BigCodeBench-Hard items");
    expect(text).toContain("lcb, the old LiveCodeBench output-prediction proxy, is legacy diagnostic data");
    expect(text).toContain("Static-Core");
    expect(text).toContain("unranked diagnostic release");
    expect(text).toContain("Serving engine lanes");
    expect(text).toContain("snapshot Merkle identity and per-file hashes");
    expect(text).toContain("localbench bench --runtime vllm --model-ref hf://");
    expect(text).toContain("&lt;repo&gt;@&lt;revision&gt;");
    expect(text).toContain("Agentic headroom is deliberate.</span> Low agentic scores");
    expect(text).toContain("Names are details, not identity proof.</span> An optional free-text handle");
  });

  it("does not retain the old Qwen/Gemma-only eligibility sentence anywhere under web", () => {
    const forbidden = "Only " + "Qwen3-";
    for (const file of webTextFiles(WEB_ROOT)) {
      expect(readFileSync(file, "utf8"), file).not.toContain(forbidden);
    }
  });

  it("documents the v4.2 correction, AppWorld scope, diagnostics, archives, and bridge guard", async () => {
    const text = normalizeText(renderToStaticMarkup(await MethodologyPage()));

    expect(text).toContain("Protocol v4.2 · LB-2026-07.2");
    expect(text).toContain("LB-2026-07.2 (scorecard-v6)");
    expect(text).toContain("Community and project rows must be scored identically");
    expect(text).toContain("making Agentic AppWorld-only everywhere");
    expect(text).toContain("fixed 96-task subset");
    expect(text).toContain("seeded stratified recipe");
    expect(text).toContain("Raw inference outputs are unchanged; no model was re-run");
    expect(text).toContain("53.12</td><td class=\"px-3 py-2 font-mono text-bench-accent\">51.31");
    expect(text).toContain("href=\"/data/archive/index-v4.1.json\"");
    expect(text).toContain("href=\"/data/archive/agentic-v4.1.json\"");
    expect(text).toContain("BFCL v3 multi-turn base — frozen snapshot");
    expect(text).toContain("never weighted, never zero-filled, and never used for ranking");
    expect(text).toContain("the only sanctioned pairing");
    expect(text).toContain("A partial v4 composite is never displayed or ranked");
  });

  it("discloses the evidence retained for community reports", async () => {
    const text = normalizeText(renderToStaticMarkup(await MethodologyPage()));

    expect(text).toContain("structured model artifact identity");
    expect(text).toContain("axis scores, sample counts, confidence intervals, and downloadable evidence");
  });
});
