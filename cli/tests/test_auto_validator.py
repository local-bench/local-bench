from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

import pytest


def _load_module() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "auto_validator.py"
    spec = importlib.util.spec_from_file_location("auto_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


auto_validator = _load_module()


class FakeApi:
    def __init__(self, rows: list[dict[str, object]], fresh: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.fresh = fresh
        self.downloads: list[str] = []

    def list_submissions(self, status: str) -> list[dict[str, object]]:
        return self.rows

    def get_submission(self, submission_id: str) -> dict[str, object]:
        return self.fresh[submission_id]

    def download_bundle(self, submission_id: str, destination: Path) -> None:
        self.downloads.append(submission_id)
        destination.write_bytes(b"bundle")


def _config(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    suite_dir: Path | None | str = "default",
    suite_cache_root: Path | None = None,
) -> object:
    return auto_validator.Config(
        site="https://example.test",
        suite_dir=(tmp_path / "suite") if suite_dir == "default" else suite_dir,
        validator_secret="validator-super-secret",
        root_dir=tmp_path / "state",
        dry_run=dry_run,
        suite_cache_root=suite_cache_root,
    )


def _accepted_update() -> dict[str, object]:
    return {
        "status": "accepted",
        "projection": {"axes": {"coding": {"status": "not_measured"}}},
        "projection_object_sha256": "a" * 64,
        "raw_bundle_sha256": "b" * 64,
    }


def _daemon(
    tmp_path: Path,
    api: FakeApi,
    *,
    verify: Callable[..., dict[str, object]] | None = None,
    post: Callable[..., dict[str, object]] | None = None,
    append: Callable[..., object] | None = None,
    dry_run: bool = False,
    suite_dir: Path | None | str = "default",
    suite_cache_root: Path | None = None,
) -> object:
    return auto_validator.AutoValidator(
        _config(tmp_path, dry_run=dry_run, suite_dir=suite_dir, suite_cache_root=suite_cache_root),
        api=api,
        verify=verify or (lambda *args, **kwargs: _accepted_update()),
        post=post or (lambda *args, **kwargs: {"status": "accepted", "published": True}),
        append_log=append or (lambda **kwargs: None),
    )


def test_fifo_orders_oldest_created_or_uploaded_timestamp_first() -> None:
    rows = [
        {"submission_id": "new", "created_at": "2026-07-18T03:00:00Z"},
        {"submission_id": "old", "uploaded_at": "2026-07-18T01:00:00Z"},
        {"submission_id": "mid", "created_at": "2026-07-18T02:00:00Z"},
    ]
    assert [row["submission_id"] for row in auto_validator.sort_fifo(rows)] == ["old", "mid", "new"]


def test_lockfile_refuses_live_owner(tmp_path: Path) -> None:
    lock = auto_validator.PidLock(tmp_path / "lock.pid", pid=101, pid_alive=lambda pid: pid == 77)
    (tmp_path / "lock.pid").write_text("77", encoding="utf-8")
    with pytest.raises(auto_validator.AlreadyRunningError):
        lock.acquire()


def test_lockfile_replaces_stale_owner_with_warning(tmp_path: Path) -> None:
    messages: list[str] = []
    lock = auto_validator.PidLock(tmp_path / "lock.pid", pid=101, pid_alive=lambda _pid: False, log=messages.append)
    (tmp_path / "lock.pid").write_text("77", encoding="utf-8")
    lock.acquire()
    assert (tmp_path / "lock.pid").read_text(encoding="utf-8") == "101"
    assert any("stale" in message for message in messages)


def test_guard_file_skips_cycle_before_listing(tmp_path: Path) -> None:
    class GuardApi(FakeApi):
        def list_submissions(self, status: str) -> list[dict[str, object]]:
            raise AssertionError("guarded cycle must not call the API")

    daemon = _daemon(tmp_path, GuardApi([], {}))
    daemon.config.pause_file.parent.mkdir(parents=True)
    daemon.config.pause_file.touch()
    assert daemon.run_cycle(process_listing="") == "guarded"


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(1, 30), (2, 60), (3, 120), (4, 240), (5, 480), (6, 600), (20, 600)],
)
def test_backoff_schedule_is_exponential_and_capped(failures: int, expected: int) -> None:
    assert auto_validator.backoff_seconds(failures) == expected


def test_fifth_api_failure_writes_alert_with_scrubbed_error(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeApi([], {}))
    for _ in range(4):
        assert daemon.record_api_failure("validator-super-secret failed") is False
    assert daemon.record_api_failure("validator-super-secret failed") is True
    alert = daemon.config.alert_file.read_text(encoding="utf-8")
    assert "validator-super-secret" not in alert
    assert "[REDACTED]" in alert


def test_dry_run_verifies_but_posts_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    verified: list[str] = []

    def verify(*args: object, **kwargs: object) -> dict[str, object]:
        verified.append("yes")
        return _accepted_update()

    def post(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry-run must not post")

    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    daemon = _daemon(tmp_path, FakeApi([row], {"sub-1": row}), verify=verify, post=post, dry_run=True)
    assert daemon.run_cycle(process_listing="") == "ok"
    assert verified == ["yes"]
    assert not daemon.config.intent_file.exists()
    assert "dry-run would POST submission_id=sub-1" in capsys.readouterr().out


def test_status_change_skips_download_and_verify(tmp_path: Path) -> None:
    listed = {"submission_id": "sub-1", "status": "pending_verification"}
    fresh = {"submission_id": "sub-1", "status": "accepted"}
    api = FakeApi([listed], {"sub-1": fresh})
    daemon = _daemon(tmp_path, api, verify=lambda *args, **kwargs: pytest.fail("must not verify"))
    assert daemon.run_cycle(process_listing="") == "ok"
    assert api.downloads == []


class ContractValidationError(Exception):
    pass


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (json.JSONDecodeError("bad", "", 0), "bundle_unreadable"),
        (auto_validator.zipfile.BadZipFile("bad zip"), "bundle_unreadable"),
        (ContractValidationError("contract invalid"), "schema_violation"),
        (RuntimeError("scorer exploded"), "rescore_failed"),
        (LookupError("unexpected"), "internal_error"),
    ],
)
def test_exception_reason_mapping_is_bounded_and_traceback_free(error: Exception, expected: str) -> None:
    code, detail = auto_validator.map_rejection(error, validation_types=(ContractValidationError,))
    assert code == expected
    assert len(detail) <= 300
    assert "Traceback" not in detail


def test_rejection_detail_scrubs_paths_and_secret() -> None:
    error = RuntimeError("failed at C:\\Users\\Michael\\secret\\bundle.zip using validator-super-secret")
    _code, detail = auto_validator.map_rejection(error, secret="validator-super-secret")
    assert "Michael" not in detail
    assert "validator-super-secret" not in detail
    assert "[REDACTED]" in detail


def test_verify_exception_posts_terminal_rejection(tmp_path: Path) -> None:
    posted: list[dict[str, object]] = []
    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        verify=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rescore crash")),
        post=lambda _id, update: posted.append(update) or {"status": "rejected"},
    )
    assert daemon.run_cycle(process_listing="") == "ok"
    assert posted[0]["status"] == "rejected"
    assert posted[0]["operation"] == "initial_decision"
    assert posted[0]["reason_code"] == "rescore_failed"
    assert "projection" not in posted[0]


def test_rejection_post_failure_leaves_submission_for_next_cycle(tmp_path: Path) -> None:
    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    appended: list[str] = []
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        verify=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rescore crash")),
        post=lambda *args, **kwargs: (_ for _ in ()).throw(auto_validator.ApiError("post failed")),
        append=lambda **kwargs: appended.append("logged"),
    )
    assert daemon.run_cycle(process_listing="") == "retry"
    assert appended == []
    assert daemon.consecutive_api_failures == 1


def test_intent_is_written_before_post_and_startup_reconciles_terminal_state(tmp_path: Path) -> None:
    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    api = FakeApi([row], {"sub-1": row})
    daemon = _daemon(
        tmp_path,
        api,
        post=lambda *args, **kwargs: (_ for _ in ()).throw(auto_validator.ApiError("lost response")),
    )
    assert daemon.run_cycle(process_listing="") == "retry"
    records = [json.loads(line) for line in daemon.config.intent_file.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["intent"] == "auto_verify"
    assert records[0]["submission_id"] == "sub-1"
    assert records[0]["operation"] == "initial_decision"
    assert isinstance(records[0]["at"], str)

    reconciled: list[dict[str, object]] = []
    api.fresh["sub-1"] = {"submission_id": "sub-1", "status": "accepted", "projection_object_sha256": "a" * 64}
    restarted = _daemon(tmp_path, api, append=lambda **kwargs: reconciled.append(kwargs))
    restarted.reconcile_intents()
    assert reconciled[0]["action"] == "reconciled_auto_verify"
    outcomes = [json.loads(line) for line in restarted.config.intent_file.read_text(encoding="utf-8").splitlines()]
    assert any(record.get("outcome") == "reconciled" for record in outcomes)


def test_refresh_conflict_regets_retries_once_then_parks(tmp_path: Path) -> None:
    states = [
        {"submission_id": "sub-1", "state_revision": 4, "projection_object_sha256": "a" * 64},
        {"submission_id": "sub-1", "state_revision": 5, "projection_object_sha256": "b" * 64},
    ]

    class RefreshApi(FakeApi):
        def get_submission(self, submission_id: str) -> dict[str, object]:
            return states.pop(0)

    calls: list[dict[str, object]] = []

    def conflict(_submission_id: str, update: dict[str, object]) -> dict[str, object]:
        calls.append(update.copy())
        raise auto_validator.ConflictError("revision conflict")

    daemon = _daemon(tmp_path, RefreshApi([], {}), post=conflict)
    assert daemon.post_refresh("sub-1", _accepted_update()) == "parked"
    assert len(calls) == 2
    assert calls[0]["expected_state_revision"] == 4
    assert calls[1]["expected_state_revision"] == 5
    assert daemon.config.alert_file.exists()


def test_intent_precedes_post_and_outcome_precedes_decision_log(tmp_path: Path) -> None:
    events: list[str] = []
    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        post=lambda *args, **kwargs: events.append("post") or {"status": "accepted", "published": True},
        append=lambda **kwargs: events.append("decision"),
    )
    original_append = daemon.journal.append

    def tracked(record: dict[str, object]) -> None:
        events.append("intent" if "intent" in record else "outcome" if "outcome" in record else "decision-marker")
        original_append(record)

    daemon.journal.append = tracked
    assert daemon.run_cycle(process_listing="") == "ok"
    assert events == ["intent", "post", "outcome", "decision", "decision-marker"]


def test_validator_secret_is_scrubbed_from_every_log_line(tmp_path: Path) -> None:
    messages: list[str] = []
    daemon = auto_validator.AutoValidator(
        _config(tmp_path),
        api=FakeApi([], {}),
        log_sink=messages.append,
    )
    daemon.log("request failed: validator-super-secret")
    assert all("validator-super-secret" not in message for message in messages)


def test_accepted_but_unpublished_is_success(tmp_path: Path) -> None:
    decisions: list[dict[str, object]] = []
    row = {"submission_id": "sub-1", "status": "pending_verification", "origin": "community"}
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        post=lambda *args, **kwargs: {"status": "accepted", "published": False},
        append=lambda **kwargs: decisions.append(kwargs),
    )
    assert daemon.run_cycle(process_listing="") == "ok"
    assert daemon.consecutive_api_failures == 0
    assert decisions[0]["reason"] == "accepted"


def test_suite_resolution_uses_cached_bundle_for_submission_suite(tmp_path: Path) -> None:
    cache = tmp_path / "suites"
    bundle_dir = cache / "suite-v1-static-exec-5axis-v1" / ("a" * 64)
    bundle_dir.mkdir(parents=True)
    seen: list[Path] = []

    def verify(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs["suite_dir"])
        return _accepted_update()

    row = {
        "submission_id": "sub-1",
        "status": "pending_verification",
        "origin": "community",
        "suite_release_id": "suite-v1-static-exec-5axis-v1",
    }
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        verify=verify,
        suite_dir=None,
        suite_cache_root=cache,
    )
    assert daemon.run_cycle(process_listing="") == "ok"
    assert seen == [bundle_dir]


def test_suite_resolution_skips_not_rejects_when_bundle_missing(tmp_path: Path) -> None:
    posted: list[object] = []
    row = {
        "submission_id": "sub-1",
        "status": "pending_verification",
        "origin": "community",
        "suite_release_id": "suite-v1-full-exec-6axis-v1",
    }
    api = FakeApi([row], {"sub-1": row})
    daemon = _daemon(
        tmp_path,
        api,
        post=lambda *args, **kwargs: posted.append(args) or {"status": "accepted"},
        suite_dir=None,
        suite_cache_root=tmp_path / "suites",
    )
    assert daemon.run_cycle(process_listing="") == "ok"
    assert posted == []
    assert api.downloads == []


def test_suite_dir_override_wins_over_cache_resolution(tmp_path: Path) -> None:
    override = tmp_path / "explicit-suite"
    seen: list[Path] = []

    def verify(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs["suite_dir"])
        return _accepted_update()

    row = {
        "submission_id": "sub-1",
        "status": "pending_verification",
        "origin": "community",
        "suite_release_id": "suite-v1-static-exec-5axis-v1",
    }
    daemon = _daemon(
        tmp_path,
        FakeApi([row], {"sub-1": row}),
        verify=verify,
        suite_dir=override,
        suite_cache_root=tmp_path / "suites",
    )
    assert daemon.run_cycle(process_listing="") == "ok"
    assert seen == [override]


def test_allow_bench_concurrent_bypasses_process_guard_but_honors_pause(tmp_path: Path) -> None:
    row = {
        "submission_id": "sub-1",
        "status": "pending_verification",
        "origin": "community",
        "suite_release_id": "suite-v1-static-exec-5axis-v1",
    }
    daemon = auto_validator.AutoValidator(
        auto_validator.Config(
            site="https://example.test",
            suite_dir=tmp_path / "suite",
            validator_secret="validator-super-secret",
            root_dir=tmp_path / "state",
            allow_bench_concurrent=True,
        ),
        api=FakeApi([row], {"sub-1": row}),
        verify=lambda *args, **kwargs: _accepted_update(),
        post=lambda *args, **kwargs: {"status": "accepted", "published": True},
        append_log=lambda **kwargs: None,
    )
    assert daemon.run_cycle(process_listing="llama-server.exe  1234 running") == "ok"
    daemon.config.pause_file.parent.mkdir(parents=True, exist_ok=True)
    daemon.config.pause_file.touch()
    assert daemon.run_cycle(process_listing="") == "guarded"
