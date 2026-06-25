"""Pytest that board_v2.json (the live scorer-side source of truth) is in sync with
web/public/data/index.json (rendered site data) so CI catches stale web data.

board_v2.json carries the agentic-led Local Intelligence Index v2.0 and is what
web/build_data.py renders. board_v1.json is the FROZEN historical K+I artifact
(scorecard v1.3) kept for provenance — it is NOT the render source, so the
site-parity contract here is against board_v2.json.

What we compare
---------------
The site is a PURE RENDERER of board_v2.json for ranked rows (METHODOLOGY-v2.0 —
no re-derived Index math in the web layer): web/build_data.py loads the board and,
for every ranked row, renders the board's verbatim composite/headline-axis
intervals.  So both the *point estimate* (deterministic from the scored items) AND
the CI *bounds* (hi/lo, and their _raw counterparts) must match the board — see
test (e).  This closes the prior gap, where the web build re-bootstrapped with a
different seed and weighted per-axis quantiles instead of the board's joint
item-level composite CI, so the bounds diverged.  Sort order (by composite point
desc) and per-model presence are also contractual.

Gaps noted where the two artifacts structurally differ:
- CI bounds (hi/lo, lo_raw/hi_raw): COMPARED across all headline axes (agentic,
  knowledge, instruction) — the site renders the board's bounds verbatim for
  ranked rows, so they are exact (test (e), tol 1e-9).
- model_label: web catalog may remap the display name (e.g. "Qwen3.6 27B"
  vs "Qwen3.6-27B") — not compared here.
- candidate/experimental axes (math, coding, long_context) carry weight 0.0 in
  AXES; test (d) verifies that a 0-weight axis never drives the composite by
  asserting the composite point equals the REGISTRY-WEIGHTED sum of the headline
  axes (Agentic 0.70 / Knowledge 0.15 / Instruction 0.15).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.scoring.axes import web_composite_weights

# --- paths -------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
# board_v2.json is the LIVE scorer artifact the site renders (agentic-led Index v2.0).
# board_v1.json is the FROZEN historical K+I artifact and is NOT what the web renders;
# the site-parity contract is therefore against board_v2.json.
BOARD_PATH = REPO_ROOT / "cli" / "runs" / "board" / "board_v2.json"
INDEX_PATH = REPO_ROOT / "web" / "public" / "data" / "index.json"

# Tolerance matches the one used inside check_board_parity().
TOLERANCE = 1e-6

# CI bounds are RENDERED verbatim from the board (not recomputed), so they must be
# (near-)exact, not merely close. Float round-trip through json.dump only — 1e-9.
BOUNDS_TOLERANCE = 1e-9

# Headline axes + their composite weights, derived from the canonical registry
# (METHODOLOGY-v2.0: Agentic 0.70 / Knowledge 0.15 / Instruction 0.15). Deriving from
# the registry means this gate tracks any future re-weight or promotion automatically.
HEADLINE_WEB_WEIGHTS = {key: w for key, w in web_composite_weights().items() if w > 0.0}
HEADLINE_WEB_KEYS = tuple(HEADLINE_WEB_WEIGHTS)

# The four CI-bound fields rendered straight from the board (display + raw). The
# point fields are covered by tests (b); these are the bounds that previously diverged.
BOUND_FIELDS = ("lo", "hi", "lo_raw", "hi_raw")


# --- helpers -----------------------------------------------------------------

def _point(obj: dict | None) -> float | None:
    if obj is None:
        return None
    p = obj.get("point")
    return float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None


def _slug(m: dict) -> str | None:
    s = m.get("slug")
    return s if isinstance(s, str) and s else None


def _is_ranked(m: dict) -> bool:
    return m.get("ranked") is True


def _composite_point(m: dict) -> float | None:
    return _point(m.get("composite") if isinstance(m.get("composite"), dict) else None)


def _axis_point(m: dict, axis: str) -> float | None:
    axes = m.get("axes")
    if not isinstance(axes, dict):
        return None
    return _point(axes.get(axis) if isinstance(axes.get(axis), dict) else None)


def _bound(obj: dict | None, field: str) -> float | None:
    if not isinstance(obj, dict):
        return None
    v = obj.get(field)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _composite_obj(m: dict) -> dict | None:
    c = m.get("composite")
    return c if isinstance(c, dict) else None


def _axis_obj(m: dict, axis: str) -> dict | None:
    axes = m.get("axes")
    if not isinstance(axes, dict):
        return None
    a = axes.get(axis)
    return a if isinstance(a, dict) else None


# --- fixtures ----------------------------------------------------------------

@pytest.fixture(scope="module")
def board() -> dict:
    assert BOARD_PATH.exists(), f"board_v1.json not found at {BOARD_PATH}"
    return json.loads(BOARD_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def index() -> dict:
    assert INDEX_PATH.exists(), f"index.json not found at {INDEX_PATH}"
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def board_ranked(board: dict) -> list[dict]:
    """Ranked models from board_v2.json, in board order."""
    return [m for m in board["models"] if _is_ranked(m)]


@pytest.fixture(scope="module")
def index_by_slug(index: dict) -> dict[str, dict]:
    return {_slug(m): m for m in index["models"] if _slug(m) is not None}


# --- (a) every ranked board model exists in the web index by slug ------------

def test_every_ranked_board_model_present_in_web_index(
    board_ranked: list[dict],
    index_by_slug: dict[str, dict],
) -> None:
    """(a) Every model marked ranked=True in board_v2.json must appear in the
    web index by slug.  If this fails, web/build_data.py was not re-run after
    a new run was added to the scorer-side board, or the slugs diverged.
    """
    missing = [
        _slug(m)
        for m in board_ranked
        if _slug(m) not in index_by_slug
    ]
    assert not missing, (
        f"Ranked board slugs not found in web index: {missing}. "
        "Re-run `python web/build_data.py` to regenerate the web index."
    )


# --- (b) composite point + axis points match within tolerance ----------------

def test_composite_points_match(
    board_ranked: list[dict],
    index_by_slug: dict[str, dict],
) -> None:
    """(b-composite) Board composite.point == web index composite.point within 1e-6.

    CI bounds (hi/lo) are intentionally excluded — the web re-bootstraps
    independently and those values will differ.
    """
    mismatches: list[str] = []
    for m in board_ranked:
        slug = _slug(m)
        if slug is None:
            continue
        web_m = index_by_slug.get(slug)
        if web_m is None:
            continue  # covered by (a)
        b_pt = _composite_point(m)
        w_pt = _composite_point(web_m)
        if b_pt is None or w_pt is None or abs(b_pt - w_pt) > TOLERANCE:
            mismatches.append(
                f"{slug}: board={b_pt} web={w_pt} diff={None if b_pt is None or w_pt is None else abs(b_pt - w_pt):.2e}"
            )
    assert not mismatches, "composite.point divergence:\n" + "\n".join(mismatches)


def test_headline_axis_points_match(
    board_ranked: list[dict],
    index_by_slug: dict[str, dict],
) -> None:
    """(b-axes) Board axes.{knowledge,instruction}.point == web index within 1e-6.

    Headline axes only — candidates/experimental are 0-weight and may not be
    present on both sides in all configurations.
    """
    mismatches: list[str] = []
    for m in board_ranked:
        slug = _slug(m)
        if slug is None:
            continue
        web_m = index_by_slug.get(slug)
        if web_m is None:
            continue  # covered by (a)
        for axis in HEADLINE_WEB_KEYS:
            b_pt = _axis_point(m, axis)
            w_pt = _axis_point(web_m, axis)
            if b_pt is None and w_pt is None:
                continue  # axis absent on both sides — OK
            if b_pt is None or w_pt is None or abs(b_pt - w_pt) > TOLERANCE:
                mismatches.append(
                    f"{slug}.axes.{axis}: board={b_pt} web={w_pt}"
                )
    assert not mismatches, "axis point divergence:\n" + "\n".join(mismatches)


# --- (c) ranked sort order matches ------------------------------------------

def test_ranked_sort_order_matches(
    board_ranked: list[dict],
    index_by_slug: dict[str, dict],
) -> None:
    """(c) The composite-descending rank order among ranked models is identical
    in board_v2.json and the web index.

    The board is the canonical ordering.  The web sorts independently; if
    index.json rows appear in a different relative order for the ranked subset,
    the site would display a different leaderboard than the scorer intended.

    Note: the web index may contain more models (unranked catalog entries) — we
    compare only the ranked subset's relative ordering.
    """
    board_slugs_ordered = [_slug(m) for m in board_ranked if _slug(m) is not None]

    # Pull web index models that are ranked, keyed by slug for ordering lookup.
    web_ranked = [
        m for m in index_by_slug.values()
        if _is_ranked(m) and _slug(m) in set(board_slugs_ordered)
    ]
    # Sort web ranked by composite point descending (same rule as board).
    # Ties broken by slug for determinism.
    web_ranked_sorted = sorted(
        web_ranked,
        key=lambda m: (_composite_point(m) or 0.0, _slug(m) or ""),
        reverse=True,
    )
    web_slugs_ordered = [_slug(m) for m in web_ranked_sorted if _slug(m) is not None]

    assert board_slugs_ordered == web_slugs_ordered, (
        f"Rank order divergence.\n"
        f"  board: {board_slugs_ordered}\n"
        f"  web:   {web_slugs_ordered}"
    )


# --- (d) candidate/0-weight axes do NOT drive the Index ----------------------

def test_zero_weight_axes_do_not_contribute_to_composite(
    board_ranked: list[dict],
) -> None:
    """(d) The composite point equals the REGISTRY-WEIGHTED sum of the headline
    axes (Agentic 0.70 / Knowledge 0.15 / Instruction 0.15, per METHODOLOGY-v2.0).
    If a 0-weight candidate (math, coding, long_context) were accidentally
    included in the composite, this assertion would fail.

    Only models where every headline axis point is present are checked; models
    that were measured on only some axes are skipped with a note.
    """
    skipped: list[str] = []
    mismatches: list[str] = []

    for m in board_ranked:
        slug = _slug(m) or "<no-slug>"
        axis_pts = {ax: _axis_point(m, ax) for ax in HEADLINE_WEB_KEYS}
        if any(p is None for p in axis_pts.values()):
            skipped.append(slug)
            continue
        # Composite must equal the registry-weighted sum of the headline axes, so a
        # 0-weight candidate (math, coding, long_context) can never drive the Index.
        expected = sum(axis_pts[ax] * HEADLINE_WEB_WEIGHTS[ax] for ax in HEADLINE_WEB_KEYS)  # type: ignore[operator]
        actual = _composite_point(m)
        if actual is None or abs(actual - expected) > TOLERANCE:
            mismatches.append(
                f"{slug}: composite={actual} expected_from_headline={expected:.8f} diff={None if actual is None else abs(actual - expected):.2e}"
            )

    if skipped:
        # Not a failure — log for visibility.
        import warnings
        warnings.warn(
            f"Skipped composite-weight check for models missing a headline axis: {skipped}",
            stacklevel=2,
        )

    assert not mismatches, (
        "Composite diverges from headline-only equal-weight average — "
        "a 0-weight axis may have been accidentally included:\n"
        + "\n".join(mismatches)
    )


# --- (e) CI bounds match: the site RENDERS the board's bounds verbatim --------

def test_ci_bounds_match_board(
    board_ranked: list[dict],
    index_by_slug: dict[str, dict],
) -> None:
    """(e) For every ranked board model, the web index's composite and headline-axis
    CI bounds (lo/hi AND lo_raw/hi_raw) equal board_v2.json within 1e-9.

    The site is a pure renderer of the immutable board artifact (METHODOLOGY-v2.0):
    web/build_data.py renders the board's intervals for ranked rows rather than re-
    deriving them (the old re-bootstrap used a different seed and summed per-axis
    quantiles instead of the board's joint item-level composite CI, so bounds diverged).
    A reader who recomputes from board_v2.json must get exactly the error bars the site
    shows, so this is (near-)exact, not a loose tolerance.
    """
    mismatches: list[str] = []
    for m in board_ranked:
        slug = _slug(m)
        if slug is None:
            continue
        web_m = index_by_slug.get(slug)
        if web_m is None:
            continue  # covered by (a)
        # Composite bounds.
        b_obj = _composite_obj(m)
        w_obj = _composite_obj(web_m)
        for field in BOUND_FIELDS:
            b_v = _bound(b_obj, field)
            w_v = _bound(w_obj, field)
            if b_v is None or w_v is None or abs(b_v - w_v) > BOUNDS_TOLERANCE:
                mismatches.append(
                    f"{slug}.composite.{field}: board={b_v} web={w_v} "
                    f"diff={None if b_v is None or w_v is None else f'{abs(b_v - w_v):.2e}'}"
                )
        # Headline-axis bounds.
        for axis in HEADLINE_WEB_KEYS:
            b_ax = _axis_obj(m, axis)
            w_ax = _axis_obj(web_m, axis)
            if b_ax is None and w_ax is None:
                continue  # axis absent on both sides — OK
            for field in BOUND_FIELDS:
                b_v = _bound(b_ax, field)
                w_v = _bound(w_ax, field)
                if b_v is None or w_v is None or abs(b_v - w_v) > BOUNDS_TOLERANCE:
                    mismatches.append(
                        f"{slug}.axes.{axis}.{field}: board={b_v} web={w_v} "
                        f"diff={None if b_v is None or w_v is None else f'{abs(b_v - w_v):.2e}'}"
                    )
    assert not mismatches, (
        "CI bound divergence — the site must render board_v2.json bounds verbatim "
        "for ranked rows (pure renderer, METHODOLOGY-v2.0):\n" + "\n".join(mismatches)
    )
