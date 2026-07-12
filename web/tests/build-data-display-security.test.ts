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

def fixture(slug, *, origin, trust_label, ranked, score, catalog_id=None, curated=False, suffix="fixture", order=0):
    run_id = f"{slug}__{suffix}"
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
        "model_row": model_row, "order": order, "run_id": run_id, "slug": slug,
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
trusted_catalog = fixture(
    target["slug"], origin="project_anchor", trust_label="project_anchor",
    ranked=True, score=10, suffix="trusted", order=1,
)
curated_catalog = fixture(
    target["slug"], origin="community", trust_label="community_re_scored",
    ranked=False, score=50, catalog_id=target["id"], curated=True,
    suffix="curated", order=2,
)
curated_alias = fixture(
    "attacker-alias", origin="community", trust_label="community_re_scored",
    ranked=False, score=99, catalog_id=target["id"], curated=True,
    suffix="alias", order=3,
)
collision_payload = builder._catalog_display_payload(
    target, builder._trusted_precedence_union([trusted_catalog], [curated_alias]),
)
precedence_curated = fixture(
    target["slug"], origin="community", trust_label="community_re_scored",
    ranked=False, score=100, curated=True, suffix="shared", order=0,
)
precedence_trusted = fixture(
    target["slug"], origin="project_anchor", trust_label="project_anchor",
    ranked=True, score=10, suffix="shared", order=1,
)
precedence_union = builder._trusted_precedence_union([precedence_trusted], [precedence_curated])

demo_source = {
    "agentic_provenance": "self_reported", "demo": True,
    "demo_score": {"quality": 50, "ci": 2, "tok_s": 10},
    "family": "Fixture", "file": "demo.json", "independent_replication": False,
    "kind": "community", "model_label": "Annotated Demo", "origin": "community",
    "quant_label": "demo", "reasoning_lane": "answer-only", "trust_label": "community_re_scored",
    "vram_footprint_gb": 1,
}
demo = builder._build_run(
    demo_source, order=0, iters=1, benches=builder.BENCHES,
    weights=builder.COMPOSITE_WEIGHTS, board=None,
)
demo["maintainer_curated_static"] = True

with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    baseline = root / "baseline"
    attacked = root / "attacked"
    dynamic_out = root / "dynamic"
    curated_out = root / "curated"
    catalog_out = root / "catalog"
    keyed_out = root / "keyed"
    collision_out = root / "collision"
    builder._write_outputs(baseline, [], catalog)
    builder._write_outputs(attacked, [forged], catalog)
    builder._write_outputs(dynamic_out, [dynamic], [])
    builder._write_outputs(curated_out, [curated], [])
    builder._write_outputs(catalog_out, [trusted_catalog, curated_catalog], [target])
    builder._write_outputs(keyed_out, [curated_alias], [target])
    try:
        builder._write_outputs(collision_out, [trusted_catalog, curated_alias], [target])
    except builder.DataBuildError as exc:
        collision_error = str(exc)
    else:
        collision_error = None
    catalog_index = json.loads((catalog_out / "index.json").read_text())["models"][0]
    catalog_page = json.loads((catalog_out / "models" / f"{target['slug']}.json").read_text())
    keyed_index = json.loads((keyed_out / "index.json").read_text())["models"]
    keyed_page = json.loads((keyed_out / "models" / f"{target['slug']}.json").read_text())
    result = {
        "target_slug": target["slug"],
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
        "catalog_payload_run_ids": [row.get("run_id") for row in catalog_page["runs"] if row.get("run_id")],
        "collision_payload_run_ids": [row.get("run_id") for row in collision_payload["runs"] if row.get("run_id")],
        "collision_error": collision_error,
        "trusted_precedence": len(precedence_union) == 1 and precedence_union[0]["index_row"]["origin"] == "project_anchor",
        "keyed_index_slugs": [row["slug"] for row in keyed_index],
        "keyed_page_run_ids": [row.get("run_id") for row in keyed_page["runs"] if row.get("run_id")],
        "keyed_standalone_exists": (keyed_out / "models" / "attacker-alias.json").exists(),
        "ranked_catalog_n_runs": catalog_index["n_runs"],
        "ranked_catalog_payload_n_runs": len([row for row in catalog_page["runs"] if row.get("run_id")]),
        "demo_displays": builder._display_eligible(demo),
        "demo_annotations": {
            field: {name: demo[field].get(name) for name in ("origin", "trust_label", "ranked", "agentic_provenance")}
            for field in ("detail", "model_row", "index_row")
        },
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

  it("keeps the trusted run in the catalog payload with trusted run-id precedence and rejects the exact different-slug collision", () => {
    const result = probe;
    expect(result.catalog_payload_run_ids).toEqual(expect.arrayContaining([
      `${String(result.target_slug)}__trusted`,
      `${String(result.target_slug)}__curated`,
    ]));
    expect(result.collision_payload_run_ids).toEqual(expect.arrayContaining([
      `${String(result.target_slug)}__trusted`,
      "attacker-alias__alias",
    ]));
    expect(result.trusted_precedence).toBe(true);
    expect(result.collision_error).toContain("refusing catalog/slug collision");
  });

  it("emits a catalog-keyed non-catalog slug once under its catalog identity", () => {
    const result = probe;
    expect(result.keyed_index_slugs).toEqual([result.target_slug]);
    expect(result.keyed_page_run_ids).toEqual(["attacker-alias__alias"]);
    expect(result.keyed_standalone_exists).toBe(false);
  });

  it("counts only trusted contributing runs on a trusted-ranked catalog row", () => {
    const result = probe;
    expect(result.ranked_catalog_n_runs).toBe(1);
    expect(result.ranked_catalog_payload_n_runs).toBe(2);
  });

  it("annotates every display-eligible demo projection with provenance and an explicit unranked label", () => {
    const result = probe;
    expect(result.demo_displays).toBe(true);
    expect(result.demo_annotations).toEqual({
      detail: { agentic_provenance: "self_reported", origin: "community", ranked: false, trust_label: "community_re_scored" },
      index_row: { agentic_provenance: "self_reported", origin: "community", ranked: false, trust_label: "community_re_scored" },
      model_row: { agentic_provenance: "self_reported", origin: "community", ranked: false, trust_label: "community_re_scored" },
    });
  });
});
