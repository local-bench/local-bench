"""AppWorld agentic-axis VIABILITY probe (CPU-only, NON-LLM, no network, no GPU).

Successor to appworld_feasibility_probe.py. The feasibility probe proved the strict
one-JSON-call-per-turn protocol with max_tool_calls=11 is INFEASIBLE (gold paths need
median 34 / p90 132 underlying API calls). THIS probe gathers the evidence to choose a
VIABLE protocol among:
  (A) raise the per-turn-JSON cap,
  (B) a declarative bounded-batch JSON primitive,
  (C) bounded code-as-action (AppWorld's NATIVE world.execute(python) mode).

It answers 6 questions with hard numbers, all hand-scripted/deterministic (NO model):
  1. CODE-BLOCK budget under code-as-action: how many incremental world.execute() blocks an
     agent needs (vs the flattened api-call count). AST analysis of real gold solutions +
     an empirical "pagination-sweep + detail-loop" cluster count from api_calls.json.
  2. Multi-turn STATE PERSISTENCE: drive a real dev task in 4 successive world.execute()
     blocks (vars from block 1 used in block 3) and reach success: True.
  3. JUDGE-FREE DETERMINISM: same task solved two ways (many tiny single calls in separate
     execute()s  vs  a few code blocks) -> identical world.evaluate() verdict; show there is
     no LLM/heuristic judge in the scoring path.
  4. BOUNDED-BATCH (B) EXPRESSIVENESS: AST survey of the dev split for conditionals / joins /
     arithmetic / string-ops / regex inside the solution bodies -> can a declarative
     pagination+map primitive express the common case, or is Turing-completeness required?
  5. GAMING surface: confirm the answer is NOT derivable from public_data (lives behind the
     APIs); enumerate escape hatches reachable from world.execute() (ground_truth files,
     apis.supervisor.*, raw fs access) that the harness must sandbox.
  6. COST signal: from the code-block distribution, estimate generations (turns) + output
     tokens for a median task -> is the Qwen-ladder + gemma GPU run affordable on one 5090.

Run (WSL appworld venv + APPWORLD_ROOT set):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && python cli/tools/appworld_viability_probe.py'
"""

from __future__ import annotations

import ast
import json
import os
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(os.environ["APPWORLD_ROOT"]) / "data"

# AppWorld library helpers that COLLAPSE an entire pagination/aggregation loop into ONE
# expression. Their presence in a gold solution is the signal that the flattened api-call
# count >> the code-block count. (find_*_from_pages drives the page loop internally.)
PAGINATION_HELPERS = {"find_all_from_pages", "find_one_from_pages"}
AGG_HELPERS = {"find_all", "find_one", "set_of", "list_of", "sum_of"}
STRING_METHODS = {"split", "replace", "strip", "join", "startswith", "endswith",
                  "lower", "upper", "to_date_string", "to_month_string"}


class SolutionStats(ast.NodeVisitor):
    def __init__(self) -> None:
        self.api_call_exprs = 0          # apis.<app>.<api>(...) written in source
        self.apps_touched: set[str] = set()
        self.pagination_sweeps = 0       # find_*_from_pages(...)
        self.agg_helper_calls = 0        # find_all/set_of/sum_of/... (declarative-ish)
        self.for_loops = 0
        self.while_loops = 0
        self.if_branches = 0
        self.comprehensions = 0          # list/dict/set comps + genexps
        self.string_ops = 0
        self.arith_ops = 0
        self.regex = False
        self.dict_builds = 0             # dict(...) / dict comp / zip(...) -> join signal
        self.break_continue = 0

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute):
            inner = f.value
            if isinstance(inner.value, ast.Name) and inner.value.id == "apis":
                self.api_call_exprs += 1
                self.apps_touched.add(inner.attr)
        if isinstance(f, ast.Name):
            if f.id in PAGINATION_HELPERS:
                self.pagination_sweeps += 1
            if f.id in AGG_HELPERS:
                self.agg_helper_calls += 1
            if f.id in ("dict", "zip"):
                self.dict_builds += 1
            if f.id == "round":
                self.arith_ops += 1
        if isinstance(f, ast.Attribute):
            name = f.attr
            if name in STRING_METHODS:
                self.string_ops += 1
            if (name in ("compile", "search", "match", "findall", "sub")
                    and isinstance(f.value, ast.Name) and f.value.id == "re"):
                self.regex = True
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.for_loops += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.while_loops += 1
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.if_branches += 1
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                                ast.Mod, ast.Pow)):
            self.arith_ops += 1
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.comprehensions += 1
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.comprehensions += 1
        self.dict_builds += 1
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.comprehensions += 1
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.comprehensions += 1
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.string_ops += 1
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        self.break_continue += 1

    def visit_Continue(self, node: ast.Continue) -> None:
        self.break_continue += 1


def _solution_body(tree: ast.Module) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_solution":
            return node
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "solution":
            return node
    return None


def analyze_solution(tid: str) -> dict[str, Any] | None:
    sol = ROOT / "tasks" / tid / "ground_truth" / "solution.py"
    if not sol.exists():
        return None
    tree = ast.parse(sol.read_text())
    body = _solution_body(tree)
    if body is None:
        return None
    st = SolutionStats()
    for stmt in body.body:
        st.visit(stmt)

    # ---- INCREMENTAL CODE-BLOCK MODEL (transparent, defensible) ----
    # An incremental agent interleaves exploration with action. We model world.execute()
    # blocks as:
    #   UPPER bound (every phase its own block, agent never fuses):
    #     1 (auth+peek) + pagination_sweeps + for_loops + 1 (compute+submit)
    #   FUSED lower bound (capable agent fuses read into one block, act into one):
    #     1 (auth) + (1 if any sweep) + (1 if any loop) + 1 (finalize)
    sweeps = st.pagination_sweeps
    loops = st.for_loops
    est_blocks_upper = 1 + sweeps + loops + 1
    est_blocks_fused = 1 + (1 if sweeps else 0) + (1 if loops else 0) + 1

    needs_turing = bool(st.comprehensions or st.regex or st.string_ops or st.arith_ops
                        or st.if_branches or st.dict_builds or st.while_loops
                        or st.break_continue)
    return {
        "tid": tid,
        "api_call_exprs": st.api_call_exprs,
        "apps": sorted(st.apps_touched),
        "pagination_sweeps": sweeps,
        "agg_helpers": st.agg_helper_calls,
        "for_loops": loops,
        "if_branches": st.if_branches,
        "comprehensions": st.comprehensions,
        "string_ops": st.string_ops,
        "arith_ops": st.arith_ops,
        "regex": st.regex,
        "dict_builds": st.dict_builds,
        "est_blocks_upper": est_blocks_upper,
        "est_blocks_fused": est_blocks_fused,
        "needs_turing": needs_turing,
    }


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def survey_split(split: str) -> list[dict[str, Any]]:
    ids = (ROOT / "datasets" / f"{split}.txt").read_text().split()
    recs = []
    for tid in ids:
        r = analyze_solution(tid)
        if r:
            mp = ROOT / "tasks" / tid / "ground_truth" / "metadata.json"
            m = json.loads(mp.read_text()) if mp.exists() else {}
            r["flat_api_calls"] = m.get("num_api_calls")
            r["difficulty"] = m.get("difficulty")
            recs.append(r)
    return recs


def main() -> None:
    print("=" * 92)
    print("APPWORLD AGENTIC VIABILITY PROBE  (CPU-only, NON-LLM, no network, no GPU)")
    print("=" * 92)

    # ---- POINT 1 + 4 : AST survey of the whole DEV split ----
    recs = survey_split("dev")
    print(f"\n### [POINT 1+4] AST survey of DEV gold solutions (n={len(recs)})")
    print(f"{'tid':<12} {'diff':<4} {'flatAPI':<7} {'wrtAPI':<6} {'swp':<3} "
          f"{'lp':<3} {'if':<3} {'cmp':<3} {'str':<3} {'ari':<3} {'rgx':<3} "
          f"{'blkUP':<5} {'blkFZ':<5} {'turing':<6}")
    for r in sorted(recs, key=lambda x: (x["difficulty"] or 0, x["flat_api_calls"] or 0)):
        print(f"{r['tid']:<12} {str(r['difficulty']):<4} {str(r['flat_api_calls']):<7} "
              f"{r['api_call_exprs']:<6} {r['pagination_sweeps']:<3} {r['for_loops']:<3} "
              f"{r['if_branches']:<3} {r['comprehensions']:<3} {r['string_ops']:<3} "
              f"{r['arith_ops']:<3} {('Y' if r['regex'] else '.'):<3} "
              f"{r['est_blocks_upper']:<5} {r['est_blocks_fused']:<5} "
              f"{('YES' if r['needs_turing'] else 'no'):<6}")

    flat = sorted(r["flat_api_calls"] for r in recs if r["flat_api_calls"] is not None)
    blk_up = sorted(r["est_blocks_upper"] for r in recs)
    blk_fz = sorted(r["est_blocks_fused"] for r in recs)
    wrote = sorted(r["api_call_exprs"] for r in recs)

    def stat_line(name: str, vals: list[float]) -> None:
        print(f"  {name:<26} min={min(vals):>3}  median={statistics.median(vals):>5.1f}  "
              f"p90={_pct(vals, 0.9):>5.1f}  max={max(vals):>3}  mean={statistics.mean(vals):>4.1f}")

    print("\n### [POINT 1] DISTRIBUTIONS over DEV split (the headline numbers)")
    stat_line("flat api-calls (gold)", flat)
    stat_line("WRITTEN api-call exprs", wrote)
    stat_line("EST code-blocks (UPPER)", blk_up)
    stat_line("EST code-blocks (FUSED)", blk_fz)
    for cap in (5, 8, 11, 15, 20):
        fit_up = sum(1 for v in blk_up if v <= cap)
        fit_fz = sum(1 for v in blk_fz if v <= cap)
        print(f"  code-blocks <= {cap:<2}:  UPPER {fit_up}/{len(blk_up)} "
              f"({100 * fit_up // len(blk_up)}%)   FUSED {fit_fz}/{len(blk_fz)} "
              f"({100 * fit_fz // len(blk_fz)}%)")

    turing = sum(1 for r in recs if r["needs_turing"])
    print(f"\n### [POINT 4] BOUNDED-BATCH (B) EXPRESSIVENESS over DEV (n={len(recs)})")
    print(f"  solutions needing Turing-complete logic: {turing}/{len(recs)} "
          f"({100 * turing // len(recs)}%)")
    print(f"    with if/branch     : {sum(1 for r in recs if r['if_branches'])}")
    print(f"    with string parsing: {sum(1 for r in recs if r['string_ops'])}")
    print(f"    with arithmetic    : {sum(1 for r in recs if r['arith_ops'])}")
    print(f"    with comprehension : {sum(1 for r in recs if r['comprehensions'])}")
    print(f"    with dict/zip join : {sum(1 for r in recs if r['dict_builds'])}")
    print(f"    with regex         : {sum(1 for r in recs if r['regex'])}")
    pure_paginate = sum(1 for r in recs if not r["needs_turing"]
                        and r["pagination_sweeps"] and not r["for_loops"])
    simple_map = sum(1 for r in recs if not r["needs_turing"])
    print(f"  expressible by PURE pagination+aggregate (no loop/branch): {pure_paginate}/{len(recs)}")
    print(f"  expressible by pagination+MAP-over-ids (loops ok, no branch/parse): "
          f"{simple_map}/{len(recs)}")

    # ---- POINT 1 cross-check: cluster flattened api_calls.json of heavy tasks ----
    print("\n### [POINT 1 cross-check] Clustering flattened api_calls.json of heavy tasks")
    for tid in ("50e1ac9_1", "57c3486_1", "d4e9306_1"):
        ap = ROOT / "tasks" / tid / "ground_truth" / "api_calls.json"
        if not ap.exists():
            continue
        calls = json.loads(ap.read_text())
        urls = [c.get("url", "") for c in calls]
        runs: list[list[Any]] = []
        for u in urls:
            base = u.split("?")[0]
            parts = base.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                base = "/".join(parts[:-1]) + "/{id}"
            if runs and runs[-1][0] == base:
                runs[-1][1] += 1
            else:
                runs.append([base, 1])
        sweeps = sum(1 for _, n in runs if n >= 3)
        print(f"  {tid}: {len(calls)} flat calls -> {len(runs)} endpoint-runs "
              f"({sweeps} are loops of >=3). Top runs:")
        for base, n in sorted(runs, key=lambda x: -x[1])[:6]:
            print(f"       {n:>4}x  {base}")

    # ---- POINTS 2 + 3 : live AppWorld ----
    print("\n### [POINT 2+3] Live AppWorld: incremental code-as-action + two-style determinism")
    try:
        from appworld import AppWorld
    except Exception as exc:  # noqa: BLE001
        print(f"  [SKIP] could not import appworld ({exc}); run inside the WSL appworld venv.")
        _print_footer()
        return

    task_id = "fac291d_1"   # diff-2, 34 flat calls: 3 paginated libraries + a union count.
    print(f"\n  -- STYLE C (code-as-action), task {task_id}, 4 incremental blocks --")
    with AppWorld(task_id=task_id, experiment_name="lb_viab_codeblocks") as world:
        instr = world.task.instruction
        print(f"     instruction: {instr[:96]}...")
        # BLOCK 1 (auth + peek): the AGENT-reachable auth path -- read the user's own account
        # passwords from the supervisor, log in, then peek page 1 to learn the schema. NOTE:
        # `main_user` / `apis.spotify.access_token_from` are gold-solution-only conveniences and
        # are NOT in the agent's execute() namespace; the agent must use supervisor+login.
        b1 = world.execute(
            "prof = apis.supervisor.show_profile()\n"
            "pwds = apis.supervisor.show_account_passwords()\n"
            "spw = next(p['password'] for p in pwds if p['account_name'] == 'spotify')\n"
            "token = apis.spotify.login(username=prof['email'], password=spw)['access_token']\n"
            "page0 = apis.spotify.show_song_library(access_token=token, page_index=0)\n"
            "print(type(page0).__name__, len(page0), (page0[0] if page0 else None))"
        )
        print(f"     [block1] {b1.strip()[:120]}")
        b2 = world.execute(
            "song_ids = set()\n"
            "pi = 0\n"
            "while True:\n"
            "    pg = apis.spotify.show_song_library(access_token=token, page_index=pi)\n"
            "    if not pg: break\n"
            "    song_ids |= {s['song_id'] for s in pg}\n"
            "    pi += 1\n"
            "print('after song lib:', len(song_ids))"
        )
        print(f"     [block2] {b2.strip()[:120]}")
        b3 = world.execute(
            "pi = 0\n"
            "while True:\n"
            "    pg = apis.spotify.show_album_library(access_token=token, page_index=pi)\n"
            "    if not pg: break\n"
            "    for al in pg: song_ids |= set(al['song_ids'])\n"
            "    pi += 1\n"
            "pi = 0\n"
            "while True:\n"
            "    pg = apis.spotify.show_playlist_library(access_token=token, page_index=pi)\n"
            "    if not pg: break\n"
            "    for pl in pg: song_ids |= set(pl['song_ids'])\n"
            "    pi += 1\n"
            "answer = len(song_ids)\n"
            "print('final unique:', answer)"
        )
        print(f"     [block3] {b3.strip()[:120]}")
        b4 = world.execute("apis.supervisor.complete_task(answer=answer, status='success')\n"
                           "print('submitted')")
        print(f"     [block4] {b4.strip()[:120]}")
        ev_code = world.evaluate().to_dict()
        print(f"     >> CODE-AS-ACTION blocks used: 4 (+evaluate). success={ev_code['success']}  "
              f"keys={list(ev_code.keys())}")

    print(f"\n  -- STYLE A (one call per execute, JSON analogue), task {task_id} --")
    with AppWorld(task_id=task_id, experiment_name="lb_viab_singlecalls") as world2:
        n_calls = 0
        # Auth via the agent-reachable supervisor+login path, ONE apis.* call per execute().
        prof = ast.literal_eval(
            world2.execute("print(apis.supervisor.show_profile())").strip())
        n_calls += 1
        pwds = ast.literal_eval(
            world2.execute("print(apis.supervisor.show_account_passwords())").strip())
        n_calls += 1
        spw = next(p["password"] for p in pwds if p["account_name"] == "spotify")
        tok_obj = ast.literal_eval(world2.execute(
            f"print(apis.spotify.login(username={prof['email']!r}, password={spw!r}))").strip())
        n_calls += 1
        token = tok_obj["access_token"]
        song_ids: set = set()
        for app_api, take in [("show_song_library", "self"),
                              ("show_album_library", "nested"),
                              ("show_playlist_library", "nested")]:
            pi = 0
            while True:
                prog = (f"print(apis.spotify.{app_api}"
                        f"(access_token={token!r}, page_index={pi}))")
                out = world2.execute(prog)
                n_calls += 1
                s = out.strip()
                try:
                    page = ast.literal_eval(s)
                except Exception:  # noqa: BLE001
                    try:
                        page = json.loads(s)
                    except Exception:  # noqa: BLE001
                        print(f"     [STYLE-A parse-stop] {app_api} p{pi}: {s[:80]}")
                        page = []
                if not page:
                    break
                if take == "self":
                    song_ids |= {s["song_id"] for s in page}
                else:
                    for row in page:
                        song_ids |= set(row["song_ids"])
                pi += 1
        answer2 = len(song_ids)
        world2.execute(f"apis.supervisor.complete_task(answer={answer2}, status='success')")
        ev_single = world2.evaluate().to_dict()
        print(f"     >> SINGLE-CALL tool calls used: {n_calls}. "
              f"success={ev_single['success']}  answer={answer2}")

    print("\n### [POINT 3] JUDGE-FREE DETERMINISM verdict")
    same = (ev_code["success"] == ev_single["success"])
    print(f"  code-as-action success={ev_code['success']}  |  single-call success="
          f"{ev_single['success']}  ->  IDENTICAL verdict: {same}")
    print(f"  evaluate().to_dict() is a fixed assertion set (keys: {list(ev_code.keys())}); "
          "no model/LLM/heuristic judge in the path.")
    print("  passing requirements (code-as-action run):")
    for p in ev_code.get("passes", [])[:6]:
        print(f"       PASS: {p.get('requirement')}")

    # ---- POINT 5 : gaming surface ----
    print("\n### [POINT 5] GAMING SURFACE probe (what world.execute() can reach)")
    gt = ROOT / "tasks" / "50e1ac9_1" / "ground_truth"
    with AppWorld(task_id="50e1ac9_1", experiment_name="lb_viab_gaming") as w:
        probes = {
            "open() ground_truth answer.json directly":
                f"print(open({str(gt / 'answer.json')!r}).read())",
            "import os; os.listdir(ground_truth)":
                f"import os; print(os.listdir({str(gt)!r}))",
            "apis.supervisor.show_private_data attr?":
                "print(getattr(apis.supervisor, 'show_private_data', 'ABSENT'))",
            "access apis.api_docs (legit on-demand docs)":
                "print(type(apis.api_docs).__name__)",
        }
        for label, code in probes.items():
            try:
                out = w.execute(code)
                verdict = out.strip()[:88]
                tag = "REACHABLE" if ("Error" not in out and "Traceback" not in out) else "blocked?"
            except Exception as e:  # noqa: BLE001
                verdict = f"{type(e).__name__}: {e}"[:88]
                tag = "blocked(raise)"
            print(f"  [{tag:<14}] {label}")
            print(f"       -> {verdict}")

    pub = json.loads((gt / "public_data.json").read_text())
    ans = json.loads((gt / "answer.json").read_text())
    priv_raw = (gt / "private_data.json").read_text().strip()
    print(f"\n  public_data given to agent: {pub}")
    print(f"  gold answer (NOT in public_data): {ans!r}")
    print(f"  private_data.json: {priv_raw!r}  -> answer lives behind the authenticated APIs only.")

    _print_footer()


def _print_footer() -> None:
    print("\n" + "=" * 92)
    print("VIABILITY PROBE COMPLETE -- see appworld-viability-research.md for the recommendation.")
    print("=" * 92)


if __name__ == "__main__":
    main()
