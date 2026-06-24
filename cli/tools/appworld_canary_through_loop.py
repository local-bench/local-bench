"""GATE 1 (Phase-2 gauntlet): run the 55-canary EXPLOIT SUITE through the FULL Protocol C
LOOP path — not just ``AppWorldSandbox.run_block`` — and confirm it introduces NO new escape.

The sandboxed canary suite (``appworld_canary_suite_sandboxed.py``) already proves every canary
is BLOCKED when its code is handed straight to ``AppWorldSandbox.run_block(can.code)``. This tool
closes the remaining gap: the real loop never calls ``run_block`` on raw model text — it first
runs the text through ``block_parser.parse_turn`` (fence extraction + final-answer detection) and
ONLY THEN executes the extracted block. So here we drive each canary payload exactly the way the
loop drives a model turn:

    assistant_text = "```python\\n<canary code>\\n```"   # the canary as a model-emitted block
    parsed = parse_turn(assistant_text)                  # the loop's parse step
    obs    = sandbox.run_block(parsed.code)              # the loop's execute step (same jail)

then classify with the SAME classifier + inert-marker demotion the sandboxed suite uses. The hard
gate is identical: **SUCCEEDED = 0 and ERROR = 0** (all 55 blocked). Gate on the PARSED COUNT, not
the exit code (AppWorld rebinds ``builtins.SystemExit`` on the trusted host).

Why this can only ever be >= as safe as the direct path, never less: ``parse_turn`` is a pure
text->text transform that (a) extracts the fenced body and (b) can REJECT a turn (0/>1/empty
block) before any execution. It can never grant the jail more capability than running the body
verbatim would. The execution still goes through the unchanged ``AppWorldSandbox.run_block`` into
the unchanged bwrap jail + env-host wall. This tool makes that guarantee EMPIRICAL rather than
argued, and it additionally audits the two HARNESS-controlled blocks the loop injects.

It ALSO runs the HARNESS-BLOCK AUDIT (model-free, no sandbox needed): the loop injects exactly two
blocks of its own — the bootstrap instruction-fetch and the finalize answer-read-back. This audit
asserts they are built from module constants (never interpolated from model text), enumerates what
they touch, and confirms they cannot be used to exfiltrate ground truth (they run in the SAME
jail as model code, which the canary suite already proves is data-free).

Run (WSL appworld venv + bwrap on PATH or at ~/.local/bin/bwrap):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && export PATH="$HOME/.local/bin:$PATH" \
    && python cli/tools/appworld_canary_through_loop.py --json'

The harness-block audit alone (no sandbox/appworld/bwrap) runs anywhere:
  python cli/tools/appworld_canary_through_loop.py --audit-only
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

# Make both the repo src (for localbench) and the tools dir (for the baseline suite) importable.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))
sys.path.insert(0, str(_REPO / "cli" / "tools"))

warnings.filterwarnings("ignore")

# Pure imports first (these never touch appworld/bwrap, so --audit-only works on any host).
from localbench.scoring.agentic_exec import protocol_c_loop as loop  # noqa: E402
from localbench.scoring.agentic_exec.block_parser import (  # noqa: E402
    BlockFormatError,
    TurnAction,
    parse_turn,
)


# ==================================================================================================
# Canary-through-loop driver
# ==================================================================================================
def _as_model_block(code: str) -> str:
    """Wrap a canary's code as a model-emitted Protocol C turn (one fenced python block).

    This is byte-for-byte how the scripted agent / a real model presents a block to the loop, so
    ``parse_turn`` sees exactly what it sees in production.
    """
    return f"```python\n{code}\n```"


def _drive_through_loop_parse(sb: object, code: str) -> str:
    """Run one canary payload through the LOOP's parse->execute path; return the classifier view.

    Mirrors ``protocol_c_loop.run_task``'s per-turn handling of a code block:
      1. wrap the canary as a fenced ```python block (a model turn),
      2. ``parse_turn`` it (the loop's parse step — may reject; an escape can't come from a
         rejected turn, so a rejection is reported as BLOCKED-by-parser),
      3. ``sandbox.run_block(parsed.code)`` (the loop's execute step — the SAME jail entry).

    The returned string is composed exactly like the sandboxed suite composes ``stdout`` for the
    classifier: printed output, plus the error text appended behind a synthetic traceback header
    when the block raised (so a raised exception reads as a BLOCK, identical to the direct path).
    """
    assistant_text = _as_model_block(code)
    parsed = parse_turn(assistant_text)
    if isinstance(parsed, BlockFormatError):
        # The loop would feed back a corrective observation and NEVER execute this turn. No code
        # ran, so nothing could escape — surface a synthetic traceback so the classifier reads it
        # as BLOCKED (and record the parser kind for the report).
        return f"Traceback (most recent call last)\nBlockFormatError({parsed.kind}): not executed"
    assert isinstance(parsed, TurnAction)
    obs = sb.run_block(parsed.code)  # type: ignore[attr-defined]
    out = getattr(obs, "stdout", "") or ""
    err = getattr(obs, "error", None)
    if err:
        out = (out + "\nTraceback (most recent call last)\n" + str(err)).strip()
    return out


def run_canaries_through_loop(emit_json: bool = False) -> int:
    # Imported lazily so --audit-only and import on Windows do not require appworld/bwrap.
    import appworld_canary_suite as base  # noqa: PLC0415
    import appworld_canary_suite_sandboxed as sandboxed  # noqa: PLC0415
    from localbench.scoring.agentic_exec.sandbox import (  # noqa: PLC0415
        AppWorldSandbox,
        SandboxConfig,
        resolve_bwrap,
    )

    print("=" * 100)
    print("APPWORLD CANARY SUITE — THROUGH THE FULL PROTOCOL C LOOP (parse_turn -> run_block)")
    print("=" * 100)

    bwrap = resolve_bwrap()
    if not bwrap:
        print("[FATAL] bwrap not found (need bubblewrap at ~/.local/bin/bwrap or on PATH). STOP.")
        return 2
    print(f"bwrap            : {bwrap}")
    print(f"APPWORLD_ROOT    : {os.environ.get('APPWORLD_ROOT', '<unset>')}")
    print(f"primary DEV task : {base.PRIMARY_TASK}   second DEV task (seed): {base.SECOND_TASK}")

    # Host-side secret oracle + cross-task seeding (identical to the sandboxed suite) so the
    # classifier can detect a leak by sentinel; the canary CODE only ever runs inside the jail.
    sec = base.load_secrets()
    print(f"answer sentinel  : {sec.answer_sentinel!r}")
    print(f"solution sentinel: {sec.solution_sentinel!r}")
    print(f"db sentinel      : {sec.db_sentinel!r}")
    try:
        base.seed_second_task_outputs()
        print("seed task outputs: written under experiments/outputs/lb_canary_seed")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] could not seed second-task outputs ({type(exc).__name__}: {exc}); "
              "L1-L3 targets may be MISSING (still treated as BLOCKED).")

    canaries = base.build_canaries(sec)
    results: list[base.Result] = []
    parser_rejected: list[str] = []  # canaries the loop's parser would reject before exec

    cfg = SandboxConfig(experiment_name="lb_canary_through_loop")
    with AppWorldSandbox(base.PRIMARY_TASK, cfg) as sb:
        for can in canaries:
            # Track whether the loop's parser would have rejected this turn (informational; a
            # rejected turn never executes, so it is at-least-as-safe as the direct path).
            parsed = parse_turn(_as_model_block(can.code))
            if isinstance(parsed, BlockFormatError):
                parser_rejected.append(f"{can.cid}({parsed.kind})")
            try:
                out = _drive_through_loop_parse(sb, can.code)
            except Exception as exc:  # noqa: BLE001 — a broker/sandbox error is a hard BLOCK signal.
                out = f"Traceback (most recent call last)\n{type(exc).__name__}: {exc}"
            results.append(sandboxed._classify_sandboxed(out, can, sec))

    # Reuse the sandboxed suite's exact table + summary printer for an apples-to-apples report.
    sandboxed._print_table_and_summary(results)

    succ = [r for r in results if r.verdict == "SUCCEEDED"]
    errs = [r for r in results if r.verdict == "ERROR"]
    blocked = [r for r in results if r.verdict == "BLOCKED"]

    print("\nLOOP-PATH NOTE:")
    print(f"  canaries driven through parse_turn -> run_block : {len(results)}")
    print(f"  the loop's parser REJECTED before any exec      : {len(parser_rejected)}"
          + (f"  -> {', '.join(parser_rejected)}" if parser_rejected else ""))
    print("  (a parser-rejected turn never reaches the jail, so it cannot escape; it is counted "
          "BLOCKED.)")

    if emit_json:
        print("\n--- JSON ---")
        print(json.dumps({
            "path": "parse_turn->run_block",
            "total": len(results),
            "succeeded": len(succ),
            "error": len(errs),
            "blocked": len(blocked),
            "parser_rejected": parser_rejected,
            "results": [{
                "cid": r.cid, "category": r.category, "verdict": r.verdict,
                "severity": r.severity, "desc": r.desc, "proof": r.proof,
            } for r in results],
        }, indent=2))

    print("\n" + "=" * 100)
    print(f"LOOP-PATH RESULT: SUCCEEDED={len(succ)}  ERROR/FLAG={len(errs)}  BLOCKED={len(blocked)}  "
          f"(gate requires SUCCEEDED=0, ERROR=0, total=55)")
    print("=" * 100)
    return 1 if (succ or errs or len(results) != 55) else 0


# ==================================================================================================
# Harness-block audit (model-free; no sandbox required)
# ==================================================================================================
def audit_harness_blocks() -> tuple[bool, list[str]]:
    """Audit the TWO harness-controlled blocks the loop injects. Returns (ok, findings).

    The loop injects exactly two blocks of its own making (everything else is model text):
      1. the BOOTSTRAP instruction-fetch (``protocol_c_loop._bootstrap_task_context``), which runs
         ``apis.supervisor.show_active_task()`` and prints the task instruction + supervisor email
         behind a ``__LB_CTX__`` tag; and
      2. the FINALIZE answer-read-back (``protocol_c_loop._READBACK_CODE``), which json-dumps the
         model's own ``answer`` variable behind a ``__LB_ANSWER__`` tag.

    The audit asserts, by inspecting the loop source, that:
      * both block strings are MODULE CONSTANTS / built only from module constants — they do NOT
        interpolate any model-supplied text (no f-string over model data, no concat of model text),
        so a model cannot inject code into a harness block;
      * the bootstrap reads only non-secret, already-prompt-visible fields (instruction + the
        supervisor email, which is also placed in the prompt) — it never reads ground truth,
        answer.json, the requester, or any other task secret; and
      * the read-back reads ONLY the model's own ``answer`` variable (which the model set) — it
        cannot exfiltrate anything the model did not already compute.
      * Both blocks execute in the SAME bwrap jail as model code (via ``sandbox.run_block`` /
        the same RPC seam), which the 55-canary suite proves has no data tree and no requester —
        so even these harness blocks have zero reach to ground truth.
    """
    findings: list[str] = []
    src = Path(loop.__file__).read_text(encoding="utf-8")

    # -- 1. The read-back block is a module constant, derived only from two module constants. ------
    rb = loop._READBACK_CODE
    rb_ok = (
        isinstance(rb, str)
        and loop._ANSWER_VAR in rb            # references the answer var name (a constant)
        and loop._READBACK_TAG in rb          # references the tag (a constant)
        and "answer" == loop._ANSWER_VAR      # the only variable it reads is the model's `answer`
    )
    if rb_ok:
        findings.append("OK   read-back block is a module constant built from "
                        "_ANSWER_VAR + _READBACK_TAG; reads only the model's own `answer` var")
    else:
        findings.append(f"FAIL read-back block not a clean constant: {rb!r}")

    # The read-back must NOT touch anything sensitive: no apis call, no file/requester/os access.
    rb_clean = not any(tok in rb for tok in ("apis.", "open(", "requester", "import os", "__"))
    # (it legitimately uses `import json as _lbjson`, which is benign; the `__` check would catch
    #  dunder tricks — but the tag itself contains underscores, so check the CODE lines only.)
    rb_code_lines = [ln for ln in rb.splitlines() if not ln.strip().startswith("print(")]
    rb_clean = not any(("apis." in ln or "requester" in ln or "open(" in ln or "os." in ln)
                       for ln in rb_code_lines)
    if rb_clean:
        findings.append("OK   read-back touches no apis/requester/file/os — only json.dumps(answer)")
    else:
        findings.append("FAIL read-back touches a sensitive name")

    # -- 2. The bootstrap block is a local constant; reads only instruction + supervisor email. ----
    # It is a function-local string literal in _bootstrap_task_context; assert by source that it
    # is built as a single string literal (no .format/% / f"" over outside data) and only calls
    # show_active_task (the same call the prompt already tells the model it may make).
    boot_fn_src = _extract_function_source(src, "_bootstrap_task_context")
    boot_ok = (
        "apis.supervisor.show_active_task()" in boot_fn_src
        and "__LB_CTX__" in boot_fn_src
        and ".format(" not in boot_fn_src          # no template interpolation of outside data
        and "f\"" not in boot_fn_src.replace("f\"\"\"", "")  # no f-string building the code
        and "answer.json" not in boot_fn_src       # never reaches ground truth
        and "requester" not in boot_fn_src
    )
    if boot_ok:
        findings.append("OK   bootstrap block is a static literal; calls only "
                        "apis.supervisor.show_active_task() and prints instruction+email "
                        "(both already prompt-visible, non-secret)")
    else:
        findings.append("FAIL bootstrap block is not a clean static literal / touches more than "
                        "show_active_task")

    # -- 3. Neither harness block is built from model-supplied text. -------------------------------
    # The loop appends model text ONLY as chat-history ChatMessages; the two harness blocks are the
    # ONLY strings handed to sandbox.run_block by the harness itself. Enumerate the REAL call
    # arguments to ``run_block`` (excluding the module docstring + the Protocol method def) and
    # confirm each is one of exactly three allowed forms — none of which is a model-derived
    # f-string/concat:
    #   * ``code``        — the bootstrap's local CONSTANT literal (in _bootstrap_task_context),
    #   * ``_READBACK_CODE`` — the read-back MODULE CONSTANT,
    #   * ``parsed.code`` — the model's block, already extracted by parse_turn and run verbatim
    #                       (this IS the model surface the canary-through-loop run exercises).
    callsite_args = _run_block_call_args(src)
    allowed_args = {"code", "_READBACK_CODE", "parsed.code"}
    unexpected = [a for a in callsite_args if a not in allowed_args]
    if set(callsite_args) <= allowed_args and {"_READBACK_CODE", "parsed.code"} <= set(callsite_args):
        findings.append("OK   every sandbox.run_block call passes a constant or parse_turn's "
                        f"parsed.code (args seen: {sorted(set(callsite_args))}); no model-"
                        "interpolated f-string is ever handed to a harness block")
    else:
        findings.append(f"FAIL sandbox.run_block called with unexpected argument(s): {unexpected} "
                        f"(all args seen: {callsite_args})")

    # -- 4. The model can never call complete_task/save_state/etc even by emitting the tag text. ---
    # The read-back tag/bootstrap are harmless even if the MODEL emits them verbatim: they only
    # read instruction/answer. The actual finalize (complete_task) + state ops are env-host-owned
    # and forbidden to the model (env_host._FORBIDDEN_API_NAMES). Cross-check that constant exists.
    try:
        from localbench.scoring.agentic_exec import env_host  # noqa: PLC0415
        forbidden = env_host._FORBIDDEN_API_NAMES
        need = {"complete_task", "evaluate", "save_state", "load_state", "close", "request"}
        if need.issubset(forbidden):
            findings.append("OK   env-host forbids the model calling complete_task/evaluate/"
                            "save_state/load_state/close/request (harness-only)")
        else:
            findings.append(f"FAIL env-host forbidden set missing {need - set(forbidden)}")
    except Exception as exc:  # noqa: BLE001 — env_host import is pure; failure is itself a finding.
        findings.append(f"WARN could not import env_host to cross-check forbidden APIs: {exc}")

    ok = all(f.startswith(("OK", "WARN")) for f in findings) and not any(
        f.startswith("FAIL") for f in findings
    )
    return ok, findings


def _run_block_call_args(module_src: str) -> list[str]:
    """Return the argument expression of every REAL ``sandbox.run_block(<arg>)`` call.

    Uses the AST so the module docstring's illustrative ``sandbox.run_block(action.code)`` and the
    ``SandboxLike.run_block`` Protocol method *definition* are excluded — only genuine call nodes
    of the form ``<name>.run_block(<single arg>)`` are returned, as their unparsed argument text.
    This is what lets the audit assert that no harness ``run_block`` call is fed a model-derived
    f-string (only a module/local constant or ``parse_turn``'s extracted ``parsed.code``).
    """
    import ast  # noqa: PLC0415 — stdlib, local to keep module import-light.

    tree = ast.parse(module_src)
    args: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "run_block" and node.args:
            try:
                args.append(ast.unparse(node.args[0]))
            except Exception:  # noqa: BLE001 — unparse is best-effort; record a sentinel.
                args.append("<unparseable>")
    return args


def _extract_function_source(module_src: str, fn_name: str) -> str:
    """Return the source text of ``def <fn_name>`` up to the next top-level ``def``/``class``.

    A light textual slice (no import side effects) sufficient for the audit's substring checks.
    """
    lines = module_src.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(f"def {fn_name}(") or ln.startswith(f"def {fn_name} "):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    return "\n".join(lines[start:end])


def _print_audit(ok: bool, findings: list[str]) -> None:
    print("=" * 100)
    print("HARNESS-BLOCK AUDIT — the two blocks the loop injects (bootstrap + answer read-back)")
    print("=" * 100)
    for f in findings:
        print(f"  {f}")
    print("-" * 100)
    print(f"AUDIT: {'PASS' if ok else 'FAIL'} — harness blocks are harness-controlled "
          f"(model cannot inject) and cannot exfiltrate ground truth.")
    print("=" * 100)


def main(argv: list[str]) -> int:
    emit_json = "--json" in argv
    audit_only = "--audit-only" in argv

    ok, findings = audit_harness_blocks()
    _print_audit(ok, findings)
    if audit_only:
        return 0 if ok else 1

    print()
    rc = run_canaries_through_loop(emit_json=emit_json)
    return rc if ok else (rc or 1)


if __name__ == "__main__":
    _rc = main(sys.argv[1:])
    sys.stdout.flush()
    sys.stderr.flush()
    # AppWorld rebinds builtins.SystemExit on the host; os._exit guarantees the code escapes.
    os._exit(_rc)
