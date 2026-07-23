"""setup-agentic must self-heal a mutated managed runtime instead of dead-ending.

Found 2026-07-24: a mutated runtime made plain `setup-agentic` fail with the very
error whose advice was to run plain `setup-agentic` — circular, with the working
remove-and-rebuild sequence undiscoverable. Detection stays fail-closed; only the
recovery path is under test here.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from localbench.appliance.provisioner import PINNED_RUNTIME_ID, ProvisioningError
from localbench.cli import _ensure_active_with_self_heal, _resume_campaign_missing_error


class MutatedThenHealthyProvisioner:
    """Fails integrity once, succeeds after the mutated runtime is removed."""

    def __init__(self) -> None:
        self.removed: list[tuple[str, bool]] = []
        self._mutated = True

    def ensure_active(self, runtime_id: str):
        if self._mutated:
            raise ProvisioningError(
                "runtime_mutated", "critical hash mismatch",
                "Reprovision: run localbench setup-agentic --reprovision",
            )
        return {"runtime_id": runtime_id}

    def remove(self, runtime_id: str, *, confirm_active: bool = False) -> None:
        assert runtime_id == PINNED_RUNTIME_ID, "self-heal must only remove the pinned managed runtime"
        self.removed.append((runtime_id, confirm_active))
        self._mutated = False


class OtherErrorProvisioner:
    def ensure_active(self, runtime_id: str):
        raise ProvisioningError("runtime_missing", "no distro", "Run localbench setup-agentic")

    def remove(self, runtime_id: str, *, confirm_active: bool = False) -> None:
        raise AssertionError("must not remove on non-mutation errors")


def test_reprovision_flag_removes_and_rebuilds() -> None:
    provisioner = MutatedThenHealthyProvisioner()
    identity = _ensure_active_with_self_heal(provisioner, reprovision=True)
    assert identity == {"runtime_id": PINNED_RUNTIME_ID}
    assert provisioner.removed == [(PINNED_RUNTIME_ID, True)]


def test_tty_accept_removes_and_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    provisioner = MutatedThenHealthyProvisioner()
    monkeypatch.setattr("localbench.cli.sys.stdin", io.StringIO())
    monkeypatch.setattr("localbench.cli.sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    identity = _ensure_active_with_self_heal(provisioner, reprovision=False)
    assert identity == {"runtime_id": PINNED_RUNTIME_ID}
    assert provisioner.removed == [(PINNED_RUNTIME_ID, True)]


def test_non_tty_declined_names_exact_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    provisioner = MutatedThenHealthyProvisioner()
    monkeypatch.setattr(
        "localbench.cli.sys.stdin", SimpleNamespace(isatty=lambda: False)
    )
    with pytest.raises(ProvisioningError) as excinfo:
        _ensure_active_with_self_heal(provisioner, reprovision=False)
    message = str(excinfo.value)
    assert excinfo.value.code == "runtime_mutated"
    assert "localbench setup-agentic --reprovision" in message
    assert f"--remove {PINNED_RUNTIME_ID} --confirm-active" in message
    assert provisioner.removed == []


def test_tty_decline_leaves_runtime_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    provisioner = MutatedThenHealthyProvisioner()
    monkeypatch.setattr(
        "localbench.cli.sys.stdin", SimpleNamespace(isatty=lambda: True)
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    with pytest.raises(ProvisioningError):
        _ensure_active_with_self_heal(provisioner, reprovision=False)
    assert provisioner.removed == []


def test_non_mutation_errors_pass_through_untouched() -> None:
    with pytest.raises(ProvisioningError) as excinfo:
        _ensure_active_with_self_heal(OtherErrorProvisioner(), reprovision=True)
    assert excinfo.value.code == "runtime_missing"


def test_resume_without_campaign_is_a_typed_usage_error(tmp_path) -> None:
    missing = _resume_campaign_missing_error(tmp_path / "no-such-run")
    assert missing is not None
    assert "no resumable campaign" in missing
    assert "campaign.json not found" in missing
    assert "Errno" not in missing

    run_dir = tmp_path / "real-run"
    run_dir.mkdir()
    (run_dir / "campaign.json").write_text("{}", encoding="utf-8")
    assert _resume_campaign_missing_error(run_dir) is None
