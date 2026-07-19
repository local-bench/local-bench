from __future__ import annotations

import hashlib

import pytest

from localbench._types import JsonObject
from localbench.scoring.agentic_exec import wsl_worker
from localbench.scoring.agentic_exec.sandbox import FINALIZATION_PROVENANCE
from localbench.scoring.agentic_exec.wsl_bridge import provenance_from_identity
from localbench.submissions.canon import canonical_json_bytes


def _fixed_wsl_identity() -> JsonObject:
    return {
        "wsl_kernel": "5.15.0-microsoft-standard-WSL2",
        "wsl_distro": "Ubuntu-24.04",
        "wsl_os_release": "Ubuntu 24.04 LTS",
        "venv_path": "/opt/localbench/venv",
        "venv_path_sha256": "1" * 64,
        "bwrap_path": "/usr/bin/bwrap",
        "bwrap_sha256": "2" * 64,
        "bwrap_version": "bubblewrap 0.9.0",
        "appworld_root": "/home/lbworker/appworld",
        "appworld_root_path_sha256": "3" * 64,
        "appworld_root_under_mnt": False,
        "appworld_root_filesystem": "ext4",
        "localbench_distribution_version": "0.4.3",
        "worker_content_sha256": "4" * 64,
    }


def test_windows_wsl_provenance_bytes_remain_unchanged() -> None:
    identity = _fixed_wsl_identity()
    published = {
        key: value
        for key, value in identity.items()
        if key not in {"venv_path", "bwrap_path", "appworld_root"}
    }
    expected = {
        "topology": {
            "scorecard_assembly": "single-campaign-no-merge",
            "model_call_location": "windows_campaign_process",
        },
        "wsl_identity": published,
        "agentic_sandbox_identity": {
            "bubblewrap_sha256": "2" * 64,
            "bubblewrap_version": "bubblewrap 0.9.0",
            "appworld_root_path_sha256": "3" * 64,
            "appworld_root_filesystem": "ext4",
        },
        "single_campaign_integrity": {"merge_step_used": False},
        "agentic_verdict_channel": {
            **FINALIZATION_PROVENANCE,
            "trust_note": "host-derived+direct-finalize-v1",
        },
    }

    assert canonical_json_bytes(
        provenance_from_identity(identity)
    ) == canonical_json_bytes(expected)


def test_windows_wsl_worker_identity_bytes_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCALBENCH_RUNTIME_TOPOLOGY", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    monkeypatch.setattr(
        wsl_worker.platform,
        "release",
        lambda: "5.15.0-microsoft-standard-WSL2",
    )
    monkeypatch.setattr(wsl_worker.platform, "python_version", lambda: "3.12.3")
    monkeypatch.setattr(wsl_worker.sys, "prefix", "/opt/localbench/venv")
    monkeypatch.setattr(wsl_worker, "resolve_bwrap", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(wsl_worker, "_package_version", lambda _name: "0.1.0")
    monkeypatch.setattr(
        wsl_worker,
        "_os_release",
        lambda: {"ID": "ubuntu", "PRETTY_NAME": "Ubuntu 24.04 LTS"},
    )
    monkeypatch.setattr(wsl_worker, "_file_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(wsl_worker, "_command_output", lambda _argv: "bubblewrap 0.9.0")
    monkeypatch.setattr(wsl_worker, "_filesystem_type", lambda _path: "ext4")
    monkeypatch.setattr(wsl_worker, "_verified_appworld_tree_sha256", lambda: "b" * 64)
    monkeypatch.setattr(
        wsl_worker,
        "worker_implementation_identity",
        lambda: {
            "localbench_distribution_version": "0.4.3",
            "worker_content_sha256": "c" * 64,
        },
    )

    def text_sha(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    expected = {
        "localbench_distribution_version": "0.4.3",
        "worker_content_sha256": "c" * 64,
        "wsl_kernel": "5.15.0-microsoft-standard-WSL2",
        "wsl_distro": "Ubuntu-24.04",
        "wsl_os_release": "Ubuntu 24.04 LTS",
        "appworld_root_under_mnt": False,
        "python_version": "3.12.3",
        "venv_path": "/opt/localbench/venv",
        "venv_path_sha256": text_sha("/opt/localbench/venv"),
        "worker_entrypoint": "localbench.scoring.agentic_exec.wsl_worker",
        "bwrap_path": "/usr/bin/bwrap",
        "bwrap_sha256": "a" * 64,
        "bwrap_version": "bubblewrap 0.9.0",
        "appworld_root": "/home/lbworker/appworld",
        "appworld_root_path_sha256": text_sha("/home/lbworker/appworld"),
        "appworld_root_filesystem": "ext4",
        "appworld_version": "0.1.0",
        "appworld_package_sha256": "b" * 64,
        "env_pins": {"PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C.UTF-8"},
    }

    identity = wsl_worker.collect_identity("/home/lbworker/appworld")

    assert canonical_json_bytes(identity) == canonical_json_bytes(expected)


def test_native_worker_identity_omits_wsl_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setenv("LOCALBENCH_RUNTIME_TOPOLOGY", "native-linux-bubblewrap")
    monkeypatch.setattr(
        wsl_worker.platform,
        "release",
        lambda: "5.15.0-microsoft-standard-WSL2",
    )
    monkeypatch.setattr(wsl_worker.platform, "python_version", lambda: "3.12.3")
    monkeypatch.setattr(wsl_worker.sys, "prefix", "/opt/localbench/venv")
    monkeypatch.setattr(wsl_worker, "resolve_bwrap", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(wsl_worker, "_package_version", lambda _name: "0.1.0")
    monkeypatch.setattr(
        wsl_worker,
        "_os_release",
        lambda: {"ID": "ubuntu", "PRETTY_NAME": "Ubuntu 24.04 LTS"},
    )
    monkeypatch.setattr(wsl_worker, "_file_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(wsl_worker, "_command_output", lambda _argv: "bubblewrap 0.9.0")
    monkeypatch.setattr(wsl_worker, "_filesystem_type", lambda _path: "ext4")
    monkeypatch.setattr(wsl_worker, "_verified_appworld_tree_sha256", lambda: "b" * 64)
    monkeypatch.setattr(
        wsl_worker,
        "worker_implementation_identity",
        lambda: {
            "localbench_distribution_version": "0.4.3",
            "worker_content_sha256": "c" * 64,
        },
    )

    identity = wsl_worker.collect_identity("/home/lbworker/appworld")

    assert identity["runtime_topology"] == "native-linux-bubblewrap"
    assert identity["linux_kernel"] == "5.15.0-microsoft-standard-WSL2"
    assert identity["linux_os_release"] == "Ubuntu 24.04 LTS"
    assert "wsl_kernel" not in identity
    assert "wsl_distro" not in identity
    assert "wsl_os_release" not in identity
    assert "appworld_root_under_mnt" not in identity


def test_native_provenance_uses_native_identity_block() -> None:
    identity = {
        **_fixed_wsl_identity(),
        "runtime_topology": "native-linux-bubblewrap",
        "linux_kernel": "6.8.0-native",
        "linux_os_release": "Ubuntu 24.04 LTS",
    }
    for key in (
        "wsl_kernel",
        "wsl_distro",
        "wsl_os_release",
        "appworld_root_under_mnt",
    ):
        identity.pop(key, None)

    provenance = provenance_from_identity(identity)

    assert provenance["topology"]["model_call_location"] == "linux_campaign_process"
    assert (
        provenance["topology"]["agentic_worker_location"] == "native_rootfs_bubblewrap"
    )
    assert "native_linux_identity" in provenance
    assert "wsl_identity" not in provenance
    assert provenance["native_linux_identity"]["linux_kernel"] == "6.8.0-native"
