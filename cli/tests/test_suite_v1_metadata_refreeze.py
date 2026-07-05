from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_REFROZEN_FILES = (
    "suite/v1/bigcodebench_hard.jsonl",
    "suite/v1/olymmath_hard.jsonl",
    "suite/v1/amo.jsonl",
)


@pytest.mark.parametrize("relative_path", _REFROZEN_FILES)
def test_refrozen_suite_v1_items_only_add_metadata(relative_path: str) -> None:
    baseline = _git_jsonl(relative_path)
    current = _disk_jsonl(_REPO / relative_path)

    assert len(current) == len(baseline)
    for index, (old, new) in enumerate(zip(baseline, current, strict=True), start=1):
        assert old.get("id") == new.get("id"), f"{relative_path}:{index} item id changed"
        for key, value in old.items():
            assert new.get(key) == value, f"{relative_path}:{old.get('id')} changed pre-existing field {key}"


def _git_jsonl(relative_path: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=_REPO,
        capture_output=True,
        check=True,
    )
    text = result.stdout.decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _disk_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
