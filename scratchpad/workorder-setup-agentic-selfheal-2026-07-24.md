# Work order: setup-agentic self-heal + friendly --resume error (0.4.7 candidates)

Two CLI defects found 2026-07-24 while launching a public-route ranked run (Qwen3.6-27B
Q6_K ladder rung). Both are UX dead-ends a real submitter would hit. DO NOT weaken any
integrity check — both fixes are about the recovery path, not the detection.

## Context (verbatim failures)

1. Bench preflight failed:
   `error  The agentic axis needs the managed AppWorld harness. Run 'localbench
   setup-agentic' before starting the full-suite benchmark. ... Setup detail:
   runtime_mutated: critical hash mismatch. Reprovision`
   Then plain `localbench setup-agentic` failed with the SAME
   `runtime_mutated: critical hash mismatch. Reprovision` (exit 15) — circular: the
   error's own advice does not work. The actual remedy (undiscoverable) was:
   `localbench setup-agentic --remove aw013p1-pypi28113a7a-ubuntu2404-py312-c0v5-r1 --confirm-active`
   then plain `localbench setup-agentic` (worked, fresh runtime provisioned).

2. `localbench bench ... --resume runs/<dir> --out runs/<dir>` where the dir had no
   campaign.json (fresh start with resume flag) died with the raw
   `error  [Errno 2] No such file or directory: 'runs\\qwen36-27b-q6k-046\\campaign.json'`.

## Fix 1 — setup-agentic self-heals a mutated managed runtime

Code sites:
- cli/src/localbench/cli.py:1286 `_setup_agentic` (subparser at cli.py:370).
- runtime_mutated raises: cli/src/localbench/appliance/native_materialization.py (multiple),
  appliance/handshake.py:25, appliance/native_worker.py:33 — all
  `ProvisioningError("runtime_mutated", ...)`.
- Removal path already exists (used by --remove/--confirm-active).

Required behavior, DEFAULT setup-agentic invocation (no --list/--remove/--prune):
- When provisioning fails because an EXISTING managed runtime fails integrity
  (ProvisioningError kind == "runtime_mutated"), do not just re-raise:
  - If stdin is a TTY: prompt `managed runtime <id> failed integrity (<detail>).
    Remove and reprovision it now? [y/N]` — on yes, remove that runtime (managed
    LocalBench-Agentic-* distros ONLY, never any other WSL distro) and provision fresh
    in the same invocation.
  - Non-interactive (no TTY) or user declines: exit with an error that contains the
    EXACT working commands including the real runtime id:
    `localbench setup-agentic --remove <id> --confirm-active` + rerun `localbench
    setup-agentic`.
  - New flag `--reprovision` (or extend existing conventions if a better fit) to
    authorize the remove+rebuild non-interactively.
- Update the guidance strings that today point circularly at plain setup-agentic for
  mutated runtimes (serving/agentic_support.py:12; scoring/agentic_exec/
  worker_resolution.py:54,170; scoring/agentic_exec/wsl_process.py:146,168): when the
  detail is runtime_mutated, the remedy must mention the self-heal path
  (`setup-agentic --reprovision`) rather than the plain command.

## Fix 2 — friendly typed error for --resume without a campaign

Code site: cli/src/localbench/cli.py:978 (`campaign_path = args.resume / "campaign.json"`)
and wherever it is read unguarded. When campaign.json does not exist under --resume:
emit a typed CLI error (same convention as other `error  ...` messages, non-zero exit):
`no resumable campaign at '<path>' (campaign.json not found) — start a fresh run
without --resume, or point --resume at an existing run directory`. No raw OSError/errno
text. Do NOT auto-fall-through to a fresh run — refusing is correct (a typo'd resume
path silently starting fresh would be worse); only the message quality changes.

## Constraints
- Tests required (cli/tests, pytest): (a) mutated-runtime self-heal with a mocked
  provisioner/removal — TTY-accept path performs remove+provision; (b) non-TTY path
  errors with the exact commands INCLUDING the runtime id; (c) --reprovision flag path;
  (d) --resume missing-campaign friendly error (message content + exit code, no
  traceback). Never invoke real wsl.exe/docker in tests — mock.
- NEVER weaken detection/fail-closed behavior. Self-heal may only touch managed
  LocalBench-Agentic-* runtimes.
- Do not bump the version (release bump happens separately).
- Gate with cli/.venv/Scripts/python.exe -m pytest (never bare `python` — wrong stack).
- A LIVE GPU benchmark is running from a separate venv: do NOT run bench/serve/
  setup-agentic/wsl/docker commands for real. Unit tests + mocks only.
