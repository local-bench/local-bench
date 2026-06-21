"""Re-emit the 4 Qwen3.5 campaign run JSONs with the CURRENT strict scorer (CPU-only).

The campaign run JSONs (cli/runs/campaign-qwen3.5-{0.8b,2b,4b,9b}.json) were written BEFORE the
strict-gate hardening: their per-item `correct` + `benches` aggregate are LEGACY (non-strict), and
the aggregate lacks the termination/conditional decomposition. This re-scores each item from its
stored transcript through localbench's current scorer (strict gate + \\boxed), recomputes the bench
aggregate (incl. termination_rate + conditional_accuracy) + the composite, and re-emits — so the
site's strict-scoring data contract is fulfilled. No GPU. Transcripts (response_text/finish_reason/
usage) are preserved; only the scoring-derived fields change.

DRY-RUN by default (prints legacy-vs-strict, writes nothing). Pass --write to back up each file to
*.legacy.json and overwrite in place.
"""
from __future__ import annotations
import json, os, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(REPO / "cli" / "src"))
from localbench._suite import render_benches, read_json_object, _item_id
from localbench._scoring import _score_response_detail, aggregate, composite

SUITE = REPO / "suite" / "v1"
RUNS = REPO / "cli" / "runs"
FILES = {
    "0.8b": "campaign-qwen3.5-0.8b.json",
    "2b": "campaign-qwen3.5-2b.json",
    "4b": "campaign-qwen3.5-4b.json",
    "9b": "campaign-qwen3.5-9b.json",
}
BENCHES = ("mmlu_pro", "ifbench")
WRITE = "--write" in sys.argv


def main():
    rendered = render_benches("mmlu_pro,ifbench", "standard", None, SUITE, read_json_object(SUITE / "suite.json"), [])
    src = {(b.name, _item_id(si)): si for b in rendered for si in b.source_items}
    baseline = {b.name: b.baseline for b in rendered}

    summary = {}
    for label, fn in FILES.items():
        p = RUNS / fn
        j = json.loads(p.read_text(encoding="utf-8"))
        legacy_comp = j.get("composite")
        legacy_benches = {k: dict(v) for k, v in j["benches"].items()}

        scored = {b: [] for b in BENCHES}
        unmatched = 0
        for it in j["items"]:
            bench = it.get("bench")
            if bench not in scored:
                continue
            si = src.get((bench, str(it["id"])))
            if si is None:
                unmatched += 1
                continue
            fr, err = it.get("finish_reason"), it.get("error")
            detail = _score_response_detail(bench, si, it.get("response_text"), err, fr)
            correct = bool(detail["correct"] and fr != "length")
            it["correct"] = correct
            it["extracted"] = detail["extracted"]
            scored[bench].append({"id": it["id"], "bench": bench, "correct": correct,
                                  "error": err, "finish_reason": fr, "extracted": detail["extracted"]})
        assert unmatched == 0, f"{fn}: {unmatched} unmatched"
        for b in BENCHES:
            assert len(scored[b]) == (400 if b == "mmlu_pro" else 294), f"{fn} {b} coverage {len(scored[b])}"

        new_benches = {b: aggregate(b, scored[b], baseline[b]) for b in BENCHES}
        new_comp = composite(new_benches)

        print(f"\n=== {label}  ({fn}) ===")
        print(f"  COMPOSITE: legacy {legacy_comp*100:5.1f}  ->  strict {new_comp*100:5.1f}")
        for b in BENCHES:
            lb, nb = legacy_benches.get(b, {}), new_benches[b]
            print(f"  {b:9s}: raw legacy {lb.get('raw_accuracy', 0)*100:5.1f} -> strict {nb['raw_accuracy']*100:5.1f}"
                  f" | term {nb['termination_rate']*100:5.1f}  cond {nb['conditional_accuracy']*100:5.1f}"
                  f" | legacy had decomp: {'termination_rate' in lb}")
        summary[label] = {"composite_strict": round(new_comp * 100, 1),
                          "composite_legacy": round((legacy_comp or 0) * 100, 1),
                          "mmlu_pro": {k: round(new_benches['mmlu_pro'][k] * 100, 1) for k in ('raw_accuracy', 'termination_rate', 'conditional_accuracy')},
                          "ifbench": {k: round(new_benches['ifbench'][k] * 100, 1) for k in ('raw_accuracy', 'termination_rate', 'conditional_accuracy')}}

        if WRITE:
            backup = p.with_suffix(".legacy.json")
            if not backup.exists():
                shutil.copy2(p, backup)
            j["benches"] = new_benches
            j["composite"] = new_comp
            p.write_text(json.dumps(j, indent=2), encoding="utf-8")
            print(f"  WROTE {fn} (backup {backup.name})")

    print("\n=== STRICT composites (Local Intelligence Index) ===")
    print("  " + " -> ".join(f"{lbl} {summary[lbl]['composite_strict']}" for lbl in FILES))
    print("  legacy was: " + " -> ".join(f"{lbl} {summary[lbl]['composite_legacy']}" for lbl in FILES))

    if WRITE:
        import subprocess
        try:
            commit = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            commit = "unknown"
        manifest = {
            "purpose": "strict-scored Qwen3.5 campaign data handoff for the site build (web/build_data.py)",
            "scorer": "localbench cli/src/localbench/_scoring.py (strict gate + termination/conditional decomposition)",
            "scorer_commit": commit,
            "runs": list(FILES.values()),
            "item_counts": {"mmlu_pro": 400, "ifbench": 294},
            "expected_strict": summary,
            "note": "raw_accuracy IS strict (answer-pass finish_reason==length counted incorrect). "
                    "Legacy composites (pre-strict-gate ifbench) are SUPERSEDED: "
                    "0.8b 17.8->14.2, 2b 37.8->32.3, 4b 59.9->56.4, 9b 69.1->66.5.",
        }
        (RUNS / "strict_handoff_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("  WROTE strict_handoff_manifest.json")
    else:
        print("\n[DRY-RUN] nothing written. Re-run with --write to re-emit in place.")
    return summary


if __name__ == "__main__":
    main()
