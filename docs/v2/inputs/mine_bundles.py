"""Mine v1 run bundles for paired-statistics grounding of the v2 check-set design.

Read-only over C:\\Users\\Michael\\lb-rung0\\runs and C:\\Users\\Michael\\local-bench.
Writes bundle-mining-results.md into the scratchpad.
"""
from __future__ import annotations

import json
import statistics
from ast import literal_eval
from collections import Counter, defaultdict
from pathlib import Path

RUNS = Path(r"C:\Users\Michael\lb-rung0\runs")
SUITE = Path(r"C:\Users\Michael\local-bench\suite\v2")
OUT = Path(r"C:\Users\Michael\AppData\Local\Temp\claude\C--Users-Michael-OneDrive---clarityconsultive-com-ClaudeCode-Projects-local-bench\3549af26-8af4-461a-b0e2-934f18e5dd30\scratchpad\bundle-mining-results.md")

BUNDLES = {
    "base_q5km": "qwen36-27b-q5km-0411",
    "q6k": "qwen36-27b-q6k-046",
    "udq2": "qwen36-27b-udq2-045",
    "fusion": "qwopus-fusion-q5km-0413",
}
BENCHES = ["bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1"]
BCBH_UNSCOREABLE = {"bcbh-006", "bcbh-007", "bcbh-014", "bcbh-035", "bcbh-074", "bcbh-096", "bcbh-104"}

report_lines: list[str] = []
md: list[str] = []


def p(s: str = "") -> None:
    print(s)
    report_lines.append(s)


def m(s: str = "") -> None:
    md.append(s)


# ---------------------------------------------------------------- load bundles
def load_bundle(dirname: str):
    """Return dict bench -> id -> record with final correctness + timing."""
    root = RUNS / dirname
    lr = json.loads((root / "localbench-run.json").read_text(encoding="utf-8"))
    final = defaultdict(dict)  # bench -> id -> final correct (post-exec truth)
    for it in lr["items"]:
        b = it.get("bench")
        if b in BENCHES:
            final[b][it["id"]] = {
                "correct": bool(it.get("correct")),
                "error": it.get("error"),
                "finish_reason": it.get("finish_reason"),
            }
    scored = defaultdict(dict)  # bench -> id -> scored_items record (pre-exec for bcb)
    hashes = defaultdict(dict)
    for b in BENCHES:
        f = root / "benchmarks" / f"{b}.scored_items.jsonl"
        for line in f.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pay = rec["payload"]
            gt = pay.get("generated_tokens") or {}
            scored[b][rec["item_id"]] = {
                "correct": bool(pay.get("correct")),
                "error": pay.get("error"),
                "finish_reason": pay.get("finish_reason"),
                "latency_s": pay.get("latency_seconds"),
                "tok_total": gt.get("total"),
                "tok_final": gt.get("final"),
                "tok_reasoning": gt.get("reasoning"),
                "failure_kind": pay.get("failure_kind"),
            }
            hashes[b][rec["item_id"]] = rec["item_hash"]
    aggs = {}
    for b in BENCHES:
        aggs[b] = json.loads((root / "benchmarks" / f"{b}.aggregate.json").read_text(encoding="utf-8"))
    benches_final = {b: lr["benches"].get(b) for b in BENCHES}
    return {"final": final, "scored": scored, "hashes": hashes, "aggs": aggs,
            "benches_final": benches_final, "dir": dirname}


data = {k: load_bundle(v) for k, v in BUNDLES.items()}

# ------------------------------------------------- integrity / manifest checks
p("## Integrity checks")
base = data["base_q5km"]
suite_ids = {}
for b in BENCHES:
    ids = []
    fname = {"bigcodebench_hard": "bigcodebench_hard", "ifbench": "ifbench",
             "olymmath_hard": "olymmath_hard", "amo": "amo", "tc_json_v1": "tc_json_v1"}[b]
    for line in (SUITE / f"{fname}.jsonl").open(encoding="utf-8"):
        line = line.strip()
        if line:
            ids.append(json.loads(line)["id"])
    suite_ids[b] = ids

problems = []
for name, d in data.items():
    for b in BENCHES:
        sids = set(d["scored"][b])
        if sids != set(suite_ids[b]):
            problems.append(f"{name}/{b}: scored id set != suite id set "
                            f"(missing {sorted(set(suite_ids[b])-sids)[:5]}, extra {sorted(sids-set(suite_ids[b]))[:5]})")
        fids = set(d["final"][b])
        if fids != sids:
            problems.append(f"{name}/{b}: run.json items ids != scored_items ids")
        # hash agreement vs base
        if name != "base_q5km":
            for iid, h in d["hashes"][b].items():
                if base["hashes"][b].get(iid) != h:
                    problems.append(f"{name}/{b}/{iid}: item_hash differs from base")
                    break
        # scored vs final correctness agreement on non-BCB benches
        if b != "bigcodebench_hard":
            mism = [iid for iid in sids if d["scored"][b][iid]["correct"] != d["final"][b][iid]["correct"]]
            if mism:
                problems.append(f"{name}/{b}: {len(mism)} scored/final correctness mismatches e.g. {mism[:5]}")
if problems:
    for x in problems:
        p("PROBLEM: " + x)
else:
    p("- all 4 bundles: scored id sets == suite id sets; item_hashes identical across bundles;")
    p("  scored_items.correct == run.json final correct on all non-coding benches (BCB differs by design: exec verdict lands in run.json).")

# recompute accuracy vs recorded aggregates
p("")
p("## Accuracy recomputation vs recorded aggregates")
for name, d in data.items():
    row = []
    for b in BENCHES:
        ids = suite_ids[b]
        if b == "bigcodebench_hard":
            scoreable = [i for i in ids if i not in BCBH_UNSCOREABLE]
            acc = sum(d["final"][b][i]["correct"] for i in scoreable) / len(scoreable)
        else:
            acc = sum(d["final"][b][i]["correct"] for i in ids) / len(ids)
        rec = d["benches_final"][b]["raw_accuracy"]
        flag = "" if abs(acc - rec) < 1e-9 else f" MISMATCH(recorded {rec:.6f})"
        row.append(f"{b}={acc*100:.2f}%{flag}")
    p(f"- {name} ({d['dir']}): " + "; ".join(row))

# --------------------------------------------------------------- paired stats
p("")
p("## Paired per-item measures (candidate vs base q5km)")
PAIRS = ["q6k", "udq2", "fusion"]
paired_tables = {}
for b in BENCHES:
    ids = [i for i in suite_ids[b] if not (b == "bigcodebench_hard" and i in BCBH_UNSCOREABLE)]
    base_correct = {i: data["base_q5km"]["final"][b][i]["correct"] for i in ids}
    base_acc = sum(base_correct.values()) / len(ids)
    p(f"\n### {b}  (n_paired={len(ids)}, base_acc={base_acc*100:.2f}%)")
    p(f"| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |")
    p(f"|---|---|---|---|---|---|---|---|---|---|")
    m(f"\n## Paired detail: {b}")
    for cand in PAIRS:
        cd = {i: data[cand]["final"][b][i]["correct"] for i in ids}
        cand_acc = sum(cd.values()) / len(ids)
        drops = sorted(i for i in ids if base_correct[i] and not cd[i])
        leaps = sorted(i for i in ids if not base_correct[i] and cd[i])
        n = len(ids)
        delta = (cand_acc - base_acc) * 100
        dr = len(drops) / n * 100
        lr_ = len(leaps) / n * 100
        rho = dr + lr_
        p(f"| {cand} | {n} | {base_acc*100:.2f} | {cand_acc*100:.2f} | {delta:+.2f} | {len(drops)} | {dr:.2f} | {len(leaps)} | {lr_:.2f} | {rho:.2f} |")
        m(f"\n### {cand} vs base — {b}")
        m(f"- drops (base-correct -> cand-wrong), n={len(drops)}: {', '.join(drops) if drops else '(none)'}")
        m(f"- leapfrogs (base-wrong -> cand-correct), n={len(leaps)}: {', '.join(leaps) if leaps else '(none)'}")
        paired_tables[(b, cand)] = dict(n=n, base=base_acc, cand=cand_acc, drops=drops, leaps=leaps)

# ------------------------------------------------------------- floor / ceiling
p("")
p("## Degenerate items across the 4 same-profile models (base, q6k, udq2, fusion-0413)")
p("(bonsai-27b-ternary / qwen3-5-9b per-item bundles NOT FOUND anywhere under lb-rung0 or local-bench —")
p(" only static web pages exist for them; fusion-0411 excluded: answer_only_v1 profile, thinking_budget=0.)")
p("")
p("| bench | n_used | floor (all 4 wrong) | ceiling (all 4 right) | degenerate% | 1-3 models correct (informative) |")
p("|---|---|---|---|---|---|")
model_names = list(BUNDLES.keys())
floor_ids = {}
ceil_ids = {}
histograms = {}
for b in BENCHES:
    ids = [i for i in suite_ids[b] if not (b == "bigcodebench_hard" and i in BCBH_UNSCOREABLE)]
    fl, ce = [], []
    hist = Counter()
    for i in ids:
        k = sum(data[mn]["final"][b][i]["correct"] for mn in model_names)
        hist[k] += 1
        if k == 0:
            fl.append(i)
        elif k == 4:
            ce.append(i)
    floor_ids[b], ceil_ids[b] = fl, ce
    histograms[b] = hist
    deg = (len(fl) + len(ce)) / len(ids) * 100
    p(f"| {b} | {len(ids)} | {len(fl)} | {len(ce)} | {deg:.1f}% | {len(ids)-len(fl)-len(ce)} |")
p("")
p("Models-correct histogram per bench (k of 4 models correct -> item count):")
for b in BENCHES:
    h = histograms[b]
    p(f"- {b}: " + ", ".join(f"k={k}:{h.get(k,0)}" for k in range(5)))

m("\n## Degenerate item ids (across base_q5km, q6k, udq2, fusion-0413; BCB excludes the 7 sandbox-unscoreable)")
for b in BENCHES:
    m(f"\n### {b}")
    m(f"- FLOOR (0/4 correct), n={len(floor_ids[b])}: {', '.join(floor_ids[b]) if floor_ids[b] else '(none)'}")
    m(f"- CEILING (4/4 correct), n={len(ceil_ids[b])}: {', '.join(ceil_ids[b]) if ceil_ids[b] else '(none)'}")

# ------------------------------------------------------------ ifbench strata
p("")
p("## IFBench constraint-type stratification (suite/v2/ifbench.jsonl, 294 items)")
type_counter = Counter()
ncons = Counter()
item_types = {}
for line in (SUITE / "ifbench.jsonl").open(encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    tl = r["instruction_id_list"]
    item_types[r["id"]] = tl
    ncons[len(tl)] += 1
    for t in tl:
        type_counter[t] += 1
p(f"- items carry `instruction_id_list` (multi-label). Constraints per item: "
  + ", ".join(f"{k} constraint(s): {v} items" for k, v in sorted(ncons.items())))
p(f"- {len(type_counter)} distinct constraint types; type -> count (of constraint instances):")
for t, c in type_counter.most_common():
    p(f"    {t}: {c}")
# family rollup (prefix before ':')
fam = Counter()
for t, c in type_counter.items():
    fam[t.split(":")[0]] += c
p("- family rollup (prefix): " + ", ".join(f"{k}={v}" for k, v in fam.most_common()))
m("\n## IFBench per-item constraint types")
for iid in sorted(item_types):
    m(f"- {iid}: {item_types[iid]}")

# ---------------------------------------------------------------- timing base
p("")
p("## Timing / token cost (BASE run qwen36-27b-q5km-0411, from scored_items payload)")
p("| bench | n | med_total_tok | p90_total_tok | med_final_tok | p90_final_tok | med_reason_tok | p90_reason_tok | med_s | p90_s | sum_h |")
p("|---|---|---|---|---|---|---|---|---|---|---|")


def q(vals, frac):
    vals = sorted(vals)
    if not vals:
        return float("nan")
    idx = frac * (len(vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (idx - lo)


for b in BENCHES:
    recs = list(data["base_q5km"]["scored"][b].values())
    toks = [r["tok_total"] for r in recs if r["tok_total"] is not None]
    fin = [r["tok_final"] for r in recs if r["tok_final"] is not None]
    rea = [r["tok_reasoning"] for r in recs if r["tok_reasoning"] is not None]
    lat = [r["latency_s"] for r in recs if r["latency_s"] is not None]
    p(f"| {b} | {len(recs)} | {q(toks,.5):.0f} | {q(toks,.9):.0f} | {q(fin,.5):.0f} | {q(fin,.9):.0f} | "
      f"{q(rea,.5):.0f} | {q(rea,.9):.0f} | {q(lat,.5):.1f} | {q(lat,.9):.1f} | {sum(lat)/3600:.2f} |")
missing_tok = [(b, iid) for b in BENCHES for iid, r in data["base_q5km"]["scored"][b].items() if r["tok_total"] is None]
if missing_tok:
    p(f"- items missing generated_tokens in base: {missing_tok}")
err_counts = {}
for name, d in data.items():
    for b in BENCHES:
        ne = sum(1 for r in d["scored"][b].values() if r["error"])
        if ne:
            err_counts[(name, b)] = ne
p(f"- non-null payload.error counts: {err_counts if err_counts else 'none'}")
# truncation
p("- finish_reason=length counts (base): " + ", ".join(
    f"{b}:{sum(1 for r in data['base_q5km']['scored'][b].values() if r['finish_reason']=='length')}" for b in BENCHES))

# per-item timing to md for base
m("\n## Base-run per-item cost (bench, id, total_tokens, latency_s) — for cost-aware selection")
for b in BENCHES:
    m(f"\n### {b}")
    for iid in suite_ids[b]:
        r = data["base_q5km"]["scored"][b][iid]
        m(f"- {iid}: tok_total={r['tok_total']}, tok_final={r['tok_final']}, latency_s={None if r['latency_s'] is None else round(r['latency_s'],1)}")

# ------------------------------------------------------------ tc_json strata
p("")
p("## tc_json_v1 stratification fields (suite/v2/tc_json_v1.jsonl, 330 items)")
strat = Counter()
src = Counter()
ntools = Counter()
ncalls = Counter()
tc_meta = {}
for line in (SUITE / "tc_json_v1.jsonl").open(encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    strat[r["stratum"]] += 1
    src[r["source"]] += 1
    nt = len(r["tools"])
    calls = r["gold"].get("calls")
    nc = len(calls) if isinstance(calls, list) else (0 if calls is None else 1)
    ntools[nt] += 1
    ncalls[nc] += 1
    tc_meta[r["id"]] = (r["stratum"], r["source"], nt, nc)
p("- `stratum` -> count: " + ", ".join(f"{k}={v}" for k, v in strat.most_common()))
p("- `source` -> count: " + ", ".join(f"{k}={v}" for k, v in src.most_common()))
p("- tools-per-item dist: " + ", ".join(f"{k} tools:{v}" for k, v in sorted(ntools.items())))
p("- gold-calls-per-item dist: " + ", ".join(f"{k} calls:{v}" for k, v in sorted(ncalls.items())))
fk = Counter(r["failure_kind"] for r in data["base_q5km"]["scored"]["tc_json_v1"].values())
p("- base-run failure_kind dist (scored_items): " + ", ".join(f"{str(k)}={v}" for k, v in fk.most_common()))
m("\n## tc_json_v1 per-item stratum/source/tools/calls")
for iid in suite_ids["tc_json_v1"]:
    s, so, nt, nc = tc_meta[iid]
    m(f"- {iid}: stratum={s}, source={so}, n_tools={nt}, n_gold_calls={nc}")

# ------------------------------------------------------------------- math
p("")
p("## olymmath_hard / amo difficulty & base accuracy distribution")
p("- suite items carry NO difficulty/category fields (only id, statement, answer, max_tokens, sampling_params).")
math_base_correct = {}
for b in ("olymmath_hard", "amo"):
    ids = suite_ids[b]
    corr = [i for i in ids if data["base_q5km"]["final"][b][i]["correct"]]
    math_base_correct[b] = corr
    p(f"- {b}: base correct {len(corr)}/{len(ids)} ({len(corr)/len(ids)*100:.1f}%)")
tot = sum(len(v) for v in math_base_correct.values())
p(f"- combined 139 math items: base correct on {tot}/139 ({tot/139*100:.1f}%)")
p("- models-correct histograms above give the difficulty spread; per-item correctness matrix in the md file.")
m("\n## Math per-item correctness matrix (base,q6k,udq2,fusion)")
for b in ("olymmath_hard", "amo"):
    m(f"\n### {b}")
    for iid in suite_ids[b]:
        row = "".join("1" if data[mn]["final"][b][iid]["correct"] else "0" for mn in model_names)
        m(f"- {iid}: {row}")

# ----------------------------------------------------------------- write md
hdr = [
    "# Bundle mining results — v2 check-set grounding",
    "",
    "Generated 2026-08-02 from lb-rung0 v1 bundles (suite full-exec-6axis-v1, lane bounded-final-v2,",
    "exec profile generic_think_tags_8192_v1, thinking_budget 8192, max_tokens 16384).",
    "Bundles: base=qwen36-27b-q5km-0411, q6k=qwen36-27b-q6k-046, udq2=qwen36-27b-udq2-045, fusion=qwopus-fusion-q5km-0413.",
    "BCB pairing excludes the 7 pinned sandbox-unscoreable ids: " + ", ".join(sorted(BCBH_UNSCOREABLE)) + ".",
    "",
    "## Summary report (as printed)",
    "",
    "```",
    *report_lines,
    "```",
]
OUT.write_text("\n".join(hdr + md) + "\n", encoding="utf-8")
print(f"\nWROTE {OUT} ({OUT.stat().st_size} bytes)")
