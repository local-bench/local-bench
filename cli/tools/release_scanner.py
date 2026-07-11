"""Fail-closed recursive licensing scanner for C1 rootfs archives."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import lzma
import re
import sqlite3
import tarfile
import tempfile
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

PROTECTED_PATH = re.compile(
    r"(?i)(^|/)(appworld(?:-[^/]+)?\.dist-info|appworld/(?:apps|data|evaluator)|"
    r"ground[_-]?truth|test_(?:normal|challenge)|tasks?)(/|$)"
)
ARCHIVE_SUFFIXES = (".zip", ".whl", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".gz")
MAX_DEPTH = 5
MAX_MEMBERS = 500_000
MAX_EMBEDDED_BYTES = 512 * 1024 * 1024
DEFAULT_ROOTFS_PATH_PREFIXES = (
    "bin", "bin.usr-is-merged", "boot", "dev", "etc", "home/lbworker",
    "lib", "lib.usr-is-merged", "lib64", "media", "mnt", "opt/localbench",
    "proc", "root", "run", "sbin", "sbin.usr-is-merged", "snap", "srv",
    "sys", "tmp", "usr/bin", "usr/include", "usr/lib", "usr/lib64",
    "usr/libexec", "usr/local", "usr/sbin", "usr/share", "var/cache/apt",
    "var/lib/apt", "var/lib/dpkg", "var/lib/localbench", "var/log", "var/tmp",
)


class ScanError(RuntimeError):
    pass


def scan_release(
    archive: Path,
    *,
    allowed_top_levels: set[str],
    allowed_path_prefixes: tuple[str, ...] | None = None,
    sandbox_wsl_distro: str | None = None,
) -> dict[str, object]:
    inventory: list[dict[str, object]] = []
    path_allowlist = allowed_path_prefixes or tuple(sorted(allowed_top_levels))
    if sandbox_wsl_distro is not None:
        _wsl_sandbox_extract(archive, sandbox_wsl_distro)
        with tarfile.open(archive, "r:xz") as outer:
            _inventory_archive(outer, inventory, allowed_top_levels, path_allowlist)
        canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
        return _report(inventory, canonical, allowed_top_levels, path_allowlist)
    with tempfile.TemporaryDirectory(prefix="localbench-release-scan-") as temporary:
        sandbox = Path(temporary).resolve()
        with tarfile.open(archive, "r:xz") as outer:
            inventory.extend(_safe_extract(outer, sandbox))
        for path in sorted(sandbox.rglob("*")):
            relative = path.relative_to(sandbox).as_posix()
            _validate_path(relative, allowed_top_levels, path_allowlist, outer=True)
            if path.is_file():
                data = path.read_bytes()
                inventory.append(_entry(relative, data))
                _inspect(relative, data, inventory, depth=0)
            elif path.is_symlink():
                inventory.append({"path": relative, "type": "symlink", "target": path.readlink().as_posix()})
            elif path.is_dir():
                inventory.append({"path": relative, "type": "directory"})
    canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return _report(inventory, canonical, allowed_top_levels, path_allowlist)


def _report(
    inventory: list[dict[str, object]],
    canonical: bytes,
    allowed_top_levels: set[str],
    path_allowlist: tuple[str, ...],
) -> dict[str, object]:
    content_types: dict[str, int] = {}
    total_bytes = 0
    for item in inventory:
        total_bytes += int(item.get("size_bytes", 0))
        if kind := item.get("content_type"):
            content_types[str(kind)] = content_types.get(str(kind), 0) + 1
    return {
        "schema": "localbench.protected_content_scan.v1",
        "result": "passed",
        "scanner": "recursive-container-and-tree-signature-v1",
        "members": len(inventory),
        "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "inventory": inventory,
        "total_member_bytes": total_bytes,
        "content_type_counts": dict(sorted(content_types.items())),
        "allowed_top_levels": sorted(allowed_top_levels),
        "allowed_path_prefixes": list(path_allowlist),
    }


def _inventory_archive(
    archive: tarfile.TarFile,
    inventory: list[dict[str, object]],
    allowed_top_levels: set[str],
    path_allowlist: tuple[str, ...],
) -> None:
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        raise ScanError("archive member limit exceeded")
    for member in members:
        name = member.name.removeprefix("./")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ScanError(f"unsafe archive member: {name}")
        _validate_path(name, allowed_top_levels, path_allowlist, outer=True)
        if member.isfile():
            stream = archive.extractfile(member)
            if stream is None:
                raise ScanError(f"unreadable archive member: {name}")
            data = stream.read()
            inventory.append(_entry(name, data))
            _inspect(name, data, inventory, depth=0)
        elif member.issym() or member.islnk():
            if not _safe_link_target(name, member.linkname):
                raise ScanError(f"unsafe archive link: {name}")
            inventory.append({"path": name, "type": "symlink" if member.issym() else "hardlink", "target": member.linkname})
        elif member.isdev() or member.isfifo():
            if not path.parts or path.parts[0] != "dev":
                raise ScanError(f"device node outside /dev: {name}")
            inventory.append({"path": name, "type": "device-node" if member.isdev() else "fifo", "mode": member.mode, "major": member.devmajor, "minor": member.devminor})
        elif member.isdir():
            inventory.append({"path": name, "type": "directory"})
        else:
            raise ScanError(f"unrecognized tar member type: {name}")


def _wsl_sandbox_extract(archive: Path, distro: str) -> None:
    resolved = archive.resolve()
    drive = resolved.drive[:1].lower()
    wsl_path = f"/mnt/{drive}/{resolved.as_posix()[3:]}"
    script = "set -eu; d=$(mktemp -d); trap 'rm -rf -- \"$d\"' EXIT; tar --no-same-owner --no-same-permissions --exclude='./dev/*' --exclude='dev/*' -xJf \"$1\" -C \"$d\"; find \"$d\" -xdev -type f -print0 | xargs -0r sha256sum >/dev/null"
    result = subprocess.run(["wsl.exe", "--distribution", distro, "--exec", "/bin/bash", "-c", script, "localbench-scan", wsl_path], capture_output=True, check=False)
    if result.returncode != 0:
        raise ScanError("sandboxed WSL extraction failed: " + (result.stderr or result.stdout).decode(errors="replace")[-1000:])


def _safe_extract(archive: tarfile.TarFile, root: Path) -> list[dict[str, object]]:
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        raise ScanError("archive member limit exceeded")
    extractable: list[tarfile.TarInfo] = []
    special: list[dict[str, object]] = []
    for member in members:
        name = member.name.removeprefix("./")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ScanError(f"unsafe archive member: {name}")
        if member.isdev() or member.isfifo():
            if not path.parts or path.parts[0] != "dev":
                raise ScanError(f"device node outside /dev: {name}")
            special.append({"path": name, "type": "device-node" if member.isdev() else "fifo", "mode": member.mode, "major": member.devmajor, "minor": member.devminor})
            continue
        if member.issym() or member.islnk():
            if not _safe_link_target(name, member.linkname):
                raise ScanError(f"unsafe archive link: {name}")
            special.append({"path": name, "type": "symlink" if member.issym() else "hardlink", "target": member.linkname})
            continue
        extractable.append(member)
    archive.extractall(root, members=extractable, filter="data")
    return special


def _validate_path(
    name: str,
    allowed_top_levels: set[str],
    path_allowlist: tuple[str, ...] = (),
    *,
    outer: bool,
) -> None:
    normalized = name.replace("\\", "/").lstrip("./")
    if PROTECTED_PATH.search(normalized):
        raise ScanError(f"protected AppWorld tree signature: {name}")
    if outer and normalized:
        top = normalized.split("/", 1)[0]
        if top not in allowed_top_levels:
            raise ScanError(f"rootfs path outside explicit allowlist: {name}")
        if path_allowlist and not any(
            normalized == prefix
            or normalized.startswith(prefix.rstrip("/") + "/")
            or prefix.startswith(normalized.rstrip("/") + "/")
            for prefix in path_allowlist
        ):
            raise ScanError(f"rootfs path outside positive path allowlist: {name}")


def _inspect(name: str, data: bytes, inventory: list[dict[str, object]], *, depth: int) -> None:
    if depth >= MAX_DEPTH:
        raise ScanError(f"container recursion limit exceeded: {name}")
    lower = name.lower()
    is_zip = data.startswith(b"PK\x03\x04") or lower.endswith((".zip", ".whl"))
    is_gzip = data.startswith(b"\x1f\x8b") or lower.endswith((".gz", ".tgz", ".tar.gz"))
    is_xz = data.startswith(b"\xfd7zXZ\x00") or lower.endswith((".xz", ".txz", ".tar.xz"))
    is_tar = _looks_tar(data) or lower.endswith(".tar")
    if is_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.infolist():
                    child = f"{name}!/{item.filename}"
                    _validate_path(item.filename, set(), outer=False)
                    if item.flag_bits & 0x1:
                        raise ScanError(f"encrypted embedded archive: {child}")
                    if item.is_dir():
                        inventory.append({"path": child, "type": "embedded-directory"})
                        continue
                    body = archive.read(item)
                    inventory.append(_entry(child, body, kind="embedded-file"))
                    _inspect(child, body, inventory, depth=depth + 1)
        except (zipfile.BadZipFile, RuntimeError) as error:
            raise ScanError(f"unreadable embedded zip: {name}") from error
        return
    if is_gzip or is_xz:
        try:
            body = gzip.decompress(data) if is_gzip else lzma.decompress(data)
        except (OSError, EOFError, lzma.LZMAError) as error:
            raise ScanError(f"unreadable embedded compressed stream: {name}") from error
        if len(body) > MAX_EMBEDDED_BYTES:
            raise ScanError(f"embedded stream too large: {name}")
        child = name + "!/stream"
        inventory.append(_entry(child, body, kind="embedded-stream"))
        _inspect(child, body, inventory, depth=depth + 1)
        return
    if is_tar:
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for item in archive.getmembers():
                    child = f"{name}!/{item.name}"
                    _validate_path(item.name, set(), outer=False)
                    if item.isfile():
                        stream = archive.extractfile(item)
                        if stream is None:
                            raise ScanError(f"unreadable embedded tar member: {child}")
                        body = stream.read(MAX_EMBEDDED_BYTES + 1)
                        if len(body) > MAX_EMBEDDED_BYTES:
                            raise ScanError(f"embedded member too large: {child}")
                        inventory.append(_entry(child, body, kind="embedded-file"))
                        _inspect(child, body, inventory, depth=depth + 1)
        except tarfile.TarError as error:
            raise ScanError(f"unreadable embedded tar: {name}") from error
        return
    if lower.endswith(ARCHIVE_SUFFIXES):
        raise ScanError(f"unrecognized or malformed embedded archive: {name}")
    if data.startswith(b"SQLite format 3\x00"):
        inventory[-1]["content_type"] = "application/vnd.sqlite3"
        inventory[-1]["sqlite"] = _sqlite_inventory(name, data)
        return
    if data.startswith(b"\x7fELF"):
        inventory[-1]["content_type"] = "application/x-elf"
        return
    stripped = data.lstrip()
    if lower.endswith(".json") or stripped.startswith(b"{"):
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ScanError(f"malformed JSON content: {name}") from error
        _reject_protected_json(name, value)
        inventory[-1]["content_type"] = "application/json"
        return
    if b"\x00" not in data[:8192]:
        inventory[-1]["content_type"] = "text/plain"
    else:
        inventory[-1]["content_type"] = "application/octet-stream"
    recognized_binary = name == "usr/lib/udev/hwdb.bin" or name.startswith(("usr/lib/firmware/", "usr/share/secureboot/updates/"))
    if name.endswith(".bin") and not recognized_binary and not data.startswith((b"\x7fELF", b"SQLite format 3\x00")):
        raise ScanError(f"opaque binary blob outside recognized format: {name}")


def _looks_tar(data: bytes) -> bool:
    return len(data) > 265 and data[257:263] in (b"ustar\x00", b"ustar ")


def _safe_link_target(name: str, target: str) -> bool:
    parts = [] if target.startswith("/") else list(PurePosixPath(name).parent.parts)
    for part in PurePosixPath(target).parts:
        if part in ("", ".", "/"):
            continue
        if part == "..":
            if not parts:
                return False
            parts.pop()
        else:
            parts.append(part)
    return True


def _entry(path: str, data: bytes, *, kind: str = "file") -> dict[str, object]:
    return {"path": path, "type": kind, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _sqlite_inventory(name: str, data: bytes) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="localbench-sqlite-scan-") as temporary:
        database = Path(temporary) / "content.sqlite"
        database.write_bytes(data)
        try:
            connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            result = []
            for (table,) in rows:
                if PROTECTED_PATH.search(str(table)):
                    raise ScanError(f"protected SQLite table in {name}: {table}")
                quoted = '"' + str(table).replace('"', '""') + '"'
                count = connection.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
                result.append({"table": str(table), "row_count": int(count)})
            connection.close()
            return result
        except sqlite3.DatabaseError as error:
            raise ScanError(f"unreadable SQLite database: {name}") from error


def _reject_protected_json(name: str, value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if PROTECTED_PATH.search(str(key)):
                    raise ScanError(f"protected JSON content class in {name}: {key}")
                pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)
