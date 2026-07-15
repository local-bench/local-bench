from __future__ import annotations

import json
from pathlib import Path

from scripts.scan_c6_existing_rows import classify_published_rows


def test_impact_scan_golden_classifies_every_published_row_conservatively() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "c6-impact-scan-golden.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    observed = classify_published_rows(
        fixture["published_index"],
        fixture["board"],
    )

    assert observed == fixture["expected"]
