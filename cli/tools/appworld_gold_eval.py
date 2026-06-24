"""GATE 3 helper: validate AppWorld's OWN evaluation seam + capture the frozen data-tree hash.

Two pure-trusted-side facilities (no jail, no model, no GPU — this is an ENV-INTEGRITY check, the
counterpart to the security gates):

  * ``evaluate_gold_solution(task_id)`` — load the task in the real AppWorld, EXECUTE its shipped
    gold program (``ground_truth/compiled_solution.py``, which uses only public ``apis.*`` with the
    supervisor's real credentials), submit the gold ``answer.json`` via ``complete_task``, then
    ``evaluate()``. If AppWorld's own gold no longer passes its own evaluator under the pinned
    build, the env/data is broken and NO loop result on it would be trustworthy. Returns a
    ``GoldVerdict`` (found_solution / success / passes / failures).

  * ``data_tree_hash(task_ids)`` — a stable SHA-256 over the FROZEN inputs that determine a
    verdict: each task's ``dbs/`` seed + ``specs.json`` + ``ground_truth/answer.json``, plus the
    shared ``base_dbs/`` and ``version.txt``. This makes "same frozen data" concrete for gate 2's
    record/replay and gate 3's gold eval (a recorded trace is only reproducible on a fixed tree).

Both reach the real ``world`` directly (trusted side), exactly like the env-host, so they require
the WSL appworld venv + ``APPWORLD_ROOT``. They do NOT touch bwrap or the jail (no security surface
here — the gold solution is trusted by construction).

Run standalone (prints both for the two dev tasks):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && python cli/tools/appworld_gold_eval.py'
"""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from dataclasses import dataclass, field

warnings.filterwarnings("ignore")

_DEV_TASKS = ["fac291d_1", "50e1ac9_1"]


@dataclass(frozen=True, slots=True)
class GoldVerdict:
    """Result of evaluating a task's shipped gold solution under the pinned AppWorld."""

    task_id: str
    found_solution: bool
    solution_path: str
    success: bool
    passes: tuple[str, ...] = field(default=())
    failures: tuple[str, ...] = field(default=())


def _appworld_root() -> str:
    root = os.environ.get("APPWORLD_ROOT", "")
    if not root:
        raise RuntimeError("APPWORLD_ROOT is not set; the gold-eval check needs the data tree.")
    return root


def _task_dir(task_id: str) -> str:
    return os.path.join(_appworld_root(), "data", "tasks", task_id)


def evaluate_gold_solution(task_id: str, experiment_name: str | None = None) -> GoldVerdict:
    """Execute the shipped gold solution for ``task_id`` and return its AppWorld verdict.

    Faithful to a real run's evaluation: runs the gold PROGRAM (so DB reads/mutations + the
    "no model changes" requirement are actually exercised), then submits the gold answer and
    evaluates. Imports AppWorld lazily so this module is import-safe where it is absent.
    """
    from appworld import AppWorld  # noqa: PLC0415 — lazy: confine the heavy import to call time.

    gt = os.path.join(_task_dir(task_id), "ground_truth")
    compiled_path = os.path.join(gt, "compiled_solution.py")
    answer_path = os.path.join(gt, "answer.json")
    if not (os.path.isfile(compiled_path) and os.path.isfile(answer_path)):
        return GoldVerdict(task_id=task_id, found_solution=False, solution_path=compiled_path,
                           success=False)

    compiled = _read_text(compiled_path)
    gold_answer = json.loads(_read_text(answer_path))

    world = AppWorld(task_id=task_id, experiment_name=experiment_name or f"lb_gold_eval_{task_id}")
    try:
        # The compiled gold defines `def solution(apis, requester): ...` using only public apis.*.
        # The world session exposes both `apis` and `requester` (verified), and AppWorld's safety
        # guard permits this trusted call. Define then invoke it so the program truly runs.
        world.execute(compiled)
        world.execute("solution(apis, requester)")
        # The compiled gold does NOT call complete_task; submit the gold answer ourselves, then
        # evaluate. complete_task + evaluate is the exact seam env_host._handle_finalize uses.
        complete_src = (
            "apis.supervisor.complete_task("
            f"answer=json.loads({json.dumps(json.dumps(gold_answer))}), status='success')"
        )
        world.execute(complete_src)
        verdict = world.evaluate().to_dict()
    finally:
        try:
            world.close()
        except Exception:  # noqa: BLE001 — best-effort teardown.
            pass

    passes = tuple(_req_text(p) for p in verdict.get("passes", []))
    failures = tuple(_req_text(f) for f in verdict.get("failures", []))
    return GoldVerdict(
        task_id=task_id,
        found_solution=True,
        solution_path=compiled_path,
        success=bool(verdict.get("success", False)),
        passes=passes,
        failures=failures,
    )


def data_tree_hash(task_ids: list[str] | None = None) -> str:
    """Stable SHA-256 over the FROZEN data-tree inputs that determine a verdict.

    Hashes, in a fixed order:
      * shared: ``data/version.txt`` and every file under ``data/base_dbs/`` (the seed DBs), and
      * per task (sorted): ``specs.json``, ``ground_truth/answer.json``, and every file under
        ``tasks/<id>/dbs/`` (the per-task DB delta the run reads/mutates).

    Content-addressed (path + bytes), so it is reproducible across machines with the same tree and
    changes iff the frozen inputs change. ``__pycache__`` and other volatile artifacts are skipped.
    """
    tids = sorted(task_ids or _DEV_TASKS)
    root = _appworld_root()
    data = os.path.join(root, "data")
    h = hashlib.sha256()

    def _absorb_file(path: str, label: str) -> None:
        h.update(label.encode("utf-8"))
        h.update(b"\0")
        with open(path, "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")

    def _absorb_dir(directory: str, label_prefix: str) -> None:
        if not os.path.isdir(directory):
            return
        for name in sorted(os.listdir(directory)):
            if name == "__pycache__" or name.endswith(".pyc"):
                continue
            full = os.path.join(directory, name)
            if os.path.isfile(full):
                _absorb_file(full, f"{label_prefix}/{name}")

    # Shared, task-independent frozen inputs.
    version_txt = os.path.join(data, "version.txt")
    if os.path.isfile(version_txt):
        _absorb_file(version_txt, "version.txt")
    _absorb_dir(os.path.join(data, "base_dbs"), "base_dbs")

    # Per-task frozen inputs.
    for tid in tids:
        tdir = os.path.join(data, "tasks", tid)
        for fname in ("specs.json",):
            fpath = os.path.join(tdir, fname)
            if os.path.isfile(fpath):
                _absorb_file(fpath, f"tasks/{tid}/{fname}")
        ans = os.path.join(tdir, "ground_truth", "answer.json")
        if os.path.isfile(ans):
            _absorb_file(ans, f"tasks/{tid}/ground_truth/answer.json")
        _absorb_dir(os.path.join(tdir, "dbs"), f"tasks/{tid}/dbs")

    return h.hexdigest()


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _req_text(item: object) -> str:
    if isinstance(item, dict):
        for key in ("requirement", "message", "name", "description"):
            val = item.get(key)
            if isinstance(val, str):
                return val
        return json.dumps(item, sort_keys=True)
    return str(item)


def main() -> int:
    import importlib.metadata as md

    print("=" * 90)
    print("GATE 3 — AppWorld env validation under the pinned build + frozen data-tree hash")
    print("=" * 90)
    try:
        print("appworld version :", md.version("appworld"))
    except Exception as exc:  # noqa: BLE001
        print("appworld version : <unknown>", exc)
    print("APPWORLD_ROOT    :", os.environ.get("APPWORLD_ROOT", "<unset>"))
    print("data-tree hash   :", data_tree_hash(_DEV_TASKS), f"({'+'.join(_DEV_TASKS)})")
    print("-" * 90)
    rc = 0
    for tid in _DEV_TASKS:
        v = evaluate_gold_solution(tid)
        status = "PASS" if (v.found_solution and v.success) else "FAIL"
        print(f"[{status}] {tid}: found={v.found_solution} success={v.success} "
              f"passes={len(v.passes)} failures={len(v.failures)}")
        for f in v.failures[:5]:
            print("        fail:", f[:140])
        if not (v.found_solution and v.success):
            rc = 1
    print("=" * 90)
    print(f"GATE 3 RESULT: {'PASS' if rc == 0 else 'FAIL'} — gold solutions evaluate as success "
          "under the pinned env.")
    print("=" * 90)
    return rc


if __name__ == "__main__":
    import sys

    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # AppWorld rebinds builtins.SystemExit on the host; os._exit guarantees the code escapes.
    os._exit(_rc)
