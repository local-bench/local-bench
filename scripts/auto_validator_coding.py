from __future__ import annotations

import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from auto_validator_model import (
    Config,
    ConfigurationError,
    ConflictError,
    JsonObject,
    SubmissionApi,
    VerifyCall,
    coding_not_measured,
    required_int,
    required_text,
    sort_fifo,
    text,
    utc_now,
)


class CodingDaemon(Protocol):
    config: Config
    api: SubmissionApi
    verify: VerifyCall
    command_runner: Callable[[Sequence[str]], int]

    def _new_work_entry(self, submission_id: str) -> Path: ...

    def _archive_work(self, source: Path, result: str) -> None: ...

    def _post_and_log(self, submission_id: str, update: JsonObject, *, action: str) -> JsonObject: ...

    def _write_alert(self, message: str) -> None: ...

    def log(self, message: str) -> None: ...


def post_refresh(daemon: CodingDaemon, submission_id: str, verified: JsonObject) -> str:
    for attempt in range(2):
        fresh = daemon.api.get_submission(submission_id)
        update = dict(verified)
        update.update(
            {
                "operation": "projection_refresh",
                "expected_state_revision": required_int(fresh, "state_revision"),
                "previous_projection_object_sha256": required_text(fresh, "projection_object_sha256"),
            },
        )
        try:
            daemon._post_and_log(submission_id, update, action="auto_coding_verify")
            return "ok"
        except ConflictError:
            if attempt == 0:
                continue
    daemon._write_alert(f"projection refresh parked after two conflicts: {submission_id}")
    daemon.log(f"parked projection refresh submission_id={submission_id}")
    return "parked"


def run_coding_pass(daemon: CodingDaemon, *, process_listing: str | None = None) -> str:
    from auto_validator_model import guard_tripped

    config = daemon.config
    if guard_tripped(config.pause_file, process_listing=process_listing):
        daemon.log("guard: bench-active; refusing coding pass")
        return "guarded"
    if config.coding_image is None or "@sha256:" not in config.coding_image:
        raise ConfigurationError("--coding-image must be digest-pinned")
    if config.receipt_signing_key is None:
        raise ConfigurationError("--receipt-signing-key is required for --coding-pass")
    for row in sort_fifo(daemon.api.list_submissions("accepted")):
        if row.get("publish_state") != "published" or not coding_not_measured(row):
            continue
        submission_id = required_text(row, "submission_id")
        work = daemon._new_work_entry(submission_id)
        bundle = work / "bundle.lbsub.zip"
        pending = work / "run.original.json"
        coding_verified = work / "coding-verified.json"
        projection = work / "projection.json"
        daemon.api.download_bundle(submission_id, bundle)
        with zipfile.ZipFile(bundle) as archive:
            pending.write_bytes(archive.read("run.original.json"))
        argv = [
            "localbench", "code", "--pending-run", str(pending),
            "--suite-dir", str(config.suite_dir), "--image", config.coding_image,
            "--receipt-signing-key", str(config.receipt_signing_key), "--out", str(coding_verified),
        ]
        if daemon.command_runner(argv) != 0:
            daemon._write_alert(f"coding pass failed for {submission_id}")
            daemon.log(f"parked coding pass submission_id={submission_id}")
            continue
        verified = daemon.verify(
            bundle,
            suite_dir=config.suite_dir,
            projection_out=projection,
            validated_at=utc_now(),
            validator_commit=config.validator_commit,
            origin=text(row.get("origin")) or "community",
            coding_verified_path=coding_verified,
        )
        if post_refresh(daemon, submission_id, verified) == "ok":
            daemon._archive_work(work, "done")
    return "ok"
