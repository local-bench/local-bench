"""Scripted NON-LLM agent: solve real AppWorld dev tasks end-to-end THROUGH the sandbox.

This is ACCEPTANCE GATE #2 for the AppWorld-C sandbox build. It proves the ``apis`` proxy +
process isolation preserve legitimate task-solving even though every canary escape is blocked:
hand-written deterministic code (NO LLM) drives incremental code blocks via ``sb.run_block`` and
then the harness-owned ``sb.finalize`` (complete_task + evaluate), reaching ``success: True``.

The solve paths are the agent-reachable ones validated by ``appworld_viability_probe.py`` (auth via
``apis.supervisor.show_account_passwords`` + ``apis.spotify.login``; NO gold-only conveniences like
``main_user`` / ``access_token_from`` — those are not in the agent namespace anyway).

Run (WSL appworld venv + bwrap):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && export APPWORLD_ROOT=/home/michael/appworld-data \
    PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 && export PATH="$HOME/.local/bin:$PATH" \
    && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_scripted_solve_sandboxed.py --json'
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench.scoring.agentic_exec.sandbox import (  # noqa: E402
    AppWorldSandbox,
    SandboxConfig,
    Verdict,
    resolve_bwrap,
)

# ---------------------------------------------------------------------------------------------
# Hand-written incremental "agent programs" — one list of code blocks per task. The final block
# binds a variable named `answer`; the solver reads it back out via a tiny echo block, then calls
# sb.finalize(answer). Everything here is deterministic; there is NO model in the loop.
# ---------------------------------------------------------------------------------------------

# fac291d_1 (diff-2): count of UNIQUE songs across the user's song/album/playlist libraries.
_FAC_BLOCKS = [
    # block 1: auth (supervisor password -> spotify login) and peek page 0 schema.
    (
        "prof = apis.supervisor.show_profile()\n"
        "pwds = apis.supervisor.show_account_passwords()\n"
        "spw = next(p['password'] for p in pwds if p['account_name'] == 'spotify')\n"
        "token = apis.spotify.login(username=prof['email'], password=spw)['access_token']\n"
        "print('auth ok; token len', len(token))\n"
    ),
    # block 2: sweep the song library (direct song_ids).
    (
        "song_ids = set()\n"
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_song_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    song_ids |= {s['song_id'] for s in pg}\n"
        "    pi += 1\n"
        "print('after song lib', len(song_ids))\n"
    ),
    # block 3: sweep album + playlist libraries (nested song_ids), compute the answer.
    (
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_album_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for al in pg:\n"
        "        song_ids |= set(al['song_ids'])\n"
        "    pi += 1\n"
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_playlist_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for pl in pg:\n"
        "        song_ids |= set(pl['song_ids'])\n"
        "    pi += 1\n"
        "answer = len(song_ids)\n"
        "print('final unique', answer)\n"
    ),
]

# 50e1ac9_1 (the canary primary): "top K most played <genre> song titles across song, album and
# playlist libraries." Gold answer is a CSV string of titles. We reproduce the documented gold
# path EXACTLY (per ground_truth/solution.py): build {title: play_count} over songs in all three
# libraries filtered to the genre, sort by play_count desc, take top_k, join with ", ". The genre
# and K are read from the task INSTRUCTION (available to any agent via show_active_task) — NOT from
# the gold files (the jail cannot read those; that is the whole point).
_SPOTIFY_BLOCKS_50E = [
    # block 1: auth + read the instruction; parse genre + top_k from it (deterministic).
    (
        "prof = apis.supervisor.show_profile()\n"
        "pwds = apis.supervisor.show_account_passwords()\n"
        "spw = next(p['password'] for p in pwds if p['account_name'] == 'spotify')\n"
        "token = apis.spotify.login(username=prof['email'], password=spw)['access_token']\n"
        "task = apis.supervisor.show_active_task()\n"
        "instr = task['instruction'].lower()\n"
        "import re as _re\n"
        "m = _re.search(r'top (\\d+)', instr)\n"
        "top_k = int(m.group(1)) if m else 4\n"
        "genre = 'R&B' if 'r&b' in instr else None\n"
        "print('auth ok; top_k', top_k, 'genre', genre)\n"
    ),
    # block 2: collect candidate song_ids from all three libraries.
    (
        "song_ids = []\n"
        "seen = set()\n"
        "def _add(sid):\n"
        "    if sid not in seen:\n"
        "        seen.add(sid); song_ids.append(sid)\n"
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_song_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for s in pg:\n"
        "        _add(s['song_id'])\n"
        "    pi += 1\n"
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_album_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for al in pg:\n"
        "        info = apis.spotify.show_album(album_id=al['album_id'])\n"
        "        for so in info['songs']:\n"
        "            _add(so['id'])\n"
        "    pi += 1\n"
        "pi = 0\n"
        "while True:\n"
        "    pg = apis.spotify.show_playlist_library(access_token=token, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for pl in pg:\n"
        "        info = apis.spotify.show_playlist(access_token=token, playlist_id=pl['playlist_id'])\n"
        "        for so in info['songs']:\n"
        "            _add(so['id'])\n"
        "    pi += 1\n"
        "print('candidate songs', len(song_ids))\n"
    ),
    # block 3: per-song genre/play_count lookup, filter, sort desc, take top_k, join titles.
    (
        "title_to_count = {}\n"
        "for sid in song_ids:\n"
        "    s = apis.spotify.show_song(song_id=sid)\n"
        "    if s.get('genre') == genre:\n"
        "        title_to_count[s['title']] = s['play_count']\n"
        "ranked = sorted(title_to_count.items(), key=lambda x: x[1], reverse=True)[:top_k]\n"
        "answer = ', '.join(t for t, _ in ranked)\n"
        "print('built answer:', answer)\n"
    ),
]


def _echo_answer(sb: AppWorldSandbox) -> object:
    """Read the `answer` variable back out of the persistent namespace as JSON."""
    obs = sb.run_block("import json as _j\nprint(_j.dumps(answer))")
    if obs.error:
        raise RuntimeError(f"could not read answer var: {obs.error}")
    return json.loads(obs.stdout.strip())


def solve_fac291d(sb: AppWorldSandbox) -> tuple[object, Verdict]:
    for code in _FAC_BLOCKS:
        obs = sb.run_block(code)
        if obs.error:
            raise RuntimeError(f"fac291d block failed: {obs.error}\nstdout={obs.stdout}")
    answer = _echo_answer(sb)
    return answer, sb.finalize(answer)


def solve_50e1ac9(sb: AppWorldSandbox) -> tuple[object, Verdict]:
    # Follows the gold path exactly (genre/top_k parsed from the instruction, not the gold files).
    for code in _SPOTIFY_BLOCKS_50E:
        obs = sb.run_block(code)
        if obs.error:
            raise RuntimeError(f"50e1ac9 block failed: {obs.error}\nstdout={obs.stdout}")
    answer = _echo_answer(sb)
    return answer, sb.finalize(answer)


def _run_one(task_id: str, solver) -> dict[str, object]:
    cfg = SandboxConfig(experiment_name=f"lb_scripted_{task_id}")
    with AppWorldSandbox(task_id, cfg) as sb:
        answer, verdict = solver(sb)
    return {
        "task_id": task_id,
        "success": verdict.success,
        "collateral_damage": verdict.collateral_damage,
        "num_passes": len(verdict.passes),
        "num_failures": len(verdict.failures),
        "failures": list(verdict.failures)[:6],
        "answer_preview": (str(answer)[:80] + ("..." if len(str(answer)) > 80 else "")),
    }


def main(emit_json: bool) -> int:
    print("=" * 100)
    print("SCRIPTED NON-LLM SOLVE — THROUGH THE SANDBOX (acceptance gate #2)")
    print("=" * 100)
    if not resolve_bwrap():
        print("[FATAL] bwrap not found; cannot run the sandboxed solve.")
        return 2
    print(f"APPWORLD_ROOT : {os.environ.get('APPWORLD_ROOT','<unset>')}")

    tasks = [
        ("fac291d_1", solve_fac291d),
        ("50e1ac9_1", solve_50e1ac9),
    ]
    rows: list[dict[str, object]] = []
    for tid, solver in tasks:
        print(f"\n--- solving {tid} through the sandbox ---")
        try:
            row = _run_one(tid, solver)
        except Exception as exc:  # noqa: BLE001
            row = {"task_id": tid, "success": False, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        ok = row.get("success")
        print(f"    success={ok}  passes={row.get('num_passes')}  failures={row.get('num_failures')}"
              f"  collateral={row.get('collateral_damage')}")
        if not ok and row.get("failures"):
            for f in row["failures"]:  # type: ignore[index]
                print(f"      FAIL: {f}")
        if row.get("error"):
            print(f"      ERROR: {row['error']}")

    n_ok = sum(1 for r in rows if r.get("success"))
    print("\n" + "=" * 100)
    print(f"SCRIPTED SOLVE RESULT: {n_ok}/{len(rows)} tasks reached success: True "
          f"(gate requires >= 2)")
    print("=" * 100)
    if emit_json:
        print("\n--- JSON ---")
        print(json.dumps(rows, indent=2))
    return 0 if n_ok >= 2 else 1


if __name__ == "__main__":
    _rc = main(emit_json=("--json" in sys.argv))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
