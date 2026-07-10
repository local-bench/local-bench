from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from localbench.exit_codes import EXIT_COMPLETE
from localbench.one_shot.serve_plan import STATIC_EXEC_BENCHES
from localbench.one_shot.types import (
    OneShotSuiteIdentity,
    ResolvedOneShotModel,
    STATIC_EXEC_SUITE_IDENTITY,
)
from localbench.suite_errors import SuiteResolutionError
from localbench.submissions.submit_run import DEFAULT_SITE, SubmitRunOptions, SubmitRunResult, submit_finished_run


class Submitter(Protocol):
    def __call__(self, options: SubmitRunOptions) -> SubmitRunResult: ...


@dataclass(frozen=True, slots=True)
class OneShotSubmitContext:
    args: argparse.Namespace
    run_root: Path
    submit_choice: bool | None
    resolved: ResolvedOneShotModel
    submitter: Submitter | None
    input_fn: Callable[[], str]
    record: dict[str, object]
    suite_identity: OneShotSuiteIdentity


def maybe_submit(context: OneShotSubmitContext) -> int:
    should_submit = context.submit_choice
    if should_submit is None and not context.resolved.local_only:
        print("submit? [y/N] ", end="")
        should_submit = context.input_fn().strip().lower() in {"y", "yes"}
    if should_submit is not True:
        print("submit    skipped")
        return EXIT_COMPLETE
    if context.suite_identity == STATIC_EXEC_SUITE_IDENTITY:
        _assert_static_submission_identity(context.record)
    result = (context.submitter or submit_finished_run)(_submit_options(context.args, context.run_root))
    for line in result.lines:
        print(line)
    return result.exit_code if result.exit_code != 0 else EXIT_COMPLETE


def _assert_static_submission_identity(record: dict[str, object]) -> None:
    manifest = record.get("manifest")
    suite = manifest.get("suite") if isinstance(manifest, dict) else None
    benches = record.get("benches")
    actual_benches = set(benches) if isinstance(benches, dict) else set()
    expected_benches = set(STATIC_EXEC_BENCHES)
    if not isinstance(suite, dict):
        raise SuiteResolutionError("static submission is missing manifest.suite identity")
    checks = {
        "coverage_profile_id": "static-exec-5axis-v1",
        "suite_release_id": STATIC_EXEC_SUITE_IDENTITY.release_id,
        "suite_manifest_sha256": STATIC_EXEC_SUITE_IDENTITY.manifest_sha256,
    }
    mismatches = [
        f"{key}={suite.get(key)!r} expected {expected!r}"
        for key, expected in checks.items()
        if suite.get(key) != expected
    ]
    if actual_benches != expected_benches:
        mismatches.append(
            f"benches={sorted(actual_benches)!r} expected {sorted(expected_benches)!r}",
        )
    if "appworld_c" in actual_benches:
        mismatches.append("appworld_c must be absent")
    if mismatches:
        raise SuiteResolutionError("static submission identity mismatch: " + "; ".join(mismatches))


def _submit_options(args: argparse.Namespace, run_root: Path) -> SubmitRunOptions:
    return SubmitRunOptions(
        site=str(getattr(args, "site", None) or DEFAULT_SITE),
        run=run_root / "localbench-run.json",
        bundle=None,
        suite_dir=getattr(args, "suite_dir", None),
        signing_key=getattr(args, "signing_key", None),
        display_name=getattr(args, "display_name", None),
        bypass_token=getattr(args, "bypass_token", None),
        bypass_token_file=getattr(args, "bypass_token_file", None),
        dry_run=False,
    )
