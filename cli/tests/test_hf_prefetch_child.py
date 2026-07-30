from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import localbench.hf_prefetch_child as child_mod
import localbench.cli as cli_mod
from localbench.cli import CacheTokenizerError

_SENTINEL = "LOCALBENCH_HF_PREFETCH_V1"


def _frame(capsys: pytest.CaptureFixture[str]) -> dict:
    out = capsys.readouterr().out
    frames = [line for line in out.splitlines() if line.startswith(_SENTINEL + " ")]
    assert len(frames) == 1, f"expected exactly one sentinel frame, got: {out!r}"
    return json.loads(frames[0][len(_SENTINEL) + 1 :])


def test_child_ok_frame_and_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given: snapshot_download succeeds in the child.
    def fake_snapshot_download(*, repo_id, allow_patterns, revision):
        assert (repo_id, allow_patterns, revision) == ("owner/model", ["*.json"], None)
        return "/hf/cache/models--owner--model/snapshots/abc"

    monkeypatch.setattr(child_mod, "_snapshot_download", fake_snapshot_download)

    # When / Then: one ok frame, exit 0.
    assert child_mod.main(["owner/model", json.dumps(["*.json"]), ""]) == 0
    assert _frame(capsys) == {
        "status": "ok",
        "path": "/hf/cache/models--owner--model/snapshots/abc",
    }


def test_child_maps_any_failure_to_error_frame_exit_one_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given: snapshot_download blows up with an untyped error.
    def fake_snapshot_download(**_kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(child_mod, "_snapshot_download", fake_snapshot_download)

    # When / Then: structured error frame, exit 1, no traceback on either stream.
    assert child_mod.main(["owner/model", json.dumps(["*.json"]), ""]) == 1
    captured = capsys.readouterr()
    frames = [l for l in captured.out.splitlines() if l.startswith(_SENTINEL + " ")]
    payload = json.loads(frames[0][len(_SENTINEL) + 1 :])
    assert payload["status"] == "error"
    assert payload["kind"] == "other"
    assert "connection reset by peer" in payload["message"]
    assert "Traceback" not in captured.out + captured.err


def test_child_bad_argv_is_a_protocol_error_frame_not_a_crash(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: malformed argv (bad JSON for allow_patterns) — argv parsing must sit
    # INSIDE the protocol boundary (oracle BLOCKER 1).
    code = child_mod.main(["owner/model", "{not json", ""])

    # Then: still a structured frame, exit 1, no traceback.
    assert code == 1
    payload = _frame(capsys)
    assert payload["status"] == "error"
    assert payload["kind"] == "protocol"


class _FakeCompleted:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _ok_frame(path: str = "/snap/abc") -> str:
    return _SENTINEL + " " + json.dumps({"status": "ok", "path": path}) + "\n"


def test_parent_strips_offline_pins_uses_isolated_flags_and_returns_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the parent process is (realistically) pinned offline.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return _FakeCompleted(_ok_frame())

    monkeypatch.setattr(cli_mod.subprocess, "run", fake_run)

    # When: the parent requests a prefetch.
    path = cli_mod._hf_snapshot_download("owner/model", ["*.json"], revision="deadbeef")

    # Then: child runs -E -P -m localbench.hf_prefetch_child (CWD/PYTHONPATH hijack
    # closed, oracle BLOCKER 3), offline pins stripped, progress bars off, stdin null.
    assert path == "/snap/abc"
    command = seen["command"]
    assert command[1:5] == ["-E", "-P", "-m", "localbench.hf_prefetch_child"]
    assert command[5:] == ["owner/model", json.dumps(["*.json"]), "deadbeef"]
    env = seen["kwargs"]["env"]
    assert "HF_HUB_OFFLINE" not in env
    assert "TRANSFORMERS_OFFLINE" not in env
    assert env["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    assert seen["kwargs"]["stdin"] == subprocess.DEVNULL
    assert seen["kwargs"]["encoding"] == "utf-8"
    assert seen["kwargs"]["errors"] == "replace"


@pytest.mark.parametrize(
    "bad_stdout",
    (
        "",  # nothing at all
        "random noise\n",  # no sentinel frame
        _SENTINEL + " null\n",  # JSON scalar, not an object (oracle BLOCKER 1)
        _SENTINEL + " [1,2]\n",  # JSON array
        _SENTINEL + ' {"status": "ok"}\n',  # ok without path
        _ok_frame() + _ok_frame(),  # duplicate frames
        "warning: something\n" + _SENTINEL + " {not json}\n",  # malformed frame
    ),
)
def test_parent_maps_protocol_violations_to_fixed_single_line_error(
    bad_stdout: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_mod.subprocess, "run", lambda *a, **k: _FakeCompleted(bad_stdout))

    with pytest.raises(CacheTokenizerError) as excinfo:
        cli_mod._hf_snapshot_download("owner/model", ["*.json"])
    message = str(excinfo.value)
    assert "\n" not in message
    assert "Traceback" not in message
    assert "cache-tokenizer" in message  # fixed protocol-failure remediation


def test_parent_never_copies_child_stderr_tracebacks_into_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the child died before emitting a frame, stderr full of traceback.
    monkeypatch.setattr(
        cli_mod.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(
            "",
            stderr="Traceback (most recent call last):\n  boom\n",
            returncode=1,
        ),
    )

    # When / Then: fixed message only — raw child stderr never reaches the operator (oracle BLOCKER 1).
    with pytest.raises(CacheTokenizerError) as excinfo:
        cli_mod._hf_snapshot_download("owner/model", ["*.json"])
    assert "Traceback" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("kind", "expected_check"),
    (
        ("auth", lambda msg: msg == cli_mod._hf_auth_error_message("owner/model")),
        ("not_found", lambda msg: "not found or is inaccessible" in msg),
        ("import", lambda msg: msg == cli_mod._HF_CACHE_EXTRA_ERROR),
        ("network", lambda msg: "dns fail" in msg),
    ),
)
def test_parent_maps_child_error_kinds(
    kind: str,
    expected_check,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _SENTINEL + " " + json.dumps(
        {"status": "error", "kind": kind, "message": "dns fail"}
    ) + "\n"
    monkeypatch.setattr(
        cli_mod.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(frame, returncode=1),
    )

    with pytest.raises(CacheTokenizerError) as excinfo:
        cli_mod._hf_snapshot_download("owner/model", ["*.json"])
    assert expected_check(str(excinfo.value))


def test_parent_maps_oserror_and_timeout_to_typed_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # OSError at spawn (oracle BLOCKER 1: subprocess.run can raise OSError).
    def raise_oserror(*_a, **_k):
        raise OSError("exec failed")

    monkeypatch.setattr(cli_mod.subprocess, "run", raise_oserror)
    with pytest.raises(CacheTokenizerError):
        cli_mod._hf_snapshot_download("owner/model", ["*.json"])

    # Timeout.
    def raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="child", timeout=120)

    monkeypatch.setattr(cli_mod.subprocess, "run", raise_timeout)
    with pytest.raises(CacheTokenizerError) as excinfo:
        cli_mod._hf_snapshot_download("owner/model", ["*.json"])
    assert "timed out" in str(excinfo.value)


def test_child_invocation_is_immune_to_cwd_and_pythonpath_shadowing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a hostile working directory AND a poisoned PYTHONPATH, each containing
    # a shadow localbench.hf_prefetch_child that emits a SHADOW frame (oracle BLOCKER 3).
    for root in (tmp_path / "cwd", tmp_path / "pypath"):
        shadow_pkg = root / "localbench"
        shadow_pkg.mkdir(parents=True)
        (shadow_pkg / "__init__.py").write_text("", encoding="utf-8")
        (shadow_pkg / "hf_prefetch_child.py").write_text(
            'print("LOCALBENCH_HF_PREFETCH_V1 {\\"status\\": \\"error\\", '
            '\\"kind\\": \\"other\\", \\"message\\": \\"SHADOW EXECUTED\\"}")\n',
            encoding="utf-8",
        )
    monkeypatch.chdir(tmp_path / "cwd")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "pypath"))
    # Bad argv against the REAL module yields a protocol-kind frame; the shadow
    # would yield "SHADOW EXECUTED".
    import subprocess as sp
    import sys as real_sys

    completed = sp.run(
        [
            real_sys.executable,
            "-E",
            "-P",
            "-m",
            "localbench.hf_prefetch_child",
            "r",
            "{bad",
            "",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "SHADOW EXECUTED" not in completed.stdout
    assert '"kind": "protocol"' in completed.stdout
