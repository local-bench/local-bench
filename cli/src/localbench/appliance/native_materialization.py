from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
from pathlib import PurePosixPath

from localbench._types import JsonObject
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import ProvisioningError
from localbench.submissions.canon import canonical_json_hash

_STATIC_CRITICAL_PATHS = {
    "worker_entrypoint_sha256": "opt/localbench/bin/localbench-worker",
    "bubblewrap_sha256": "usr/bin/bwrap",
    "wsl_conf_sha256": "etc/wsl.conf",
}


def materialize_rootfs(tar_archive: Path, rootfs: Path, manifest: JsonObject) -> None:
    if rootfs.exists():
        verify_materialized_rootfs(rootfs, manifest)
        return
    staging = rootfs.with_name(f".{rootfs.name}.materializing")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(tar_archive, mode="r:") as source:
            source.extractall(
                staging,
                members=_validated_rootfs_members(source),
                filter=_rootfs_filter,
            )
        verify_materialized_rootfs(staging, manifest)
        os.replace(staging, rootfs)
    except (OSError, ValueError, tarfile.TarError) as error:
        raise ProvisioningError(
            "rootfs_materialization_failed",
            str(error),
            "Discard the runtime and retry with the signed appliance artifact",
        ) from error
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _validated_rootfs_members(source: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = source.getmembers()
    symlinks = {_normalized_member_path(member) for member in members if member.issym()}
    for member in members:
        path = _normalized_member_path(member)
        if any(parent in symlinks for parent in path.parents):
            raise ValueError(f"archive member traverses symlink: {member.name}")
    return members


def _normalized_member_path(member: tarfile.TarInfo) -> PurePosixPath:
    path = PurePosixPath(member.name)
    while path.parts and path.parts[0] == ".":
        path = PurePosixPath(*path.parts[1:])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive member path: {member.name}")
    return path


def _rootfs_filter(member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo | None:
    if not (member.isreg() or member.isdir() or member.issym() or member.islnk()):
        return None
    if member.issym():
        # data_filter realpath-resolves relative link targets through symlinks
        # already on disk, so a relative link to an absolute rootfs symlink
        # (Ubuntu's /etc/ssl/certs chains) is misread as an escape. Symlinks are
        # checked lexically instead: absolute targets resolve inside the jail at
        # runtime, and the member pre-scan forbids extracting through any symlink.
        path = _normalized_member_path(member)
        _assert_symlink_target_contained(path, member)
        return member.replace(
            name=str(path),
            mode=None,
            uid=None,
            gid=None,
            uname=None,
            gname=None,
            deep=False,
        )
    return tarfile.data_filter(member, destination)


def _assert_symlink_target_contained(
    path: PurePosixPath, member: tarfile.TarInfo
) -> None:
    link = PurePosixPath(member.linkname)
    if link.is_absolute():
        return
    depth = len(path.parent.parts)
    for part in link.parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                raise ValueError(f"symlink escapes rootfs: {member.name}")
        elif part != ".":
            depth += 1


def verify_materialized_rootfs(rootfs: Path, manifest: JsonObject) -> None:
    critical = manifest.get("critical_hashes")
    if not isinstance(critical, dict):
        raise ProvisioningError(
            "runtime_mutated", "critical hashes missing", "Reprovision"
        )
    observed = {
        field: _file_sha(rootfs / relative)
        for field, relative in _STATIC_CRITICAL_PATHS.items()
    }
    observed["worker_wheel_tree_sha256"] = _worker_tree_sha(rootfs)
    for field, digest in observed.items():
        if critical.get(field) != digest:
            raise ProvisioningError("runtime_mutated", field, "Reprovision")
    assert_native_ownership(rootfs, str(manifest.get("runtime_id", PINNED_RUNTIME_ID)))


def assert_native_ownership(rootfs: Path, runtime_id: str) -> None:
    marker_path = rootfs / "etc/localbench-appliance-owner.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvisioningError(
            "ownership_marker_missing", str(rootfs), "Refusing to remove this runtime"
        ) from error
    expected = {
        "owner": "localbench",
        "runtime_id": runtime_id,
        "schema": "localbench.appliance_owner.v1",
    }
    if marker != expected:
        raise ProvisioningError(
            "ownership_marker_mismatch", str(rootfs), "Refusing to remove this runtime"
        )


def _worker_tree_sha(rootfs: Path) -> str:
    site_packages = rootfs / "opt/localbench/venv/lib"
    records = sorted(
        site_packages.glob("python*/site-packages/local_bench_ai-*.dist-info/RECORD")
    )
    if len(records) != 1:
        raise ProvisioningError(
            "runtime_mutated", "worker RECORD missing", "Reprovision"
        )
    record = records[0]
    package_root = record.parent.parent
    # The builder admits every RECORD path inside the venv (console scripts are
    # recorded as ../../../bin/...), so containment is venv-scoped and lexical
    # to byte-match the signed worker_wheel_tree_sha256.
    venv_root = Path(os.path.normpath(str(rootfs / "opt/localbench/venv")))
    entries: list[tuple[str, str, int]] = []
    try:
        rows = csv.reader(record.read_text(encoding="utf-8").splitlines())
        for relative, recorded_hash, recorded_size in rows:
            normalized = relative.replace("\\", "/")
            if normalized.endswith((".pyc", ".pyo")) or "/__pycache__/" in normalized:
                continue
            path = Path(os.path.normpath(str(package_root / normalized)))
            if not path.is_relative_to(venv_root) or not path.is_file():
                raise ProvisioningError("runtime_mutated", normalized, "Reprovision")
            data = path.read_bytes()
            digest = hashlib.sha256(data).digest()
            if recorded_hash:
                algorithm, encoded = recorded_hash.split("=", 1)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                if algorithm != "sha256" or digest != expected:
                    raise ProvisioningError(
                        "runtime_mutated", normalized, "Reprovision"
                    )
            if recorded_size and len(data) != int(recorded_size):
                raise ProvisioningError("runtime_mutated", normalized, "Reprovision")
            entries.append((normalized, digest.hex(), len(data)))
    except (OSError, UnicodeError, ValueError) as error:
        raise ProvisioningError("runtime_mutated", str(error), "Reprovision") from error
    entries.sort()
    return canonical_json_hash(entries)


def _file_sha(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise ProvisioningError("runtime_mutated", str(path), "Reprovision") from error
