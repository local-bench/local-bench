from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from localbench.exit_codes import EXIT_COMPLETE
from localbench.one_shot.types import (
    OneShotSuiteIdentity,
    ResolvedOneShotModel,
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
    if context.record.get("headline_complete") is not True:
        raise SuiteResolutionError(
            "incomplete_run: one-shot submission requires all six headline axes; "
            "finish coding and agentic grading before submitting",
        )
    result = (context.submitter or submit_finished_run)(_submit_options(context.args, context.run_root))
    for line in result.lines:
        print(line)
    return result.exit_code if result.exit_code != 0 else EXIT_COMPLETE


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
