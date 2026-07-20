from __future__ import annotations

from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.contracts import SUBMISSION_FORMAT


def verify_bundle_offline(
    bundle_path: Path,
    *,
    suite_dir: Path,
    out_path: Path | None = None,
) -> JsonObject:
    from localbench.submissions.verify import verify_bundle_offline as verify

    return verify(bundle_path, suite_dir=suite_dir, out_path=out_path)

__all__ = ("SUBMISSION_FORMAT", "verify_bundle_offline")
