from __future__ import annotations

import importlib.util
import hashlib
import io
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
        expected_packages={"dpkg=1.22.6ubuntu6.1"},
        exact_digest_allowlist=exact(metadata),
    )
    assert report["regular_file_admission"] == "dpkg-manifest-or-exact-digest-v1"


def test_captured_dpkg_info_fixture_records_real_list_and_md5sums() -> None:
    captured = (Path(__file__).parent / "fixtures" / "dpkg-info-builder-r2.txt").read_text(
        encoding="utf-8"
    )
    assert "/usr/bin/dpkg" in captured
    assert "db5a344aba5b485cb9507afcd6fa297c  usr/bin/dpkg" in captured


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
        allowed_top_levels={"var"}, expected_packages={"dpkg=1.22.6ubuntu6.1"},
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
            expected_packages={"dpkg=1.22.6ubuntu6.1"}, exact_digest_allowlist=allowlist
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
            expected_packages={"dpkg=1.22.6ubuntu6.1"}, exact_digest_allowlist=allowlist
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
            expected_packages={"dpkg=1.22.6ubuntu6.1"}, exact_digest_allowlist=allowlist
        )
