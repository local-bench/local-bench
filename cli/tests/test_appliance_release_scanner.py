from __future__ import annotations

import importlib.util
import base64
import hashlib
import io
import json
import tarfile
import zipfile
import sqlite3
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "release_scanner.py"
SPEC = importlib.util.spec_from_file_location("release_scanner_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


def archive(tmp_path: Path, files: dict[str, bytes]) -> Path:
    path = tmp_path / "fixture.tar.xz"
    with tarfile.open(path, "w:xz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(body))
    return path


def nested_zip(name: str, body: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        zipped.writestr(name, body)
    return output.getvalue()


def exact(files: dict[str, bytes]) -> dict[str, dict[str, str]]:
    return {
        name: {
            "sha256": hashlib.sha256(body).hexdigest(),
            "justification": "synthetic scanner regression fixture",
        }
        for name, body in files.items()
    }


def dpkg_admission(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, dict[str, str]]]:
    status = (Path(__file__).parent / "fixtures" / "dpkg-status-installed-builder-r2.txt").read_bytes()
    listing = ("/.\n" + "".join(f"/{name}\n" for name in files)).encode()
    md5sums = "".join(
        f"{hashlib.md5(body, usedforsecurity=False).hexdigest()}  {name}\n"
        for name, body in files.items()
    ).encode()
    metadata = {
        "var/lib/dpkg/status": status,
        "var/lib/dpkg/info/dpkg.list": listing,
        "var/lib/dpkg/info/dpkg.md5sums": md5sums,
    }
    return {**metadata, **files}, exact(metadata)


def test_scanner_accepts_explicit_minimal_rootfs_inventory(tmp_path: Path) -> None:
    files = {"etc/wsl.conf": b"[automount]\nenabled=false\n", "usr/bin/tool": b"#!/bin/sh\n"}
    report = scanner.scan_release(
        archive(tmp_path, files),
        allowed_top_levels={"etc", "usr"},
        exact_digest_allowlist=exact(files),
    )
    assert report["result"] == "passed"
    assert report["members"] >= 4
    assert report["inventory"]
    assert all(
        {"path", "size_bytes", "sha256"} <= set(item)
        for item in report["inventory"]
    )


def test_scanner_rejects_loose_file_under_previously_admitted_prefix(tmp_path: Path) -> None:
    with pytest.raises(scanner.ScanError, match="no class"):
        scanner.scan_release(
            archive(tmp_path, {"usr/lib/unexpected.txt": b"x"}),
            allowed_top_levels={"usr"},
        )


def test_scanner_enforces_exact_package_allowlist(tmp_path: Path) -> None:
    captured = (Path(__file__).parent / "fixtures" / "dpkg-status-installed-builder-r2.txt").read_bytes()
    status = captured + (
        b"\nPackage: expected\nVersion: 1.2.3\nStatus: install ok installed\n\n"
        b"Package: injected\nVersion: 9\nStatus: install ok installed\n"
    )
    with pytest.raises(scanner.ScanError, match="unexpected=.*injected=9"):
        scanner.scan_release(
            archive(tmp_path, {"var/lib/dpkg/status": status}),
            allowed_top_levels={"var"},
            expected_packages={"expected=1.2.3"},
        )


def test_scanner_admits_file_from_captured_dpkg_list_and_md5sums(tmp_path: Path) -> None:
    status = (Path(__file__).parent / "fixtures" / "dpkg-status-installed-builder-r2.txt").read_bytes()
    tool = b"dpkg-owned fixture\n"
    listing = b"/.\n/usr/bin/tool\n"
    md5sums = hashlib.md5(tool, usedforsecurity=False).hexdigest().encode() + b"  usr/bin/tool\n"
    metadata = {
        "var/lib/dpkg/status": status,
        "var/lib/dpkg/info/dpkg.list": listing,
        "var/lib/dpkg/info/dpkg.md5sums": md5sums,
    }
    files = {**metadata, "usr/bin/tool": tool}
    report = scanner.scan_release(
        archive(tmp_path, files),
        allowed_top_levels={"usr", "var"},
        expected_packages={"dpkg=1.22.6ubuntu6.6"},
        exact_digest_allowlist=exact(metadata),
    )
    assert report["regular_file_admission"] == "dpkg-wheel-record-or-exact-digest-v2"


def test_scanner_rejects_dpkg_list_file_without_integrity_digest(tmp_path: Path) -> None:
    status = (Path(__file__).parent / "fixtures" / "dpkg-status-installed-builder-r2.txt").read_bytes()
    metadata = {
        "var/lib/dpkg/status": status,
        "var/lib/dpkg/info/dpkg.list": b"/.\n/usr/bin/tool\n",
        "var/lib/dpkg/info/dpkg.md5sums": b"",
    }
    with pytest.raises(scanner.ScanError, match="no class"):
        scanner.scan_release(
            archive(tmp_path, {**metadata, "usr/bin/tool": b"unverified\n"}),
            allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"},
            exact_digest_allowlist=exact(metadata),
        )


def test_captured_dpkg_fixtures_match_provenance_sidecar() -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    provenance = json.loads(
        (fixture_root / "dpkg-builder-r2.provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["wsl_writes_performed"] is False
    assert "Ubuntu 24.04.3 LTS" in provenance["environment_identity"]["os_release_pretty_name"]
    for name, evidence in provenance["fixtures"].items():
        captured = (fixture_root / name).read_bytes()
        assert hashlib.sha256(captured).hexdigest() == evidence["sha256"]
        assert evidence["command"].startswith("wsl.exe -d Ubuntu -u michael -- ")
    assert (fixture_root / "dpkg-builder-r2.list").read_bytes() == b"/usr/bin/dpkg\n"
    assert (fixture_root / "dpkg-builder-r2.md5sums").read_bytes() == (
        b"1c9124caa101c66a71237b0285acd7ac  usr/bin/dpkg\n"
    )


def test_scanner_admits_venv_file_only_with_wheel_record_sha256(tmp_path: Path) -> None:
    package_path = "opt/localbench/venv/lib/python3.12/site-packages/example/__init__.py"
    record_path = "opt/localbench/venv/lib/python3.12/site-packages/example-1.dist-info/RECORD"
    body = b"VALUE = 1\n"
    digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
    record = f"example/__init__.py,sha256={digest},{len(body)}\n"
    files = {package_path: body, record_path: record.encode()}
    report = scanner.scan_release(
        archive(tmp_path, files),
        allowed_top_levels={"opt"},
        exact_digest_allowlist=exact({record_path: record.encode()}),
    )
    assert report["result"] == "passed"


def test_scanner_fails_closed_when_allowlist_rootfs_id_mismatches(tmp_path: Path) -> None:
    marker_path = "etc/localbench-appliance-owner.json"
    marker = b'{"runtime_id":"artifact-r2"}'
    with pytest.raises(scanner.ScanError, match="allowlist rootfs-id mismatch"):
        scanner.scan_release(
            archive(tmp_path, {marker_path: marker}),
            allowed_top_levels={"etc"},
            exact_digest_allowlist=exact({marker_path: marker}),
            allowlist_rootfs_id="wrong-r2",
        )


def test_exact_allowlisted_json_still_gets_scalar_inspection(tmp_path: Path) -> None:
    name = "usr/share/cache.json"
    body = b'{"value":"renamed/ground_truth/evaluation.py"}'
    with pytest.raises(scanner.ScanError, match="JSON scalar"):
        scanner.scan_release(
            archive(tmp_path, {name: body}),
            allowed_top_levels={"usr"},
            exact_digest_allowlist=exact({name: body}),
        )


def test_allowlist_generator_binds_reviewed_residue_to_artifact(tmp_path: Path) -> None:
    marker_path = "etc/localbench-appliance-owner.json"
    config_path = "etc/localbench-runtime.conf"
    marker = b'{"runtime_id":"r2"}'
    config = b"locked=true\n"
    built = archive(tmp_path, {marker_path: marker, config_path: config})
    generated = scanner.generate_exact_digest_allowlist(
        built,
        rootfs_id="r2",
        residue_justifications={
            marker_path: "owner marker binds the extracted distro to runtime r2; inert JSON metadata",
            config_path: "runtime build configuration consumed by LocalBench; contains no task data",
        },
    )
    assert generated["rootfs_id"] == "r2"
    assert generated["files"][config_path]["sha256"] == hashlib.sha256(config).hexdigest()


def test_allowlist_generator_stops_and_reports_large_residue_categories(tmp_path: Path) -> None:
    marker_path = "etc/localbench-appliance-owner.json"
    files = {marker_path: b'{"runtime_id":"r2"}'}
    files.update({f"loose/file-{index}.txt": b"x" for index in range(3)})
    with pytest.raises(scanner.ScanError, match=r'count=4.*"loose": 3'):
        scanner.generate_exact_digest_allowlist(
            archive(tmp_path, files),
            rootfs_id="r2",
            residue_justifications={},
            max_residue_files=2,
        )


def test_scanner_enumerates_sqlite_tables_and_row_counts(tmp_path: Path) -> None:
    database = tmp_path / "fixture.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("create table cache (value text)")
    connection.executemany("insert into cache values (?)", [("a",), ("b",)])
    connection.commit()
    connection.close()
    files, allowlist = dpkg_admission(
        {"var/lib/localbench/cache.sqlite": database.read_bytes()}
    )
    report = scanner.scan_release(
        archive(tmp_path, files),
        allowed_top_levels={"var"}, expected_packages={"dpkg=1.22.6ubuntu6.6"},
        exact_digest_allowlist=allowlist,
    )
    item = next(entry for entry in report["inventory"] if entry["path"].endswith("cache.sqlite"))
    assert item["content_type"] == "application/vnd.sqlite3"
    assert item["sqlite"] == [{"table": "cache", "row_count": 2}]


@pytest.mark.parametrize(
    "files",
    [
        {"usr/share/cache.zip": nested_zip("renamed/GROUND_truth/evaluation.py", b"secret")},
        {"usr/lib/python/site-packages/AppWorld-0.1.dist-info/METADATA": b"Name: appworld"},
        {"usr/share/renamed/tasks/evaluation.py": b"secret"},
        {"safe.bin": b"opaque-not-a-recognized-container"},
        {"usr/share/malformed.zip": b"not really a zip"},
    ],
)
def test_scanner_adversarial_corpus_fails_closed(tmp_path: Path, files: dict[str, bytes]) -> None:
    with pytest.raises(scanner.ScanError):
        scanner.scan_release(
            archive(tmp_path, files),
            allowed_top_levels={next(iter(files)).split("/", 1)[0]},
            exact_digest_allowlist=exact(files),
        )


def test_json_scalar_protected_content_fails_closed(tmp_path: Path) -> None:
    files, allowlist = dpkg_admission(
        {"usr/share/cache.json": b'{"innocent":"renamed/ground_truth/evaluation.py"}'}
    )
    with pytest.raises(scanner.ScanError, match="JSON scalar"):
        scanner.scan_release(
            archive(tmp_path, files), allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"}, exact_digest_allowlist=allowlist
        )


def test_sqlite_row_protected_content_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "protected.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("create table cache (value text)")
    connection.execute("insert into cache values (?)", ("renamed/tasks/evaluation.py",))
    connection.commit()
    connection.close()
    files, allowlist = dpkg_admission(
        {"var/lib/localbench/cache.sqlite": database.read_bytes()}
    )
    with pytest.raises(scanner.ScanError, match="SQLite row value"):
        scanner.scan_release(
            archive(tmp_path, files), allowed_top_levels={"var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"}, exact_digest_allowlist=allowlist
        )


def test_elf_appended_bytes_fail_closed(tmp_path: Path) -> None:
    # Minimal ELF64 header with no tables/segments: the image ends at e_ehsize=64.
    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
    import struct

    struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, 0, 0, 0, 0, 64, 0, 0, 0, 0, 0)
    files, allowlist = dpkg_admission({"usr/bin/tool": bytes(header) + b"smuggled"})
    with pytest.raises(scanner.ScanError, match="appended data"):
        scanner.scan_release(
            archive(tmp_path, files), allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"}, exact_digest_allowlist=allowlist
        )


def test_elf_attacker_chosen_ehsize_zero_tables_and_payload_fails_closed(
    tmp_path: Path,
) -> None:
    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
    import struct

    payload = b"smuggled"
    struct.pack_into(
        "<HHIQQQIHHHHHH",
        header,
        16,
        2,
        62,
        1,
        0,
        0,
        0,
        0,
        len(header) + len(payload),
        0,
        0,
        0,
        0,
        0,
    )
    files, allowlist = dpkg_admission({"usr/bin/tool": bytes(header) + payload})
    with pytest.raises(scanner.ScanError, match="ELF header size"):
        scanner.scan_release(
            archive(tmp_path, files),
            allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"},
            exact_digest_allowlist=allowlist,
        )


@pytest.mark.parametrize("offset_field", ["program", "section"])
def test_elf_zero_count_table_offset_at_eof_fails_closed(
    tmp_path: Path, offset_field: str
) -> None:
    import struct

    payload = b"smuggled"
    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
    eof = len(header) + len(payload)
    phoff = eof if offset_field == "program" else 0
    shoff = eof if offset_field == "section" else 0
    struct.pack_into(
        "<HHIQQQIHHHHHH",
        header,
        16,
        2,
        62,
        1,
        0,
        phoff,
        shoff,
        0,
        64,
        0,
        0,
        0,
        0,
        0,
    )
    files, allowlist = dpkg_admission({"usr/bin/tool": bytes(header) + payload})

    with pytest.raises(scanner.ScanError, match=f"ELF {offset_field}-header table"):
        scanner.scan_release(
            archive(tmp_path, files),
            allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"},
            exact_digest_allowlist=allowlist,
        )


@pytest.mark.parametrize(
    "elf_class,table_kind",
    [
        (64, "program"),
        (64, "section"),
        (32, "program"),
    ],
)
def test_elf_zero_size_table_entry_cannot_claim_trailing_payload(
    tmp_path: Path, elf_class: int, table_kind: str
) -> None:
    import struct

    elf64 = elf_class == 64
    header_size = 64 if elf64 else 52
    entry_size = (56 if elf64 else 32) if table_kind == "program" else (64 if elf64 else 40)
    header = bytearray(header_size)
    header[:16] = b"\x7fELF" + (b"\x02" if elf64 else b"\x01") + b"\x01\x01" + b"\x00" * 9
    table_offset = header_size
    payload = b"smuggled"
    eof = header_size + entry_size + len(payload)
    phoff = table_offset if table_kind == "program" else 0
    shoff = table_offset if table_kind == "section" else 0
    phentsize = entry_size if table_kind == "program" else 0
    phnum = 1 if table_kind == "program" else 0
    shentsize = entry_size if table_kind == "section" else 0
    shnum = 1 if table_kind == "section" else 0
    header_format = "<HHIQQQIHHHHHH" if elf64 else "<HHIIIIIHHHHHH"
    struct.pack_into(
        header_format,
        header,
        16,
        2,
        62 if elf64 else 3,
        1,
        0,
        phoff,
        shoff,
        0,
        header_size,
        phentsize,
        phnum,
        shentsize,
        shnum,
        0,
    )
    entry = bytearray(entry_size)
    if table_kind == "program":
        if elf64:
            struct.pack_into("<IIQQQQ", entry, 0, 0, 0, eof, 0, 0, 0)
        else:
            struct.pack_into("<IIIII", entry, 0, 0, eof, 0, 0, 0)
    else:
        struct.pack_into("<IIQQQQ", entry, 0, 0, 0, 0, 0, eof, 0)
    files, allowlist = dpkg_admission(
        {"usr/bin/tool": bytes(header) + bytes(entry) + payload}
    )

    with pytest.raises(scanner.ScanError, match="appended data"):
        scanner.scan_release(
            archive(tmp_path, files),
            allowed_top_levels={"usr", "var"},
            expected_packages={"dpkg=1.22.6ubuntu6.6"},
            exact_digest_allowlist=allowlist,
        )
