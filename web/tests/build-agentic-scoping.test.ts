import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

type JsonObject = Record<string, unknown>;

const WEB_ROOT = process.cwd();
const REPO_ROOT = join(WEB_ROOT, "..");
const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("agentic build scoping", () => {
  it("skips repo records outside a single-source build", () => {
    const workspace = temporaryDirectory("localbench-agentic-scope-");
    const sourcesPath = join(workspace, "sources.json");
    const outDir = join(workspace, "out");
    const source = firstCuratedSource();
    writeFileSync(sourcesPath, `${JSON.stringify([source])}\n`, "utf8");

    const result = spawnSync(
      "uv",
      [
        "run",
        "--project",
        join(REPO_ROOT, "cli"),
        "python",
        "build_data.py",
        "--sources",
        sourcesPath,
        "--out",
        outDir,
        "--iters",
        "1",
        "--benches",
        "knowledge",
        "--allow-lineage-gaps",
      ],
      { cwd: WEB_ROOT, encoding: "utf8" },
    );

    expect(result.status, result.stderr || result.stdout).toBe(0);
    const agentic = readJsonObject(join(outDir, "agentic.json"));
    expect(agentic["models"]).toEqual({});
  });

  it("fails loudly when a maintainer-curated build omits ranked records", () => {
    const workspace = temporaryDirectory("localbench-agentic-strict-");
    const outDir = join(workspace, "out");
    mkdirSync(outDir);
    writeFileSync(join(outDir, "index.json"), '{"models":[]}\n', "utf8");

    const result = spawnSync(
      "uv",
      [
        "run",
        "--project",
        join(REPO_ROOT, "cli"),
        "python",
        "-c",
        "from pathlib import Path; import sys; from build_data import _build_agentic_column; _build_agentic_column(Path(sys.argv[1]), maintainer_curated=True)",
        outDir,
      ],
      { cwd: WEB_ROOT, encoding: "utf8" },
    );

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("no matching best_run_id in index.json");
  });
});

function firstCuratedSource(): JsonObject {
  const parsed: unknown = JSON.parse(readFileSync(join(WEB_ROOT, "data_sources.json"), "utf8"));
  if (!Array.isArray(parsed) || !isJsonObject(parsed[0])) {
    throw new Error("data_sources.json has no object source");
  }
  return parsed[0];
}

function readJsonObject(path: string): JsonObject {
  const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));
  if (!isJsonObject(parsed)) throw new Error(`${path} is not a JSON object`);
  return parsed;
}

function isJsonObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function temporaryDirectory(prefix: string): string {
  const directory = mkdtempSync(join(tmpdir(), prefix));
  temporaryDirectories.push(directory);
  return directory;
}
