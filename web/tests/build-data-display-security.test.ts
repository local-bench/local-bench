import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

const WEB_ROOT = join(process.cwd());
const REPO_ROOT = join(WEB_ROOT, "..");

const SECURITY_PROBE = String.raw`
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import build_data as builder

catalog = builder.catalog_entries(builder._read_json(Path.cwd() / builder.CATALOG_FILENAME))
target = catalog[0]

def fixture(slug, *, origin, trust_label, ranked, score, catalog_id=None, curated=False):
    run_id = f"{slug}__fixture"
    row = {
        "axes": {}, "best_run_id": run_id, "composite": {"point": score},
        "family": "Fixture", "kind": "community", "model_label": slug,
        "n_runs": 1, "origin": origin, "ranked": ranked, "replicated": False,
        "score_status": "measured", "slug": slug, "trust_label": trust_label,
    }
    model_row = {
        "axes": {}, "composite": {"point": score}, "origin": origin,
        "quant_label": "fixture", "ranked": ranked, "run_id": run_id,
        "score_status": "measured", "trust_label": trust_label,
    }
    return {
        "catalog_id": catalog_id, "composite_raw": score / 100, "detail": {"run_id": run_id},
        "family": "Fixture", "index_row": row, "kind": "community", "model_label": slug,
        "model_row": model_row, "order": 0, "run_id": run_id, "slug": slug,
        "suite_version": "fixture", "maintainer_curated_static": curated,
    }

forged = fixture(
    target["slug"], origin="community", trust_label="community_self_submitted",
    ranked=True, score=100, catalog_id=target["id"],
)
trusted = fixture(
    "trusted", origin="project_anchor", trust_label="project_anchor",
    ranked=True, score=10,
)
dynamic = fixture(
    "dynamic-public", origin="community", trust_label="community_self_submitted",
    ranked=False, score=99,
)
curated = fixture(
    "curated-static", origin="community", trust_label="community_re_scored",
    ranked=False, score=50, curated=True,
)

with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    baseline = root / "baseline"
    attacked = root / "attacked"
    dynamic_out = root / "dynamic"
    curated_out = root / "curated"
    builder._write_outputs(baseline, [], catalog)
    builder._write_outputs(attacked, [forged], catalog)
    builder._write_outputs(dynamic_out, [dynamic], [])
    builder._write_outputs(curated_out, [curated], [])
    result = {
        "protected_unchanged": (
            (baseline / "models" / f"{target['slug']}.json").read_bytes()
            == (attacked / "models" / f"{target['slug']}.json").read_bytes()
        ),
        "forged_details": len(list((attacked / "runs").glob("*.json"))),
        "forged_catalog_groups": builder._catalog_run_groups([forged]),
        "forged_ranks": builder._trusted_ranked_run(forged),
        "representative": builder._representative_run([forged, trusted])["slug"],
        "dynamic_displays": builder._display_eligible(dynamic),
        "dynamic_models": json.loads((dynamic_out / "index.json").read_text())["models"],
        "dynamic_details": len(list((dynamic_out / "runs").glob("*.json"))),
        "curated_displays": builder._display_eligible(curated),
        "curated_models": [row["slug"] for row in json.loads((curated_out / "index.json").read_text())["models"]],
    }
print(json.dumps(result))
`;

function securityProbe(): Record<string, unknown> {
  const result = spawnSync(
    "uv",
    ["run", "--project", join(REPO_ROOT, "cli"), "python", "-c", SECURITY_PROBE],
    { cwd: WEB_ROOT, encoding: "utf8" },
  );
  expect(result.status, result.stderr).toBe(0);
  return JSON.parse(result.stdout) as Record<string, unknown>;
}

describe("static display eligibility security boundary", () => {
  let probe: Record<string, unknown>;

  beforeAll(() => {
    probe = securityProbe();
  });

  it("rejects an untrusted protected-catalog claim from protected model and run outputs", () => {
    const result = probe;
    expect(result.protected_unchanged).toBe(true);
    expect(result.forged_details).toBe(0);
    expect(result.forged_catalog_groups).toEqual({});
  });

  it("never lets an untrusted row rank or displace the trusted representative", () => {
    const result = probe;
    expect(result.forged_ranks).toBe(false);
    expect(result.representative).toBe("trusted");
  });

  it("displays canonical curated-static rows but excludes dynamic public rows", () => {
    const result = probe;
    expect(result.curated_displays).toBe(true);
    expect(result.curated_models).toEqual(["curated-static"]);
    expect(result.dynamic_displays).toBe(false);
    expect(result.dynamic_models).toEqual([]);
    expect(result.dynamic_details).toBe(0);
  });
});
