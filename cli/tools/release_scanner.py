"""Fail-closed recursive licensing scanner for C1 rootfs archives."""

from __future__ import annotations

import gzip
import base64
import csv
import hashlib
import io
import json
import lzma
import re
import sqlite3
import struct
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
class ScanError(RuntimeError):
    pass


def generate_exact_digest_allowlist(
    archive_path: Path,
    *,
    rootfs_id: str,
    residue_justifications: dict[str, str],
    max_residue_files: int = 50,
) -> dict[str, object]:
    """Generate the artifact-specific third admission class after dpkg/wheel verification.

    Digests cannot be pre-fabricated because the r2 archive does not exist until the
    deferred build window.  The policy supplies reviewed, per-path reasons; this function
    binds those reasons to the bytes in that exact artifact.  A large residue indicates a
    missing structural class and stops with category counts instead of producing filler.
    """
    with tarfile.open(archive_path, "r:xz") as archive:
        observed_rootfs_id = _rootfs_id(archive)
        if observed_rootfs_id != rootfs_id:
            raise ScanError(
                f"exact-digest allowlist rootfs-id mismatch: policy={rootfs_id}, artifact={observed_rootfs_id}"
            )
        installed = _dpkg_packages(archive)
        dpkg_files = _dpkg_manifest_files(archive, installed)
        wheel_files = _wheel_record_files(archive)
        residue: dict[str, bytes] = {}
        categories: dict[str, int] = {}
        for member in archive.getmembers():
            name = member.name.removeprefix("./").removeprefix("/")
            if not member.isfile() or name in dpkg_files or name in wheel_files:
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise ScanError(f"archive member is unreadable: {name}")
            residue[name] = stream.read()
            category = _residue_category(name)
            categories[category] = categories.get(category, 0) + 1
    if len(residue) > max_residue_files:
        raise ScanError(
            "exact-digest residue exceeds review limit: "
            f"count={len(residue)}, categories={json.dumps(categories, sort_keys=True)}"
        )
    files: dict[str, dict[str, str]] = {}
    for name, data in sorted(residue.items()):
        justification = residue_justifications.get(name)
        if not isinstance(justification, str) or not justification.strip():
            raise ScanError(f"exact-digest residue lacks per-file justification: {name}")
        files[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "justification": justification.strip(),
        }
    unused = sorted(set(residue_justifications) - set(residue))
    if unused:
        raise ScanError(f"exact-digest policy contains paths absent from artifact: {unused}")
    return {
        "schema": "localbench.rootfs_exact_file_allowlist.v2",
        "rootfs_id": rootfs_id,
        "residue_categories": dict(sorted(categories.items())),
        "files": files,
    }


def _residue_category(path: str) -> str:
    if path.startswith("var/lib/dpkg/"):
        return "dpkg-database-and-maintainer-metadata"
    if path.startswith("opt/localbench/venv/"):
        return "wheel-unhashed-install-metadata"
    if path.startswith(("etc/localbench", "usr/share/localbench/", "opt/localbench/bin/")):
        return "localbench-runtime-generated-files"
    return path.split("/", 1)[0] or "root"


def scan_release(
    archive: Path,
    *,
    allowed_top_levels: set[str],
    expected_packages: set[str] | None = None,
    exact_digest_allowlist: dict[str, dict[str, str]] | None = None,
    allowlist_rootfs_id: str | None = None,
    rootfs_id: str | None = None,
    sandbox_wsl_distro: str | None = None,
) -> dict[str, object]:
    inventory: list[dict[str, object]] = []
    digest_allowlist = exact_digest_allowlist or {}
    with tarfile.open(archive, "r:xz") as package_archive:
        observed_rootfs_id = _rootfs_id(package_archive)
        if rootfs_id is not None and observed_rootfs_id != rootfs_id:
            raise ScanError(
                f"artifact rootfs-id mismatch: expected={rootfs_id}, observed={observed_rootfs_id}"
            )
        if allowlist_rootfs_id is not None and observed_rootfs_id != allowlist_rootfs_id:
            raise ScanError(
                "exact-digest allowlist rootfs-id mismatch: "
                f"allowlist={allowlist_rootfs_id}, artifact={observed_rootfs_id}"
            )
        observed_packages = _dpkg_packages(package_archive)
        packaged_files = _dpkg_manifest_files(package_archive, observed_packages)
        wheel_files = _wheel_record_files(package_archive)
    if expected_packages is not None and observed_packages != expected_packages:
        unexpected = sorted(observed_packages - expected_packages)
        missing = sorted(expected_packages - observed_packages)
        raise ScanError(
            f"rootfs package allowlist mismatch; unexpected={unexpected}, missing={missing}"
        )
    if sandbox_wsl_distro is not None:
        _wsl_sandbox_extract(archive, sandbox_wsl_distro)
        with tarfile.open(archive, "r:xz") as outer:
            _inventory_archive(
                outer, inventory, allowed_top_levels, packaged_files, wheel_files, digest_allowlist
            )
        canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
        return _report(
            inventory,
            canonical,
            allowed_top_levels,
            observed_packages,
            expected_packages is not None,
        )
    with tempfile.TemporaryDirectory(prefix="localbench-release-scan-") as temporary:
        sandbox = Path(temporary).resolve()
        with tarfile.open(archive, "r:xz") as outer:
            inventory.extend(_safe_extract(outer, sandbox))
        for path in sorted(sandbox.rglob("*")):
            relative = path.relative_to(sandbox).as_posix()
            _validate_path(relative, allowed_top_levels, outer=True)
            if path.is_file():
                data = path.read_bytes()
                exact_allowlisted = _justify_regular_file(
                    relative, data, packaged_files, wheel_files, digest_allowlist
                )
                inventory.append(_entry(relative, data))
                _inspect(
                    relative, data, inventory, depth=0, exact_allowlisted=exact_allowlisted
                )
            elif path.is_symlink():
                target = path.readlink().as_posix()
                inventory.append(_metadata_entry(relative, "symlink", target=target))
            elif path.is_dir():
                inventory.append(_metadata_entry(relative, "directory"))
    canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return _report(
        inventory,
        canonical,
        allowed_top_levels,
        observed_packages,
        expected_packages is not None,
    )


def _report(
    inventory: list[dict[str, object]],
    canonical: bytes,
    allowed_top_levels: set[str],
    observed_packages: set[str],
    package_allowlist_enforced: bool,
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
        "regular_file_admission": "dpkg-wheel-record-or-exact-digest-v2",
        "package_allowlist_enforced": package_allowlist_enforced,
        "installed_packages": sorted(observed_packages),
    }


def _inventory_archive(
    archive: tarfile.TarFile,
    inventory: list[dict[str, object]],
    allowed_top_levels: set[str],
    packaged_files: dict[str, str | None],
    wheel_files: dict[str, str],
    digest_allowlist: dict[str, dict[str, str]],
) -> None:
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        raise ScanError("archive member limit exceeded")
    for member in members:
        name = member.name.removeprefix("./")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ScanError(f"unsafe archive member: {name}")
        _validate_path(name, allowed_top_levels, outer=True)
        if member.isfile():
            stream = archive.extractfile(member)
            if stream is None:
                raise ScanError(f"unreadable archive member: {name}")
            data = stream.read()
            exact_allowlisted = _justify_regular_file(
                name, data, packaged_files, wheel_files, digest_allowlist
            )
            inventory.append(_entry(name, data))
            _inspect(
                name, data, inventory, depth=0, exact_allowlisted=exact_allowlisted
            )
        elif member.issym() or member.islnk():
            if not _safe_link_target(name, member.linkname):
                raise ScanError(f"unsafe archive link: {name}")
            inventory.append(
                _metadata_entry(
                    name,
                    "symlink" if member.issym() else "hardlink",
                    target=member.linkname,
                )
            )
        elif member.isdev() or member.isfifo():
            if not path.parts or path.parts[0] != "dev":
                raise ScanError(f"device node outside /dev: {name}")
            inventory.append(
                _metadata_entry(
                    name,
                    "device-node" if member.isdev() else "fifo",
                    mode=member.mode,
                    major=member.devmajor,
                    minor=member.devminor,
                )
            )
        elif member.isdir():
            inventory.append(_metadata_entry(name, "directory"))
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
            special.append(
                _metadata_entry(
                    name,
                    "device-node" if member.isdev() else "fifo",
                    mode=member.mode,
                    major=member.devmajor,
                    minor=member.devminor,
                )
            )
            continue
        if member.issym() or member.islnk():
            if not _safe_link_target(name, member.linkname):
                raise ScanError(f"unsafe archive link: {name}")
            special.append(
                _metadata_entry(
                    name,
                    "symlink" if member.issym() else "hardlink",
                    target=member.linkname,
                )
            )
            continue
        extractable.append(member)
    archive.extractall(root, members=extractable, filter="data")
    return special


def _validate_path(
    name: str,
    allowed_top_levels: set[str],
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


def _inspect(
    name: str,
    data: bytes,
    inventory: list[dict[str, object]],
    *,
    depth: int,
    exact_allowlisted: bool = False,
) -> None:
    if depth >= MAX_DEPTH:
        raise ScanError(f"container recursion limit exceeded: {name}")
    lower = name.lower()
    # Container signatures are grounded in PKWARE APPNOTE (ZIP local header), RFC 1952
    # section 2.3.1 (gzip ID1/ID2), and the Tukaani .xz file-format specification:
    # https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
    # https://www.rfc-editor.org/rfc/rfc1952.html#section-2.3.1
    # https://tukaani.org/xz/xz-file-format.txt
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
                        inventory.append(_metadata_entry(child, "embedded-directory"))
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
        # SQLite's authoritative file-format document fixes bytes 0..15 to this header:
        # https://www.sqlite.org/fileformat.html#the_database_header
        inventory[-1]["content_type"] = "application/vnd.sqlite3"
        inventory[-1]["sqlite"] = (
            "exact-digest-allowlisted"
            if exact_allowlisted
            else _sqlite_inventory(name, data)
        )
        return
    if data.startswith(b"\x7fELF"):
        # ELF magic and layout: System V ABI, "Object Files", ELF Header/Program
        # Header/Section Header (the same 0x7f,'E','L','F' identity documented by elf(5)).
        # https://refspecs.linuxfoundation.org/elf/gabi4+/ch4.eheader.html
        _reject_elf_appended_data(name, data)
        inventory[-1]["content_type"] = "application/x-elf"
        return
    stripped = data.lstrip()
    if lower.endswith((".jsonl", ".ndjson")):
        try:
            values = [
                json.loads(line)
                for line in data.decode("utf-8").splitlines()
                if line.strip()
            ]
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ScanError(f"malformed NDJSON content: {name}") from error
        _reject_protected_json(name, values)
        inventory[-1]["content_type"] = "application/x-ndjson"
        return
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
    # POSIX ustar TMAGIC at offset 257: https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/tar.h.html
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


def _metadata_entry(path: str, kind: str, **metadata: object) -> dict[str, object]:
    identity = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    return {
        "path": path,
        "type": kind,
        "size_bytes": len(identity),
        "sha256": hashlib.sha256(identity).hexdigest(),
        **metadata,
    }


def _dpkg_packages(archive: tarfile.TarFile) -> set[str]:
    status = next(
        (
            member
            for member in archive.getmembers()
            if member.name.removeprefix("./") == "var/lib/dpkg/status"
        ),
        None,
    )
    if status is None or not status.isfile():
        return set()
    stream = archive.extractfile(status)
    if stream is None:
        raise ScanError("dpkg status is unreadable")
    packages: set[str] = set()
    for paragraph in stream.read().decode("utf-8", errors="strict").split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in paragraph.splitlines()
            if ": " in line
        )
        # dpkg-query Status-Abbrev/Status field semantics are captured verbatim in
        # tests/fixtures/dpkg-status-installed-builder-r2.txt from the builder distro.
        if fields.get("Status") == "install ok installed":
            name, version = fields.get("Package"), fields.get("Version")
            if name and version:
                packages.add(f"{name}={version}")
    return packages


def _dpkg_manifest_files(
    archive: tarfile.TarFile, installed_packages: set[str]
) -> dict[str, str | None]:
    installed_names = {item.rsplit("=", 1)[0] for item in installed_packages}
    members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
    result: dict[str, str | None] = _dpkg_conffile_digests(archive, installed_names)
    for path, member in members.items():
        match = re.fullmatch(r"var/lib/dpkg/info/(.+)\.list", path)
        if match is None or not member.isfile():
            continue
        package = match.group(1).removesuffix(":amd64")
        if package not in installed_names:
            continue
        stream = archive.extractfile(member)
        if stream is None:
            raise ScanError(f"dpkg list is unreadable: {path}")
        listed = {
            line.removeprefix("./").removeprefix("/")
            for line in stream.read().decode("utf-8", errors="strict").splitlines()
            if line not in {"", ".", "/"}
        }
        md5_path = path[:-5] + ".md5sums"
        md5: dict[str, str] = {}
        md5_member = members.get(md5_path)
        if md5_member is not None and md5_member.isfile():
            md5_stream = archive.extractfile(md5_member)
            if md5_stream is None:
                raise ScanError(f"dpkg md5sums is unreadable: {md5_path}")
            for line in md5_stream.read().decode("utf-8", errors="strict").splitlines():
                digest, separator, filename = line.partition("  ")
                if not separator or not re.fullmatch(r"[0-9a-f]{32}", digest):
                    raise ScanError(f"malformed dpkg md5sums entry: {md5_path}")
                md5[filename.removeprefix("/")] = digest
        for filename in listed:
            expected = md5.get(filename)
            # dpkg only provides an integrity check for files that have MD5 metadata;
            # mere membership in a .list is not content authentication:
            # https://manpages.debian.org/bookworm/dpkg/dpkg.1.en.html#--verify-format
            if expected is None:
                continue
            previous = result.setdefault(filename, expected)
            if previous is not None and expected is not None and previous != expected:
                raise ScanError(f"conflicting dpkg manifests for regular file: {filename}")
    return result


def _dpkg_conffile_digests(
    archive: tarfile.TarFile, installed_names: set[str]
) -> dict[str, str | None]:
    member = next(
        (item for item in archive.getmembers() if item.name.removeprefix("./") == "var/lib/dpkg/status"),
        None,
    )
    if member is None or not member.isfile():
        return {}
    stream = archive.extractfile(member)
    if stream is None:
        raise ScanError("dpkg status is unreadable")
    result: dict[str, str | None] = {}
    for paragraph in stream.read().decode("utf-8", errors="strict").split("\n\n"):
        package = next(
            (line.removeprefix("Package: ") for line in paragraph.splitlines() if line.startswith("Package: ")),
            None,
        )
        if package not in installed_names:
            continue
        in_conffiles = False
        for line in paragraph.splitlines():
            if line == "Conffiles:":
                in_conffiles = True
                continue
            if in_conffiles and not line.startswith(" "):
                in_conffiles = False
            if not in_conffiles:
                continue
            fields = line.split()
            if len(fields) >= 2 and re.fullmatch(r"[0-9a-f]{32}", fields[1]):
                result[fields[0].removeprefix("/")] = fields[1]
    return result


def _wheel_record_files(archive: tarfile.TarFile) -> dict[str, str]:
    """Return venv files authenticated by installed-wheel RECORD sha256 rows.

    The PyPA "Recording installed projects" specification defines RECORD as CSV and
    requires URL-safe-base64 hashes for installed files; blank/unsupported hashes are
    deliberately not admitted here:
    https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-record-file
    """
    result: dict[str, str] = {}
    members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
    for record_path, member in members.items():
        if (
            not member.isfile()
            or not record_path.startswith("opt/localbench/venv/")
            or not record_path.endswith(".dist-info/RECORD")
        ):
            continue
        marker = "/site-packages/"
        if marker not in record_path:
            raise ScanError(f"wheel RECORD is outside site-packages: {record_path}")
        site_root = record_path.split(marker, 1)[0] + marker.rstrip("/")
        stream = archive.extractfile(member)
        if stream is None:
            raise ScanError(f"wheel RECORD is unreadable: {record_path}")
        try:
            rows = csv.reader(io.StringIO(stream.read().decode("utf-8", errors="strict")))
            for row in rows:
                if len(row) != 3:
                    raise ScanError(f"malformed wheel RECORD row: {record_path}")
                relative, encoded_hash, _size = row
                algorithm, separator, encoded = encoded_hash.partition("=")
                if not separator or algorithm != "sha256":
                    continue
                resolved = PurePosixPath(site_root, relative)
                normalized_parts: list[str] = []
                for part in resolved.parts:
                    if part in ("", ".", "/"):
                        continue
                    if part == "..":
                        if not normalized_parts:
                            raise ScanError(f"wheel RECORD path escapes rootfs: {relative}")
                        normalized_parts.pop()
                    else:
                        normalized_parts.append(part)
                normalized = "/".join(normalized_parts)
                if not normalized.startswith("opt/localbench/venv/"):
                    raise ScanError(f"wheel RECORD path escapes installed venv: {relative}")
                try:
                    digest = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).hex()
                except ValueError as error:
                    raise ScanError(f"malformed wheel RECORD hash: {record_path}") from error
                if len(digest) != 64:
                    raise ScanError(f"malformed wheel RECORD sha256: {record_path}")
                previous = result.setdefault(normalized, digest)
                if previous != digest:
                    raise ScanError(f"conflicting wheel RECORD hashes: {normalized}")
        except csv.Error as error:
            raise ScanError(f"malformed wheel RECORD CSV: {record_path}") from error
    return result


def _justify_regular_file(
    name: str,
    data: bytes,
    packaged_files: dict[str, str | None],
    wheel_files: dict[str, str],
    digest_allowlist: dict[str, dict[str, str]],
) -> bool:
    normalized = name.removeprefix("./").removeprefix("/")
    package_digest = packaged_files.get(normalized)
    package_admitted = package_digest is not None
    if package_digest is not None and hashlib.md5(data, usedforsecurity=False).hexdigest() != package_digest:
        raise ScanError(f"dpkg manifest digest mismatch: {normalized}")
    wheel_digest = wheel_files.get(normalized)
    wheel_admitted = wheel_digest is not None
    if wheel_digest is not None and hashlib.sha256(data).hexdigest() != wheel_digest:
        raise ScanError(f"wheel RECORD digest mismatch: {normalized}")
    exact = digest_allowlist.get(normalized)
    exact_admitted = exact is not None
    if exact_admitted:
        assert exact is not None
        justification = exact.get("justification")
        expected = exact.get("sha256")
        if not justification or not isinstance(justification, str):
            raise ScanError(f"exact-digest allowlist lacks justification: {normalized}")
        if expected != hashlib.sha256(data).hexdigest():
            raise ScanError(f"exact-digest allowlist mismatch: {normalized}")
    class_count = sum((package_admitted, wheel_admitted, exact_admitted))
    if class_count != 1:
        classification = "multiple classes" if class_count else "no class"
        raise ScanError(f"regular file is not justified by exactly one content class ({classification}): {normalized}")
    return exact_admitted


def _rootfs_id(archive: tarfile.TarFile) -> str | None:
    marker = next(
        (
            member
            for member in archive.getmembers()
            if member.name.removeprefix("./") == "etc/localbench-appliance-owner.json"
        ),
        None,
    )
    if marker is None or not marker.isfile():
        return None
    stream = archive.extractfile(marker)
    if stream is None:
        raise ScanError("rootfs owner marker is unreadable")
    try:
        payload = json.loads(stream.read().decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ScanError("rootfs owner marker is malformed") from error
    rootfs_id = payload.get("runtime_id") if isinstance(payload, dict) else None
    return rootfs_id if isinstance(rootfs_id, str) else None


def _sqlite_inventory(name: str, data: bytes) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="localbench-sqlite-scan-") as temporary:
        database = Path(temporary) / "content.sqlite"
        database.write_bytes(data)
        connection: sqlite3.Connection | None = None
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
                for row in connection.execute(f"SELECT * FROM {quoted}"):
                    for value in row:
                        if isinstance(value, str) and PROTECTED_PATH.search(value):
                            raise ScanError(
                                f"protected SQLite row value in {name}/{table}: {value}"
                            )
                result.append({"table": str(table), "row_count": int(count)})
            return result
        except sqlite3.DatabaseError as error:
            raise ScanError(f"unreadable SQLite database: {name}") from error
        finally:
            if connection is not None:
                connection.close()


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
        elif isinstance(item, str) and PROTECTED_PATH.search(item):
            raise ScanError(f"protected JSON scalar value in {name}: {item}")


def _reject_elf_appended_data(name: str, data: bytes) -> None:
    if len(data) < 16 or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ScanError(f"malformed ELF identity: {name}")
    endian = "<" if data[5] == 1 else ">"
    elf64 = data[4] == 2
    try:
        if elf64:
            header = struct.unpack_from(endian + "HHIQQQIHHHHHH", data, 16)
            phoff, shoff, ehsize, phentsize, phnum, shentsize, shnum = (
                header[4], header[5], header[7], header[8], header[9], header[10], header[11]
            )
        else:
            header = struct.unpack_from(endian + "HHIIIIIHHHHHH", data, 16)
            phoff, shoff, ehsize, phentsize, phnum, shentsize, shnum = (
                header[4], header[5], header[7], header[8], header[9], header[10], header[11]
            )
        required_ehsize = 64 if elf64 else 52
        required_phentsize = 56 if elf64 else 32
        required_shentsize = 64 if elf64 else 40
        if ehsize != required_ehsize:
            raise ScanError(
                f"ELF header size is invalid: {name} expected={required_ehsize} observed={ehsize}"
            )
        # System V gABI, ELF Header: e_phoff/e_shoff hold zero when the corresponding table is
        # absent. We also require a zero entry size so a zero-count table contributes no extent.
        if phnum == 0:
            if phoff != 0 or phentsize != 0:
                raise ScanError(f"ELF program-header table is absent but metadata is nonzero: {name}")
        elif phentsize != required_phentsize:
            raise ScanError(f"ELF program-header entry size is invalid: {name}")
        if shnum == 0:
            if shoff != 0 or shentsize != 0:
                raise ScanError(f"ELF section-header table is absent but metadata is nonzero: {name}")
        elif shentsize != required_shentsize:
            raise ScanError(f"ELF section-header entry size is invalid: {name}")
        file_extents = [(0, required_ehsize)]
        if phnum:
            file_extents.append((phoff, phoff + phentsize * phnum))
        if shnum:
            file_extents.append((shoff, shoff + shentsize * shnum))
        for index in range(phnum):
            offset = phoff + index * phentsize
            if elf64:
                _type, _flags, file_offset, _vaddr, _paddr, file_size = struct.unpack_from(
                    endian + "IIQQQQ", data, offset
                )
            else:
                _type, file_offset, _vaddr, _paddr, file_size = struct.unpack_from(
                    endian + "IIIII", data, offset
                )
            if file_size > 0:
                file_extents.append((file_offset, file_offset + file_size))
        for index in range(shnum):
            offset = shoff + index * shentsize
            if elf64:
                _name, _type, _flags, _addr, file_offset, file_size = struct.unpack_from(
                    endian + "IIQQQQ", data, offset
                )
            else:
                _name, _type, _flags, _addr, file_offset, file_size = struct.unpack_from(
                    endian + "IIIIII", data, offset
                )
            # SHT_NOBITS (8), e.g. .bss, occupies no bytes in the object file.
            if _type != 8 and file_size > 0:
                file_extents.append((file_offset, file_offset + file_size))
    except (struct.error, IndexError) as error:
        raise ScanError(f"malformed ELF structure: {name}") from error
    merged_extents: list[list[int]] = []
    for start, end in sorted(file_extents):
        if merged_extents and start <= merged_extents[-1][1]:
            merged_extents[-1][1] = max(merged_extents[-1][1], end)
        else:
            merged_extents.append([start, end])
    # ELF alignment permits legitimate unowned interior padding, so enforce trailing coverage
    # after the final merged file-backed extent. Zero-size attacker-chosen offsets add no extent.
    coverage_end = merged_extents[-1][1]
    if coverage_end != len(data):
        disposition = "appended data" if coverage_end < len(data) else "truncated image"
        raise ScanError(
            f"ELF {disposition}: {name} coverage_end={coverage_end} size={len(data)}"
        )
