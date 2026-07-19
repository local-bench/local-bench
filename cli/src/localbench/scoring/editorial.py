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
# index-v4.1 is the 2026-07-17 season-2 reweight. index-v4.2 keeps those weights
# and corrects Agentic to AppWorld-only so project and community rows use the
# same protocol. Historical public labels remain accepted and are never narrowed.
INDEX_VERSION_V4_1: Final = "index-v4.1"
INDEX_VERSION_V4_2: Final = "index-v4.2"
INDEX_VERSION_V4: Final = INDEX_VERSION_V4_2
OLDER_INDEX_VERSIONS: Final = frozenset(
    {INDEX_VERSION_V3, "index-v4.0", INDEX_VERSION_V4_1}
)
SEASON_2_COVERAGE_PROFILE_ID: Final = "full-exec-tooluse-5axis-v2"
CURRENT_COVERAGE_PROFILE_IDS: Final = frozenset(
    {
        SEASON_2_COVERAGE_PROFILE_ID,
        "full-exec-6axis-v1",
    },
)


def index_version_for_coverage_profile(profile_id: str) -> str:
    """Return the editorial label for a validated coverage-profile identity."""
    if profile_id == "custom-partial-v1":
        return INDEX_VERSION_V3
    profile = coverage_profile_for_id(profile_id)
    return INDEX_VERSION_V4 if profile.profile_id in CURRENT_COVERAGE_PROFILE_IDS else INDEX_VERSION_V3


def index_version_for_benches(benches: set[str]) -> str:
    profile = coverage_profile_for_benches(benches)
    if profile.profile_id in CURRENT_COVERAGE_PROFILE_IDS:
        return INDEX_VERSION_V4
    return INDEX_VERSION_V3


def record_index_version(record: Mapping[str, JsonValue]) -> str:
    value = record.get("index_version")
    if not isinstance(value, str) or not value:
        raise ValueError("scored record must carry a non-empty index_version")
    return value
