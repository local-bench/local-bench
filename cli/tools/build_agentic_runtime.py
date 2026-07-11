"""Build C1 twice inside WSL, accept only byte-identical tar.xz output, then sign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import tarfile
from pathlib import Path

from localbench._types import JsonObject
from localbench.appliance.manifest import (
    MANIFEST_SCHEMA,
    PINNED_RUNTIME_ID,
    signed_manifest,
)
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.submissions.canon import canonical_json_hash, write_json_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--signing-key", type=Path, default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    key = args.signing_key or _key_from_env()
    config = _read_object(args.config)
    _validate_config(config)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="localbench-runtime-build-") as temporary:
        root = Path(temporary)
        first = root / "first.tar.xz"
        second = root / "second.tar.xz"
        _build_once(config, first)
        _build_once(config, second)
        if _sha(first) != _sha(second) or first.read_bytes() != second.read_bytes():
            raise RuntimeError(
                "C1 reproducibility gate failed: double-build archives differ"
            )
        _scan_no_protected_content(first)
        artifact = args.out / f"localbench-agentic-runtime-{PINNED_RUNTIME_ID}.tar.xz"
        if artifact.exists() and _sha(artifact) != _sha(first):
            raise RuntimeError(
                "immutable runtime ID already exists with different rootfs bytes"
            )
        os.replace(first, artifact)
    sbom: JsonObject = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "operating-system", "name": PINNED_RUNTIME_ID}
        },
        "components": [
            {
                "type": "library",
                "name": str(package).split("=", 1)[0],
                "version": str(package).split("=", 1)[1],
            }
            for package in config["apt_packages"]
        ]
        + [
            {
                "type": "application",
                "name": "local-bench-ai-worker",
                "version": str(_object(config["worker"])["version"]),
                "hashes": [
                    {
                        "alg": "SHA-256",
                        "content": str(_object(config["worker"])["sha256"]),
                    }
                ],
            }
        ],
    }
    provenance: JsonObject = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": artifact.name, "digest": {"sha256": _sha(artifact)}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://local-bench.ai/buildtypes/agentic-rootfs-v1",
                "externalParameters": {
                    "runtime_id": PINNED_RUNTIME_ID,
                    "inputs_sha256": canonical_json_hash(config),
                },
                "resolvedDependencies": [
                    {
                        "uri": _object(config["base"])["url"],
                        "digest": {"sha256": _object(config["base"])["sha256"]},
                    },
                    {
                        "uri": _object(config["apt_snapshot"])["url"],
                        "digest": {
                            "sha256": _object(config["apt_snapshot"])["indexes_sha256"]
                        },
                    },
                ],
            },
            "runDetails": {
                "builder": {"id": "cli/tools/build_agentic_runtime.py"},
                "metadata": {
                    "double_build_byte_identical": True,
                    "protected_content_scan": "passed-zero-appworld-protected-content",
                },
            },
        },
    }
    sbom_path = args.out / f"{PINNED_RUNTIME_ID}.sbom.json"
    provenance_path = args.out / f"{PINNED_RUNTIME_ID}.provenance.json"
    write_json_file(sbom_path, sbom)
    write_json_file(provenance_path, provenance)
    payload = _manifest_payload(config, artifact, sbom_path, provenance_path)
    manifest_path = args.out / "manifest.json"
    document = signed_manifest(payload, key)
    if manifest_path.exists():
        existing = _read_object(manifest_path)
        if existing != document:
            raise RuntimeError(
                "immutable runtime ID already exists with a different manifest"
            )
    write_json_file(manifest_path, document)
    return 0


def _build_once(config: JsonObject, destination: Path) -> None:
    script = Path(__file__).with_name("runtime_rootfs_build.sh")
    wsl_config = dict(config)
    wsl_config["worker_wheel_wsl_path"] = _wsl_path(
        Path(str(config["worker_wheel_windows_path"]))
    )
    wsl_config["dependency_lock_wsl_path"] = _wsl_path(
        Path(str(config["dependency_lock_windows_path"]))
    )
    wsl_config["wheelhouse_wsl_path"] = _wsl_path(
        Path(str(config["wheelhouse_windows_path"]))
    )
    completed = subprocess.run(
        [
            "wsl.exe",
            "--distribution",
            str(config["builder_wsl_distro"]),
            "--exec",
            "/bin/bash",
            _wsl_path(script),
            json.dumps(wsl_config, sort_keys=True, separators=(",", ":")),
            _wsl_path(destination),
        ],
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"WSL rootfs build failed with exit {completed.returncode}")


def _manifest_payload(
    config: JsonObject, artifact: Path, sbom: Path, provenance: Path
) -> JsonObject:
    contract = load_execution_contract()
    contract_payload = _object(contract["payload"])
    identity = _object(contract_payload["task_identity"])
    worker = _object(config["worker"])
    return {
        "schema": MANIFEST_SCHEMA,
        "runtime_id": PINNED_RUNTIME_ID,
        "rootfs": {
            "url": str(config["artifact_url"]),
            "sha256": _sha(artifact),
            "size_bytes": artifact.stat().st_size,
            "uncompressed_size_bytes": _xz_uncompressed_size(artifact),
            "format": "tar.xz",
            "compressor": "xz 5.4.5",
            "compressor_flags": "--threads=1 --check=crc64 -9e",
        },
        "worker": worker,
        "python": config["python"],
        "bubblewrap": config["bubblewrap"],
        "appworld": config["appworld"],
        "execution_contract_sha256": contract["payload_sha256"],
        "task_identity": {
            field: identity[field]
            for field in (
                "ordered_task_ids",
                "ordered_task_ids_sha256",
                "selection_recipe_sha256",
                "semantic_task_sha256",
            )
        },
        "canary_suite_id": "localbench-appliance-canaries-v1",
        "cli_compatibility": {"minimum": "0.4.0", "maximum_exclusive": "0.5.0"},
        "critical_hashes": _derive_critical_hashes(artifact, config),
        "trust": config["trust"],
        "disk_requirements": config["disk_requirements"],
        "provenance": {"sha256": _sha(provenance), "url": config["provenance_url"]},
        "sbom": {"sha256": _sha(sbom), "url": config["sbom_url"]},
        "measured_artifact_size_bytes": artifact.stat().st_size,
    }


def _validate_config(config: JsonObject) -> None:
    required = {
        "runtime_id",
        "builder_wsl_distro",
        "base",
        "apt_snapshot",
        "apt_packages",
        "worker_wheel_windows_path",
        "dependency_lock_windows_path",
        "dependency_lock_sha256",
        "wheelhouse_windows_path",
        "wheelhouse_sha256",
        "worker",
        "python",
        "bubblewrap",
        "appworld",
        "trust",
        "disk_requirements",
        "artifact_url",
        "provenance_url",
        "sbom_url",
    }
    missing = required - config.keys()
    if missing:
        raise ValueError(f"build config missing {sorted(missing)}")
    if config["runtime_id"] != PINNED_RUNTIME_ID:
        raise ValueError("build config runtime_id differs from CLI pin")
    for key in ("base", "worker"):
        value = _object(config[key])
        if not isinstance(value.get("sha256"), str) or len(str(value["sha256"])) != 64:
            raise ValueError(f"{key}.sha256 must be pinned")
    packages = config["apt_packages"]
    if (
        not isinstance(packages, list)
        or not packages
        or any("=" not in str(item) for item in packages)
    ):
        raise ValueError("apt_packages must contain exact name=version pins")


def _scan_no_protected_content(archive: Path) -> None:
    command = [
        "wsl.exe",
        "--exec",
        "/bin/bash",
        "-lc",
        'set -o pipefail; xz -dc "$1" | tar -tf - | '
        "grep -Eai '(^|/)(appworld/data|data/tasks|ground[_-]?truth|test_normal|test_challenge)(/|$)'",
        "localbench-scan",
        _wsl_path(archive),
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode == 0:
        raise RuntimeError(
            "licensing gate failed: AppWorld protected content path found"
        )
    if result.returncode != 1:
        raise RuntimeError("licensing gate scan failed to inspect archive")


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive[:1].lower()
    return f"/mnt/{drive}/{resolved.as_posix()[3:]}"


def _key_from_env() -> Path:
    value = os.environ.get("LOCALBENCH_RUNTIME_ROOT_SIGNING_KEY")
    if not value:
        raise ValueError(
            "pass --signing-key or set LOCALBENCH_RUNTIME_ROOT_SIGNING_KEY"
        )
    return Path(value)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _xz_uncompressed_size(path: Path) -> int:
    import lzma

    total = 0
    with lzma.open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
    return total


def _derive_critical_hashes(archive: Path, config: JsonObject) -> JsonObject:
    with tarfile.open(archive, "r:xz") as tar:
        members = tar.getmembers()
        entrypoint = _member_sha(tar, members, "opt/localbench/bin/localbench-worker")
        bwrap = _member_sha(tar, members, "usr/bin/bwrap")
        wsl_conf = _member_sha(tar, members, "etc/wsl.conf")
        metadata = next(
            member
            for member in members
            if "local_bench_ai-" in _clean_name(member.name)
            and _clean_name(member.name).endswith(".dist-info/METADATA")
        )
        dist_root = _clean_name(metadata.name).rsplit("/", 1)[0]
        entries: list[list[object]] = []
        for member in sorted(members, key=lambda item: _clean_name(item.name)):
            name = _clean_name(member.name)
            if name == dist_root:
                continue
            if not name.startswith(dist_root + "/"):
                continue
            relative = name[len(dist_root) + 1 :]
            if member.issym():
                entries.append([relative, "symlink", member.linkname])
            elif member.isfile():
                stream = tar.extractfile(member)
                if stream is None:
                    raise RuntimeError(f"unable to read {name}")
                data = stream.read()
                entries.append(
                    [relative, "file", hashlib.sha256(data).hexdigest(), len(data)]
                )
            elif member.isdir():
                entries.append([relative, "dir"])
    appworld = _object(config["appworld"])
    return {
        "worker_entrypoint_sha256": entrypoint,
        "worker_wheel_tree_sha256": hashlib.sha256(
            json.dumps(
                entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest(),
        "bubblewrap_sha256": bwrap,
        "appworld_installed_tree_sha256": appworld["installed_tree_sha256"],
        "appworld_data_tree_sha256": appworld["data_tree_sha256"],
        "wsl_conf_sha256": wsl_conf,
    }


def _member_sha(
    tar: tarfile.TarFile, members: list[tarfile.TarInfo], suffix: str
) -> str:
    member = next(item for item in members if _clean_name(item.name) == suffix)
    stream = tar.extractfile(member)
    if stream is None:
        raise RuntimeError(f"unable to read {suffix}")
    return hashlib.sha256(stream.read()).hexdigest()


def _clean_name(name: str) -> str:
    return name.removeprefix("./")


def _read_object(path: Path) -> JsonObject:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("JSON object required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
