"""Build C1 twice and emit an unsigned canonical offline-signing bundle."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import posixpath
import subprocess
import shutil
import tempfile
import tarfile
from pathlib import Path

import jsonschema

from localbench._types import JsonObject
from localbench.appliance.manifest import (
    MANIFEST_SCHEMA,
    PINNED_RUNTIME_ID,
)
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.submissions.canon import canonical_json_hash, write_json_file
from release_scanner import generate_exact_digest_allowlist, scan_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--retain-failed-builds", action="store_true")
    args = parser.parse_args()
    config = _read_object(args.config)
    _validate_config(config)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="localbench-runtime-build-") as temporary:
        root = Path(temporary)
        first = root / "first.tar.xz"
        second = root / "second.tar.xz"
        _build_once(config, first)
        _build_once(config, second)
        first_sha, second_sha = _sha(first), _sha(second)
        if first_sha != second_sha or first.read_bytes() != second.read_bytes():
            write_json_file(args.out / "failed-double-build.json", {"first_sha256": first_sha, "second_sha256": second_sha, "byte_identical": False})
            if args.retain_failed_builds:
                shutil.copy2(first, args.out / "failed-first.tar.xz")
                shutil.copy2(second, args.out / "failed-second.tar.xz")
            raise RuntimeError(
                "C1 reproducibility gate failed: double-build archives differ"
            )
        write_json_file(
            args.out / "double-build.json",
            {
                "schema": "localbench.runtime_double_build.v1",
                "first_archive_sha256": first_sha,
                "second_archive_sha256": second_sha,
                "byte_comparison": "identical",
            },
        )
        if args.retain_failed_builds:
            shutil.copy2(first, args.out / "scan-candidate.tar.xz")
        exact_policy = _read_object(
            Path(__file__).parents[1] / "runtime" / "rootfs-exact-file-allowlist-v1.json"
        )
        generated_allowlist = generate_exact_digest_allowlist(
            first,
            rootfs_id=str(exact_policy["rootfs_id"]),
            residue_justifications={
                str(path): str(reason)
                for path, reason in _object(exact_policy["residue_justifications"]).items()
            },
            max_residue_files=int(exact_policy["max_residue_files"]),
        )
        write_json_file(args.out / "generated-rootfs-exact-file-allowlist.json", generated_allowlist)
        scan_report = scan_release(
            first,
            allowed_top_levels={"bin", "bin.usr-is-merged", "boot", "dev", "etc", "home", "lib", "lib.usr-is-merged", "lib64", "media", "mnt", "opt", "proc", "root", "run", "sbin", "sbin.usr-is-merged", "snap", "srv", "sys", "tmp", "usr", "var"},
            expected_packages=set(
                json.loads(
                    (
                        Path(__file__).parents[1]
                        / "runtime"
                        / "rootfs-package-allowlist-v1.json"
                    ).read_text(encoding="utf-8")
                )["packages"]
            ),
            exact_digest_allowlist=_object(generated_allowlist["files"]),
            allowlist_rootfs_id=str(generated_allowlist["rootfs_id"]),
            rootfs_id=PINNED_RUNTIME_ID,
            sandbox_wsl_distro=str(config["builder_wsl_distro"]),
        )
        final_artifact = args.out / f"localbench-agentic-runtime-{PINNED_RUNTIME_ID}.tar.xz"
        if final_artifact.exists() and _sha(final_artifact) != first_sha:
            raise RuntimeError(
                "immutable runtime ID already exists with different rootfs bytes"
            )
        artifact = args.out / f".{final_artifact.name}.candidate"
        os.replace(first, artifact)
    sbom: JsonObject = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "operating-system", "name": PINNED_RUNTIME_ID}
        },
        "components": _complete_sbom_components(artifact),
    }
    provenance: JsonObject = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": final_artifact.name, "digest": {"sha256": _sha(artifact)}}],
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
    scan_path = args.out / f"{PINNED_RUNTIME_ID}.protected-content-scan.json"
    write_json_file(sbom_path, sbom)
    write_json_file(provenance_path, provenance)
    write_json_file(scan_path, scan_report)
    payload = _manifest_payload(config, artifact, sbom_path, provenance_path, scan_path)
    payload_digest = canonical_json_hash(payload)
    write_json_file(args.out / "manifest.unsigned.json", payload)
    write_json_file(
        args.out / "signing-request.json",
        {
            "schema": "localbench.runtime_signing_request.v1",
            "domain": "localbench.agentic-runtime-manifest.v1",
            "key_id": "localbench-runtime-root-2026-07",
            "payload_sha256": payload_digest,
        },
    )
    os.replace(artifact, final_artifact)
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
    config: JsonObject, artifact: Path, sbom: Path, provenance: Path, scan: Path
) -> JsonObject:
    contract = load_execution_contract()
    contract_payload = _object(contract["payload"])
    identity = _object(contract_payload["task_identity"])
    worker = _object(config["worker"])
    metadata = _archive_json(artifact, "usr/share/localbench/build-metadata.json")
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
        "python": {"version": metadata["python_version"]},
        "bubblewrap": {"version": metadata["bubblewrap_version"]},
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
        "disk_requirements": config["disk_requirements"],
        "provenance": {"sha256": _sha(provenance), "url": config["provenance_url"]},
        "sbom": {"sha256": _sha(sbom), "url": config["sbom_url"]},
        "protected_content_scan": {"sha256": _sha(scan)},
        "measured_artifact_size_bytes": artifact.stat().st_size,
    }


def _validate_config(config: JsonObject) -> None:
    schema = _read_object(
        Path(__file__).parents[1] / "runtime" / "runtime-build-v1.schema.json"
    )
    jsonschema.Draft202012Validator(schema).validate(config)
    script = Path(__file__).with_name("runtime_rootfs_build.sh")
    if _object(config["toolchain"])["builder_script_sha256"] != _sha(script):
        raise ValueError("toolchain.builder_script_sha256 differs from builder source")
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
    contract = _object(load_execution_contract()["payload"])
    expected = _object(contract["appworld_identity"])
    lineage = _object(contract["identity_lineage"])
    appworld = _object(config["appworld"])
    python = _object(config["python"])
    actual = {
        "appworld_version": appworld.get("version"),
        # C0's historical field name identifies the normalized installed
        # distribution tree (see collect_identity), not the encrypted wheel bytes.
        "appworld_package_sha256": appworld.get("installed_tree_sha256"),
        "appworld_data_sha256": appworld.get("semantic_task_sha256"),
        "python_version": python.get("version"),
        "env_pins": appworld.get("env_pins"),
    }
    if actual != expected:
        raise ValueError("C1 AppWorld identity differs from signed C0 contract")
    package = _object(appworld.get("package"))
    if package.get("sha256") != lineage.get("official_wheel_sha256"):
        raise ValueError(
            "C1 AppWorld wheel digest differs from successor contract official_wheel_sha256"
        )


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive[:1].lower()
    return f"/mnt/{drive}/{resolved.as_posix()[3:]}"


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
        site_root = dist_root.rsplit("/", 1)[0]
        record_name = dist_root + "/RECORD"
        record_member = next(item for item in members if _clean_name(item.name) == record_name)
        record_stream = tar.extractfile(record_member)
        if record_stream is None:
            raise RuntimeError("worker RECORD is unreadable")
        entries: list[list[object]] = []
        rows = csv.reader(record_stream.read().decode("utf-8").splitlines())
        by_name = {_clean_name(item.name): item for item in members}
        for relative, recorded_hash, recorded_size in rows:
            normalized = relative.replace("\\", "/")
            if normalized.endswith((".pyc", ".pyo")) or "/__pycache__/" in normalized:
                continue
            name = posixpath.normpath(site_root + "/" + relative)
            if not name.startswith("opt/localbench/venv/"):
                raise RuntimeError(f"worker RECORD path escapes installed venv: {relative}")
            member = by_name.get(name)
            if member is None or not member.isfile():
                raise RuntimeError(f"worker RECORD file missing: {relative}")
            stream = tar.extractfile(member)
            if stream is None:
                raise RuntimeError(f"worker RECORD file unreadable: {relative}")
            data = stream.read()
            digest = hashlib.sha256(data).digest()
            if recorded_hash:
                algorithm, encoded = recorded_hash.split("=", 1)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                if algorithm != "sha256" or digest != expected:
                    raise RuntimeError(f"worker RECORD hash mismatch: {relative}")
            if recorded_size and len(data) != int(recorded_size):
                raise RuntimeError(f"worker RECORD size mismatch: {relative}")
            entries.append([normalized, digest.hex(), len(data)])
        entries.sort()
    appworld = _object(config["appworld"])
    return {
        "worker_entrypoint_sha256": entrypoint,
        "worker_wheel_tree_sha256": hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
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


def _archive_json(archive: Path, name: str) -> JsonObject:
    with tarfile.open(archive, "r:xz") as tar:
        member = next(item for item in tar.getmembers() if _clean_name(item.name) == name)
        stream = tar.extractfile(member)
        if stream is None:
            raise RuntimeError(f"archive metadata missing: {name}")
        return _object(json.loads(stream.read().decode("utf-8")))


def _complete_sbom_components(archive: Path) -> list[JsonObject]:
    components: list[JsonObject] = []
    with tarfile.open(archive, "r:xz") as tar:
        members = tar.getmembers()
        status = next(item for item in members if _clean_name(item.name) == "var/lib/dpkg/status")
        stream = tar.extractfile(status)
        if stream is None:
            raise RuntimeError("dpkg status missing")
        for paragraph in stream.read().decode("utf-8", errors="strict").split("\n\n"):
            fields = dict(line.split(": ", 1) for line in paragraph.splitlines() if ": " in line)
            if fields.get("Package") and fields.get("Version") and fields.get("Status") == "install ok installed":
                components.append({"type": "library", "name": fields["Package"], "version": fields["Version"], "properties": [{"name": "localbench:package-manager", "value": "dpkg"}]})
        for member in members:
            name = _clean_name(member.name)
            if not name.endswith(".dist-info/METADATA") or not member.isfile():
                continue
            metadata_stream = tar.extractfile(member)
            if metadata_stream is None:
                continue
            fields = {}
            for line in metadata_stream.read().decode("utf-8", errors="replace").splitlines():
                if line.startswith(("Name: ", "Version: ")):
                    key, value = line.split(": ", 1)
                    fields[key] = value
            if fields.get("Name") and fields.get("Version"):
                components.append({"type": "library", "name": fields["Name"], "version": fields["Version"], "properties": [{"name": "localbench:package-manager", "value": "python-wheel"}]})
    return sorted(components, key=lambda item: (str(item["name"]).lower(), str(item["version"])))


def _read_object(path: Path) -> JsonObject:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("JSON object required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
