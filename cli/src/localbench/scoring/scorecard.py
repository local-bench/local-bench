"""Scorecard identity — freezes the SCORING object, not just the item set.

The item set is pinned by `suite.json`'s sha256 (the *suite* identity). But the
headline *score* also depends on the axis weights/roles (the registry), the per-bench
scorers, and the CI method — none of which live in `suite.json`. A one-line registry
edit could silently re-score every historical run while the suite identity stayed the
same; and `web/build_data` reads the *current* registry weights, so history could be
reinterpreted with no visible change.

`scorecard_identity()` closes that hole: it hashes the registry digest + scorer
versions + CI method into a stable `scorecard_id` recorded in every run manifest, so a
run is self-describing about HOW it was scored. Reweighting or promoting a candidate
bumps `SCORECARD_VERSION` and changes the id; old runs stay reproducible under their
own recorded scorecard. (Oracle red-team, 2026-06-19, finding #1.)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from typing import Final

from localbench._types import JsonObject
from localbench.scoring.axes import AXES, Axis

# Human-facing scorecard label. BUMP whenever the scoring object changes deliberately
# (a weight edit, a scorer-version bump, a CI-method change).
SCORECARD_VERSION: Final = "scorecard-v1.2"

# How interval estimates are produced (part of scoring identity; the iteration count is
# a per-call parameter, not part of identity).
CI_METHOD: Final = "stratified-nonparametric-bootstrap-percentile"

# Per-bench scorer+extractor version. A bench's scoring pipeline (answer extraction +
# scoring) is versioned as a unit; bump MANUALLY when its logic changes. `test_scorecard`
# asserts every registry/exec bench appears here (guards presence, not freshness). This is
# a deliberate v1 tradeoff: hashing scorer SOURCE would trip the digest on cosmetic edits
# (false drift), so we accept a manual bump + the registry digest (which IS auto-derived).
SCORER_VERSIONS: Final[dict[str, str]] = {
    "mmlu_pro": "1",
    "ifbench": "1",
    "olymmath_hard": "1",
    "amo": "1",
    "ruler_32k": "1",
    "bfcl": "1",
    "bfcl_multi_turn": "1",
    "lcb": "1",
    "bigcodebench_hard": "1",
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
            field.name: (
                list(value)
                if isinstance(value := getattr(axis, field.name), tuple)
                else value
            )
            for field in fields(Axis)
        }
        for axis in AXES
    ]


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def registry_digest() -> str:
    """sha256 of the weight registry (roles + weights + bench membership).

    Changes whenever any axis weight, role, or bench membership changes — the thing
    that previously could move a published score with no identity change.
    """
    return _digest(_registry_payload())


def scorecard_identity() -> JsonObject:
    """The frozen scoring-object identity recorded in every run manifest.

    `scorecard_id` hashes the version + registry digest + scorer versions + CI method;
    the full `registry` payload is embedded so an OLD run stays self-describing even
    after the live registry is reweighted.
    """
    components: JsonObject = {
        "scorecard_version": SCORECARD_VERSION,
        "registry_digest": registry_digest(),
        "scorer_versions": dict(SCORER_VERSIONS),
        "ci_method": CI_METHOD,
    }
    return {
        **components,
        "scorecard_id": _digest(components),
        "registry": _registry_payload(),
    }
