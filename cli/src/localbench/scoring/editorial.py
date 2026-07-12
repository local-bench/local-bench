"""Editorial index labels derived from frozen scoring coverage identity."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from localbench._types import JsonValue
from localbench.suite_release import (
    coverage_profile_for_benches,
    coverage_profile_for_id,
)

INDEX_VERSION_V3: Final = "index-v3.0"
INDEX_VERSION_V4: Final = "index-v4.0"
SEASON_2_COVERAGE_PROFILE_ID: Final = "full-exec-tooluse-5axis-v2"


def index_version_for_coverage_profile(profile_id: str) -> str:
    """Return the editorial label for a validated coverage-profile identity."""
    if profile_id == "custom-partial-v1":
        return INDEX_VERSION_V3
    profile = coverage_profile_for_id(profile_id)
    return (
        INDEX_VERSION_V4
        if profile.profile_id == SEASON_2_COVERAGE_PROFILE_ID
        else INDEX_VERSION_V3
    )


def index_version_for_benches(benches: set[str]) -> str:
    profile = coverage_profile_for_benches(benches)
    if profile.profile_id == SEASON_2_COVERAGE_PROFILE_ID:
        return INDEX_VERSION_V4
    return INDEX_VERSION_V3


def record_index_version(record: Mapping[str, JsonValue]) -> str:
    value = record.get("index_version")
    if not isinstance(value, str) or not value:
        raise ValueError("scored record must carry a non-empty index_version")
    return value
