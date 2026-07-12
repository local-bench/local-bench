from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from suite import build_v2_bfcl_multi_turn as builder

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V1_ITEMS = _REPO_ROOT / "suite" / "v1" / "bfcl_multi_turn.jsonl"


def test_v2_builder_emits_exact_category_partition_of_v1_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original = _load_jsonl(_V1_ITEMS)
    monkeypatch.setattr(builder, "OUT_DIR", tmp_path)
    monkeypatch.setattr(builder.v1_builder, "_load_candidates", lambda: original)

    assert builder.main() == 0

    base = _load_jsonl(tmp_path / "bfcl_multi_turn_base.jsonl")
    long_context = _load_jsonl(tmp_path / "bfcl_multi_turn_long_context.jsonl")
    assert len(base) == 50
    assert len(long_context) == 50
    assert Counter(str(row["category"]) for row in base) == {"multi_turn_base": 50}
    assert Counter(str(row["category"]) for row in long_context) == {
        "multi_turn_long_context": 50
    }
    assert _by_source_id([*base, *long_context]) == _by_source_id(original)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _by_source_id(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["source_id"]): row for row in rows}
