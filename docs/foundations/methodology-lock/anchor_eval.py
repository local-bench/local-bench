"""Off-family anchor validation — reproducible 4-status eval (local-bench).

Companion to ANCHOR-VALIDATION-PREREG-2026-06-21.md. Re-scores the 4 off-family anchors +
the Qwen3.5 ladder through localbench's OWN scorer (so numbers match the production pipeline),
recovering two deterministic transcript artifacts losslessly on CPU (no GPU re-runs):

  * Granite emits LaTeX \\boxed{} answers   -> recovered by the committed additive MCQ extractor.
  * R1-Distill transcripts are byte-level BPE -> recovered by the GPT-2 byte decoder below
    (Ġ=space, Ċ=newline; proven lossless, bad_chars=0). R1's IFBench is also re-scored on the
    decoded text (the corruption spuriously PASSED count/format constraints, net +45 items).

Self-verifies on every run: asserts the re-score reproduces known-good numbers (Nemotron's
printed run + the §6.1 locked Qwen strict rungs) before trusting recovered values. Emits
anchor-validation-results.json for the docs + the web pipeline.

Run:  <repo>/cli/.venv/Scripts/python.exe docs/foundations/methodology-lock/anchor_eval.py
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(REPO / "cli" / "src"))
from localbench._suite import render_benches, read_json_object, _item_id
from localbench._scoring import _score_response_detail
from localbench.scorers.mcq import score_mcq_detailed

RUNS = REPO / "cli" / "runs"
SUITE = REPO / "suite" / "v1"
OUT_JSON = Path(__file__).resolve().parent / "anchor-validation-results.json"
BENCHES = ("mmlu_pro", "ifbench")


# ---- lossless GPT-2 byte-level BPE decoder (R1-Distill transcripts) ----
def _bytes_to_unicode() -> dict[int, str]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))

_U2B = {u: b for b, u in _bytes_to_unicode().items()}

def decode_bpe(s: str) -> str:
    out = bytearray()
    for ch in s:
        if ch in _U2B:
            out.append(_U2B[ch])
        elif ord(ch) < 256:
            out.append(ord(ch))
    return out.decode("utf-8", errors="replace")


MODELS = {
    "granite-2b":  ("anchor-granite-3.3-2b.json", False, "anchor"),
    "granite-8b":  ("anchor-granite-3.3-8b.json", False, "anchor"),
    "nemotron-4b": ("anchor-nemotron-nano-4b.json", False, "anchor"),
    "r1-8b":       ("anchor-r1-distill-llama-8b.json", True, "anchor"),
    "qwen-0.8b":   ("campaign-qwen3.5-0.8b.json", False, "qwen"),
    "qwen-2b":     ("campaign-qwen3.5-2b.json", False, "qwen"),
    "qwen-4b":     ("campaign-qwen3.5-4b.json", False, "qwen"),
    "qwen-9b":     ("campaign-qwen3.5-9b.json", False, "qwen"),
}
ANCHORS = ["granite-2b", "granite-8b", "nemotron-4b", "r1-8b"]
QWEN = ["qwen-0.8b", "qwen-2b", "qwen-4b", "qwen-9b"]

# §6.1 pre-registered brackets, as [lower_rung, upper_rung] Qwen rung labels (strict-score space).
BRACKETS = {
    "granite-2b":  {"mmlu_pro": ("qwen-0.8b", "qwen-2b"), "ifbench": ("qwen-0.8b", "qwen-4b")},
    "granite-8b":  {"mmlu_pro": ("qwen-0.8b", "qwen-4b"), "ifbench": ("qwen-2b", "qwen-9b")},
    "nemotron-4b": {"mmlu_pro": ("qwen-2b", "qwen-4b"),   "ifbench": ("qwen-4b", "qwen-9b")},
    "r1-8b":       {"mmlu_pro": ("qwen-4b", "qwen-9b"),   "ifbench": ("qwen-4b", "qwen-9b")},
}


def load_suite():
    benches = render_benches("mmlu_pro,ifbench", "standard", None, SUITE, read_json_object(SUITE / "suite.json"), [])
    src = {(b.name, _item_id(si)): si for b in benches for si in b.source_items}
    baseline = {b.name: b.baseline for b in benches}
    return src, baseline


def score_model(fn: str, decode: bool, src) -> dict[str, dict[str, tuple[bool, bool]]]:
    """Return per-bench {id: (correct_strict, terminated)}."""
    j = json.loads((RUNS / fn).read_text(encoding="utf-8"))
    out = {b: {} for b in BENCHES}
    for it in j["items"]:
        bench = it.get("bench")
        if bench not in out:
            continue
        si = src.get((bench, str(it["id"])))
        if si is None:
            continue
        rt = it.get("response_text")
        if decode and rt:
            rt = decode_bpe(rt)
        fr, err = it.get("finish_reason"), it.get("error")
        detail = _score_response_detail(bench, si, rt, err, fr)
        terminated = bool(err is None and fr != "length")
        correct = bool(detail["correct"] and fr != "length")
        out[bench][str(it["id"])] = (correct, terminated)
    return out


def arrays(d, bench):
    corr = np.array([v[0] for v in d[bench].values()])
    term = np.array([v[1] for v in d[bench].values()])
    return corr, term


def point(corr, term, stat):
    if stat == "S":
        return float(corr.mean() * 100)
    den = term.sum()
    return float(corr.sum() / den * 100) if den else 0.0


def boot_ci(corr, term, stat, B=4000, seed=20260621):
    rng = np.random.default_rng(seed)
    n = len(corr)
    idx = rng.integers(0, n, size=(B, n))
    c = corr[idx]
    if stat == "S":
        vals = c.mean(axis=1) * 100
    else:
        t = term[idx]
        den = t.sum(axis=1)
        vals = np.where(den > 0, (c & t).sum(axis=1) / np.maximum(den, 1) * 100, 0.0)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def main():
    src, baseline = load_suite()
    scored = {label: score_model(fn, dec, src) for label, (fn, dec, _kind) in MODELS.items()}

    S = {m: {b: point(*arrays(scored[m], b), "S") for b in BENCHES} for m in MODELS}
    T = {m: {b: float(arrays(scored[m], b)[1].mean() * 100) for b in BENCHES} for m in MODELS}
    C = {m: {b: point(*arrays(scored[m], b), "C") for b in BENCHES} for m in MODELS}

    # --- self-verification against known-good (fail loudly on drift) ---
    def close(a, b, tol=0.6):
        return abs(a - b) <= tol
    assert close(S["nemotron-4b"]["mmlu_pro"], 52.5) and close(T["nemotron-4b"]["mmlu_pro"], 94.8) and close(C["nemotron-4b"]["mmlu_pro"], 55.4), "nemotron known-good drift"
    for m, exp in zip(QWEN, [24.8, 51.5, 73.0, 78.5]):
        assert close(S[m]["mmlu_pro"], exp), f"{m} mmlu strict rung drift: {S[m]['mmlu_pro']} != {exp}"
    for m, exp in zip(QWEN, [12.9, 19.0, 43.2, 57.1]):
        assert close(S[m]["ifbench"], exp), f"{m} ifbench strict rung drift: {S[m]['ifbench']} != {exp}"
    assert score_mcq_detailed("x \\boxed{D}", "D", 10)["extracted"] == "D", "boxed extractor missing"
    print("[self-verify] OK: re-score reproduces Nemotron printed run + §6.1 Qwen strict rungs + \\boxed extractor")

    min_qwen_T = {b: min(T[q][b] for q in QWEN) for b in BENCHES}

    rows = []
    for a in ANCHORS:
        for b in BENCHES:
            corr, term = arrays(scored[a], b)
            slo, shi = boot_ci(corr, term, "S")
            lo_r, hi_r = BRACKETS[a][b]
            lo, hi = S[lo_r][b], S[hi_r][b]
            miss = round(lo - S[a][b], 1) if S[a][b] < lo else 0.0
            ci_survives = shi < lo
            rows.append({
                "anchor": a, "axis": b, "S": round(S[a][b], 1), "T": round(T[a][b], 1), "C": round(C[a][b], 1),
                "S_ci95": [round(slo, 1), round(shi, 1)], "bracket_strict": [round(lo, 1), round(hi, 1)],
                "bracket_rungs": [lo_r, hi_r], "miss_below_lower": miss,
                "ci_survives_miss": bool(ci_survives), "health_ok": bool(T[a][b] >= min_qwen_T[b] - 10),
            })

    # difficulty audit: Qwen-4b strict-correct rate on each anchor's terminated vs non-terminated mmlu items
    q4 = scored["qwen-4b"]["mmlu_pro"]
    audit = []
    for a in ANCHORS:
        d = scored[a]["mmlu_pro"]
        term_ids = [i for i, v in d.items() if v[1]]
        non_ids = [i for i, v in d.items() if not v[1]]
        def rate(ids):
            vals = [q4[i][0] for i in ids if i in q4]
            return (round(sum(vals) / len(vals) * 100, 1) if vals else None), len(vals)
        tr, tn = rate(term_ids)
        nr, nn = rate(non_ids)
        audit.append({"anchor": a, "qwen4b_on_terminated_pct": tr, "n_terminated": tn,
                      "qwen4b_on_nonterminated_pct": nr, "n_nonterminated": nn})

    results = {
        "generated_for": "ANCHOR-VALIDATION-PREREG-2026-06-21.md",
        "lane": "capped-thinking (greedy temp-0, s1 two-pass, think<=8192)",
        "metrics": {m: {b: {"S": round(S[m][b], 1), "T": round(T[m][b], 1), "C": round(C[m][b], 1)} for b in BENCHES} for m in MODELS},
        "placement": rows,
        "termination_asymmetry": {b: {m: round(T[m][b], 1) for m in MODELS} for b in BENCHES},
        "difficulty_audit_mmlu": audit,
        "notes": "S=strict (leaderboard). T=termination. C=conditional. Anchors recovered on CPU "
                 "(Granite \\boxed extractor; R1 byte-BPE decode). Self-verified vs known-good.",
    }
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n{'anchor':12s} {'axis':9s} {'S':>5s} {'S_CI95':>13s} {'T':>5s} {'C':>5s} {'bracket':>11s} {'miss':>5s} {'CI?':>4s}")
    print("-" * 80)
    for r in rows:
        ci = "yes" if (r["ci_survives_miss"] and r["miss_below_lower"]) else ("-" if not r["miss_below_lower"] else "no")
        blo, bhi = r["bracket_strict"]
        bracket = f"{blo:.0f}-{bhi:.0f}"
        slo, shi = r["S_ci95"]
        print(f"{r['anchor']:12s} {r['axis']:9s} {r['S']:5.1f} [{slo:5.1f},{shi:5.1f}] "
              f"{r['T']:5.1f} {r['C']:5.1f} {bracket:>11s} {r['miss_below_lower']:5.1f} {ci:>4s}")
    print(f"\n[out] {OUT_JSON}")


if __name__ == "__main__":
    main()
