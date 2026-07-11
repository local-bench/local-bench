from __future__ import annotations

import importlib.util
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


def test_scanner_accepts_explicit_minimal_rootfs_inventory(tmp_path: Path) -> None:
    report = scanner.scan_release(
        archive(tmp_path, {"etc/wsl.conf": b"[automount]\nenabled=false\n", "usr/bin/tool": b"#!/bin/sh\n"}),
        allowed_top_levels={"etc", "usr"},
    )
    assert report["result"] == "passed"
    assert report["members"] >= 4
    assert report["inventory"]
    assert all(
        {"path", "size_bytes", "sha256"} <= set(item)
        for item in report["inventory"]
    )


def test_scanner_enforces_positive_path_allowlist(tmp_path: Path) -> None:
    with pytest.raises(scanner.ScanError, match="positive path allowlist"):
        scanner.scan_release(
            archive(tmp_path, {"usr/share/unexpected.txt": b"x"}),
            allowed_top_levels={"usr"},
            allowed_path_prefixes=("usr/bin",),
        )


def test_scanner_enforces_exact_package_allowlist(tmp_path: Path) -> None:
    status = (
        b"Package: expected\nVersion: 1.2.3\nStatus: install ok installed\n\n"
        b"Package: injected\nVersion: 9\nStatus: install ok installed\n"
    )
    with pytest.raises(scanner.ScanError, match="unexpected=.*injected=9"):
        scanner.scan_release(
            archive(tmp_path, {"var/lib/dpkg/status": status}),
            allowed_top_levels={"var"},
            allowed_path_prefixes=("var/lib/dpkg",),
            expected_packages={"expected=1.2.3"},
        )


def test_scanner_enumerates_sqlite_tables_and_row_counts(tmp_path: Path) -> None:
    database = tmp_path / "fixture.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("create table cache (value text)")
    connection.executemany("insert into cache values (?)", [("a",), ("b",)])
    connection.commit()
    connection.close()
    report = scanner.scan_release(
        archive(tmp_path, {"var/lib/localbench/cache.sqlite": database.read_bytes()}),
        allowed_top_levels={"var"},
        allowed_path_prefixes=("var/lib/localbench",),
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
        scanner.scan_release(archive(tmp_path, files), allowed_top_levels={"usr"})
