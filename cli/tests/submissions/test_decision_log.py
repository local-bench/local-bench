from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.cli import main
from localbench.submissions.decision_log import (
    GENESIS_PREV_SHA256,
    append_decision_log,
    decision_log_path,
    verify_log,
)


def test_decision_log_append_verify_round_trip_and_genesis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an isolated localbench home without an ops log key.
    _isolate_home(monkeypatch, tmp_path)

    # When: two maintainer decisions are appended and the CLI verifies the chain.
    first = append_decision_log(
        actor="maintainer",
        action="admin_verify",
        submission_id="sub_1",
        reason="accepted",
        extra={"status": "accepted"},
    )
    second = append_decision_log(
        actor="maintainer",
        action="admin_decision",
        submission_id="sub_1",
        reason="publish_state=preview",
        extra={"publish_state": "preview"},
    )
    code = main(["submit", "log", "verify"])

    # Then: the genesis link, sequence, signatures, and CLI verifier are all valid.
    output = capsys.readouterr().out
    assert first.seq == 1
    assert first.prev_entry_sha256 == GENESIS_PREV_SHA256
    assert second.seq == 2
    assert verify_log().ok
    assert code == 0
    assert "decision_log ok entries=2" in output
    assert (tmp_path / "home" / ".localbench" / "ops_log_ed25519.pem").exists()


def test_decision_log_detects_chain_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a two-entry decision log.
    _isolate_home(monkeypatch, tmp_path)
    append_decision_log(
        actor="maintainer",
        action="admin_verify",
        submission_id="sub_1",
        reason="accepted",
        extra={},
    )
    append_decision_log(
        actor="maintainer",
        action="admin_decision",
        submission_id="sub_1",
        reason="publish_state=published",
        extra={},
    )

    # When: the first line is edited after it was signed.
    path = decision_log_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["reason"] = "tampered"
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Then: verification fails before the altered chain can be trusted.
    result = verify_log()
    assert not result.ok
    assert result.error is not None
    assert "signature" in result.error or "hash chain" in result.error


def test_decision_log_detects_signature_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a signed decision log entry.
    _isolate_home(monkeypatch, tmp_path)
    append_decision_log(
        actor="maintainer",
        action="admin_verify",
        submission_id="sub_1",
        reason="accepted",
        extra={},
    )

    # When: only the signature is changed.
    path = decision_log_path()
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    line["sig"] = "00" + line["sig"][2:]
    path.write_text(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    # Then: signature verification fails.
    result = verify_log()
    assert not result.ok
    assert result.error is not None
    assert "signature" in result.error


def test_decision_log_show_tail_omits_signatures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: two log entries exist.
    _isolate_home(monkeypatch, tmp_path)
    append_decision_log(actor="maintainer", action="admin_verify", submission_id="sub_1", reason="accepted", extra={})
    append_decision_log(
        actor="maintainer",
        action="admin_decision",
        submission_id="sub_2",
        reason="publish_state=preview",
        extra={"publish_state": "preview"},
    )

    # When: the CLI pretty-prints the tail.
    code = main(["submit", "log", "show", "--tail", "1"])

    # Then: it shows the latest operational fields without dumping signatures.
    output = capsys.readouterr().out
    assert code == 0
    assert "2 admin_decision sub_2 maintainer publish_state=preview" in output
    assert "sig" not in output
    assert "sub_1" not in output


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("LOCALBENCH_HOME", raising=False)
