from __future__ import annotations

from pathlib import Path

from localbench.check.reference import ReferenceEditionError
from localbench.check.run import CheckRequest, run_check
from localbench.check.types import CheckError


def check_command(
    artifact: Path,
    *,
    parent: str | None,
    dry_run: bool,
    manifest: Path,
    out: Path | None,
    resume: Path | None,
    reference_bundle: Path | None,
    reference_public_key: str | None,
    reference_checkset_edition: str | None,
    smoke: bool = False,
    reference_run: Path | None = None,
    allow_untrusted_code: bool = False,
) -> tuple[int, str]:
    try:
        run_dir, record = run_check(
            CheckRequest(
                artifact=artifact,
                manifest=manifest,
                parent=parent,
                dry_run=dry_run,
                out=out,
                resume=resume,
                reference_bundle=reference_bundle,
                reference_public_key=reference_public_key,
                reference_checkset_edition=reference_checkset_edition,
                smoke=smoke,
                reference_run=reference_run,
                allow_untrusted_code=allow_untrusted_code,
            )
        )
    except (CheckError, ReferenceEditionError, OSError, ValueError) as error:
        return 2, f"error: {error}"
    comparison = record.get("comparison")
    pairing = comparison.get("pairing_status") if isinstance(comparison, dict) else "unknown"
    return 0, f"check record written to {run_dir}; pairing={pairing}"
