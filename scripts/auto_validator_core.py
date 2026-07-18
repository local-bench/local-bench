from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from localbench.submissions.decision_log import append_decision_log
from localbench.submissions.status_update import verify_submission
from localbench.submissions.validate import SubmissionValidationError

from auto_validator_coding import post_refresh as coding_post_refresh
from auto_validator_coding import run_coding_pass as coding_run
from auto_validator_http import StdlibApi, post_with_installed_helper
from auto_validator_model import (
    MAX_API_FAILURES,
    KEEP_WORK_ENTRIES,
    SAFE_NAME_PATTERN,
    ApiError,
    AppendLogCall,
    Config,
    ConflictError,
    JsonObject,
    PostCall,
    SubmissionApi,
    VerifyCall,
    guard_tripped,
    initial_update,
    map_rejection,
    rejection_update,
    required_text,
    run_command,
    scrub_text,
    sort_fifo,
    text,
    utc_now,
)
from auto_validator_state import IntentJournal, RotatingLog


class AutoValidator:
    def __init__(
        self,
        config: Config,
        *,
        api: SubmissionApi | None = None,
        verify: VerifyCall = verify_submission,
        post: PostCall | None = None,
        append_log: AppendLogCall = append_decision_log,
        log_sink: Callable[[str], None] | None = None,
        command_runner: Callable[[Sequence[str]], int] | None = None,
    ) -> None:
        self.config = config
        self.api = api or StdlibApi(config.site, config.validator_secret)
        self.verify = verify
        self.post = post or self._post_default
        self.append_log = append_log
        self.log_sink = log_sink or RotatingLog(config.log_file, config.validator_secret)
        self.command_runner = command_runner or run_command
        self.journal = IntentJournal(config.intent_file)
        self.consecutive_api_failures = 0

    def log(self, message: str) -> None:
        self.log_sink(scrub_text(message, self.config.validator_secret))

    def run_cycle(self, *, process_listing: str | None = None) -> str:
        if guard_tripped(self.config.pause_file, process_listing=process_listing):
            self.log("guard: bench-active")
            return "guarded"
        try:
            rows = sort_fifo(self.api.list_submissions("pending_verification"))
        except ApiError as error:
            return "stop" if self.record_api_failure(str(error)) else "retry"
        for row in rows:
            outcome = self._process_initial(row)
            if outcome in {"retry", "stop"}:
                return outcome
        self.consecutive_api_failures = 0
        return "ok"

    def _process_initial(self, listed: JsonObject) -> str:
        submission_id = required_text(listed, "submission_id")
        try:
            fresh = self.api.get_submission(submission_id)
        except ApiError as error:
            return "stop" if self.record_api_failure(str(error)) else "retry"
        if fresh.get("status") != "pending_verification":
            self.log(f"skip: status-changed submission_id={submission_id}")
            return "ok"
        work = self._new_work_entry(submission_id)
        bundle = work / "bundle.lbsub.zip"
        projection = work / "projection.json"
        result_kind = "failed"
        try:  # noqa: BROAD_EXCEPT_OK
            self.api.download_bundle(submission_id, bundle)
            verified = self.verify(
                bundle,
                suite_dir=self.config.suite_dir,
                projection_out=projection,
                validated_at=utc_now(),
                validator_commit=self.config.validator_commit,
                origin=text(fresh.get("origin")) or "community",
            )
            update = initial_update(verified)
            result_kind = "done" if update["status"] == "accepted" else "failed"
        except Exception as error:  # noqa: BROAD_EXCEPT_OK
            code, detail = map_rejection(
                error,
                secret=self.config.validator_secret,
                validation_types=(SubmissionValidationError,),
            )
            update = rejection_update(code, detail)
        if self.config.dry_run:
            self.log(f"dry-run would POST submission_id={submission_id} payload={json.dumps(update, sort_keys=True)}")
            self._archive_work(work, result_kind)
            return "ok"
        try:
            self._post_and_log(submission_id, update, action="auto_verify")
        except ConflictError:
            self.log(f"fifo conflict: retry next cycle submission_id={submission_id}")
            return "retry"
        except ApiError as error:
            return "stop" if self.record_api_failure(str(error)) else "retry"
        self._archive_work(work, result_kind)
        self.consecutive_api_failures = 0
        return "ok"

    def _post_and_log(self, submission_id: str, update: JsonObject, *, action: str) -> JsonObject:
        attempt_id = uuid.uuid4().hex
        operation = required_text(update, "operation")
        self.journal.append(
            {"attempt_id": attempt_id, "intent": action, "submission_id": submission_id, "operation": operation, "at": utc_now()},
        )
        try:
            response = self.post(submission_id, update)
        except ConflictError:
            self.journal.append(
                {"attempt_id": attempt_id, "outcome": "conflict", "submission_id": submission_id, "http_status": 409, "at": utc_now()},
            )
            raise
        self.journal.append(
            {"attempt_id": attempt_id, "outcome": "success", "submission_id": submission_id, "http_status": 200, "at": utc_now()},
        )
        status = text(update.get("status")) or "unknown"
        extra = self._decision_extra(submission_id, status, update)
        self.append_log(actor="auto-validator", action=action, submission_id=submission_id, reason=status, extra=extra)
        self.journal.append(
            {"attempt_id": attempt_id, "decision_logged": action, "submission_id": submission_id, "at": utc_now()},
        )
        if status == "accepted" and response.get("published") is False:
            self.log(f"accepted submission_id={submission_id} published=false")
        return response

    def reconcile_intents(self) -> bool:
        for intent in self.journal.dangling():
            submission_id = required_text(intent, "submission_id")
            try:
                row = self.api.get_submission(submission_id)
            except ApiError as error:
                self.log(f"reconcile failed submission_id={submission_id}: {error}")
                self.record_api_failure(str(error))
                return False
            status = text(row.get("status")) or "unknown"
            self.log(f"reconciled submission_id={submission_id} status={status}")
            if status not in {"accepted", "rejected"}:
                continue
            extra = self._decision_extra(submission_id, status, row)
            self.append_log(
                actor="auto-validator", action="reconciled_auto_verify",
                submission_id=submission_id, reason=status, extra=extra,
            )
            attempt_id = required_text(intent, "attempt_id")
            if intent.get("recorded_outcome") is None:
                self.journal.append(
                    {"attempt_id": attempt_id, "outcome": "reconciled", "submission_id": submission_id, "http_status": 200, "at": utc_now()},
                )
            self.journal.append(
                {"attempt_id": attempt_id, "decision_logged": "reconciled_auto_verify", "submission_id": submission_id, "at": utc_now()},
            )
        self.consecutive_api_failures = 0
        return True

    def post_refresh(self, submission_id: str, verified: JsonObject) -> str:
        return coding_post_refresh(self, submission_id, verified)

    def run_coding_pass(self, *, process_listing: str | None = None) -> str:
        return coding_run(self, process_listing=process_listing)

    def record_api_failure(self, message: str) -> bool:
        self.consecutive_api_failures += 1
        self.log(f"api failure {self.consecutive_api_failures}: {message}")
        if self.consecutive_api_failures < MAX_API_FAILURES:
            return False
        self._write_alert(message)
        return True

    def _write_alert(self, message: str) -> None:
        self.config.alert_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.alert_file.write_text(
            f"{utc_now()} {scrub_text(message, self.config.validator_secret)}\n",
            encoding="utf-8",
        )

    def _post_default(self, submission_id: str, update: JsonObject) -> JsonObject:
        return post_with_installed_helper(self.config.site, self.config.validator_secret, submission_id, update)

    def _new_work_entry(self, submission_id: str) -> Path:
        safe_id = SAFE_NAME_PATTERN.sub("_", submission_id).strip("_") or "submission"
        entry = self.config.effective_work_dir / f"{utc_now(compact=True)}-{safe_id}-{uuid.uuid4().hex[:8]}"
        entry.mkdir(parents=True)
        return entry

    def _archive_work(self, source: Path, result: str) -> None:
        destination_root = self.config.effective_work_dir.parent / result
        destination_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination_root / source.name)
        entries = sorted(
            (path for path in destination_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
        )
        for expired in entries[:-KEEP_WORK_ENTRIES]:
            shutil.rmtree(expired)

    @staticmethod
    def _decision_extra(submission_id: str, status: str, source: JsonObject) -> JsonObject:
        extra: JsonObject = {"result": status, "submission_id": submission_id}
        projection_sha = text(source.get("projection_object_sha256"))
        if projection_sha is not None:
            extra["projection_object_sha256"] = projection_sha
        return extra
