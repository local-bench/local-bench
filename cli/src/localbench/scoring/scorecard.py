"""Scorecard identity — freezes the SCORING object, not just the item set.

The item set is pinned by `suite.json`'s sha256 (the *suite* identity). But the
headline *score* also depends on the axis weights/roles (the registry), the per-bench
scorers, and the CI method — none of which live in `suite.json`. A one-line registry
edit could silently re-score every historical run while the suite identity stayed the
same; and `web/build_data` reads the *current* registry weights, so history could be
reinterpreted with no visible change.

`scorecard_identity()` closes that hole: it hashes the scoring registry digest,
scorer versions, CI method, lane spec digest, and selected execution-profile digest
into a stable `scorecard_id` recorded in every run manifest. Reweighting or promoting
a candidate bumps `SCORECARD_VERSION` and changes the id; adding unrelated execution
profiles only changes the informational profile-catalog digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields, is_dataclass
from typing import Final

from localbench._types import JsonObject
from localbench.coding_exec.ast_gate import AST_GATE_REV
from localbench.coding_exec.extract import EXTRACTOR_REV
from localbench.coding_exec.program import SENTINEL_SCHEME_REV
from localbench.coding_exec.score import CODING_SCOREABLE_REV
from localbench.lane_spec import DEFAULT_LANE_SPEC_ID, lane_spec_digest
from localbench.reasoning_registry import (
    execution_profile_digest,
    execution_profile_for_id,
    execution_profile_payload,
    reasoning_registry_payload,
)
from localbench.scoring.axes import AXES, Axis

# Human-facing scorecard label. BUMP whenever the scoring object changes deliberately
# (a weight edit, a scorer-version bump, a CI-method change).
# "6" = index-v4.1 reweight (tool_use 0.20->0.25, others scaled by 15/16) plus the
# "Tool Use"->"Agentic" display rename (display is hashed into the registry digest).
SCORECARD_VERSION: Final = "6"

# How interval estimates are produced (part of scoring identity; the iteration count is
# a per-call parameter, not part of identity).
CI_METHOD: Final = "stratified-nonparametric-bootstrap-percentile"

# Per-bench scorer+extractor version. A bench's scoring pipeline (answer extraction +
# scoring) is versioned as a unit; bump MANUALLY when its logic changes. `test_scorecard`
# asserts every registry/exec bench appears here (guards presence, not freshness). This is
# a deliberate v1 tradeoff: hashing scorer SOURCE would trip the digest on cosmetic edits
# (false drift), so we accept a manual bump + the registry digest (which IS auto-derived).
SCORER_VERSIONS: Final[dict[str, str]] = {
    "appworld_c": "1",
    "mmlu_pro": "1",
    "ifbench": "1",
    "olymmath_hard": "1",
    "amo": "1",
    "ruler_32k": "1",
    "bfcl": "1",
    "bfcl_multi_turn": "1",
    "bfcl_multi_turn_base": "1",
    "bfcl_multi_turn_long_context": "1",
    "lcb": "1",
    "tc_json_v1": "1",
    "bigcodebench_hard": f"1+{CODING_SCOREABLE_REV}+{AST_GATE_REV}+{SENTINEL_SCHEME_REV}",
    # suite-v0 legacy benches (back-compat scoring)
    "supergpqa": "1",
    "ifeval": "1",
    "genmath": "1",
}

# Exec-lane benches that live outside the AXES registry (their own orchestrator) but
# still need a frozen scorer version. Kept here so the drift guard covers them.
EXEC_BENCHES: Final[tuple[str, ...]] = ("bigcodebench_hard",)


def _registry_payload() -> list[JsonObject]:
    """Canonical, order-preserving serialization of the weight registry.

    Hashes EVERY `Axis` field (not a hand-picked subset) so any scoring- OR
    display-affecting change moves the digest — including `web_key`/`web_display`,
    which steer the web composite. Tuples are normalized to lists for stable JSON.
    """
    return [
        {
            field.name: _registry_value(getattr(axis, field.name))
            for field in fields(Axis)
        }
        for axis in AXES
    ]


def _registry_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _registry_value(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple | list):
        return [_registry_value(item) for item in value]
    return value


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def registry_digest() -> str:
    """sha256 of the weight registry (roles + weights + bench membership).

    Changes whenever any axis weight, role, or bench membership changes — the thing
    that previously could move a published score with no identity change.
    """
    return _digest(_registry_payload())


def scorecard_identity(
    execution_profile_id: str | None = None,
    *,
    lane_spec_id: str = DEFAULT_LANE_SPEC_ID,
) -> JsonObject:
    """The frozen scoring-object identity recorded in every run manifest.

    `scorecard_id` hashes the version, scoring registry digest, scorer versions,
    CI method, lane spec digest, and the selected execution profile digest only.
    The full scoring `registry` payload and selected `execution_profile` payload are
    embedded so an OLD run stays self-describing after live catalogs change.
    """
    execution_profile_entry = (
        None if execution_profile_id is None else execution_profile_for_id(execution_profile_id)
    )
    if execution_profile_id is not None and execution_profile_entry is None:
        raise ValueError(f"unknown execution profile: {execution_profile_id}")
    profile_payload = (
        None
        if execution_profile_entry is None
        else execution_profile_payload(execution_profile_entry)
    )
    profile_digest = (
        None
        if execution_profile_entry is None
        else execution_profile_digest(execution_profile_entry)
    )
    components: JsonObject = {
        "scorecard_version": SCORECARD_VERSION,
        "registry_digest": registry_digest(),
        "scorer_versions": dict(SCORER_VERSIONS),
        "extractor_rev": EXTRACTOR_REV,
        "coding_ast_gate_rev": AST_GATE_REV,
        "coding_sentinel_scheme_rev": SENTINEL_SCHEME_REV,
        "ci_method": CI_METHOD,
        "lane_spec_digest": lane_spec_digest(lane_spec_id),
        "execution_profile_id": execution_profile_id,
        "execution_profile_digest": profile_digest,
    }
    return {
        **components,
        "lane_spec_id": lane_spec_id,
        "scorecard_id": _digest(components),
        # Informational only: excluded from scorecard_id so adding profiles does not
        # invalidate runs that used other profiles.
        "profile_catalog_digest": _digest(reasoning_registry_payload()),
        "registry": _registry_payload(),
        "execution_profile": profile_payload,
    }
