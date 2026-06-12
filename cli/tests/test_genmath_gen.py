"""Tests for the generated-math suite builder."""

from __future__ import annotations

import random
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "suite"
if str(SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(SUITE_DIR))

from genmath_gen import TEMPLATES, Answer, answer_to_string
from genmath_gen.build import DEFAULT_SEED, build_itemsets, jsonl_bytes


def test_templates_when_sampled_render_valid_numeric_items() -> None:
    # Given the generated-math template registry.
    # When each template is sampled over deterministic seeds.
    for template in TEMPLATES:
        for offset in range(100):
            params = template.sample(random.Random(DEFAULT_SEED + offset))
            statement = template.render(params)
            answer = template.answer(params)

            # Then statements and answers satisfy the numeric scorer contract.
            assert "{" not in statement
            assert "}" not in statement
            assert statement.endswith(
                (
                    "Give your final answer as a single number.",
                    "Give your final answer as a single number or fraction.",
                ),
            )
            assert isinstance(answer, int | Fraction)
            assert abs(answer) < 1_000_000_000
            if isinstance(answer, Fraction):
                assert answer.denominator < 1000
            assert answer_to_string(answer)


def test_combinatorics_and_probability_when_bruteforced_match_closed_forms() -> None:
    # Given every counting and probability template.
    checked = 0

    # When comparing the closed form with its independent brute-force checker.
    for template in TEMPLATES:
        if template.category not in {"combinatorics", "probability"}:
            continue
        assert template.brute_force is not None
        for offset in range(50):
            params = template.sample(random.Random(17_000 + offset))
            assert template.answer(params) == template.brute_force(params)
            checked += 1

    # Then all applicable templates have been independently checked.
    assert checked >= 50


def test_algebra_and_geometry_when_verified_pass_substitution_checks() -> None:
    # Given algebraic and geometric templates.
    checked = 0

    # When running their independent recomputation checks.
    for template in TEMPLATES:
        if template.category not in {"algebra", "geometry"}:
            continue
        assert template.verify is not None
        for offset in range(50):
            params = template.sample(random.Random(29_000 + offset))
            assert template.verify(params, template.answer(params))
            checked += 1

    # Then every such template participates in the verification loop.
    assert checked >= 50


def test_build_when_seed_repeats_produces_identical_jsonl_bytes() -> None:
    # Given two generated builds with the same seed.
    first = build_itemsets(DEFAULT_SEED)
    second = build_itemsets(DEFAULT_SEED)

    # When serializing the standard and quick sets.
    first_standard = jsonl_bytes(first.standard)
    second_standard = jsonl_bytes(second.standard)
    first_quick = jsonl_bytes(first.quick)
    second_quick = jsonl_bytes(second.quick)

    # Then both JSONL files are byte-identical.
    assert first_standard == second_standard
    assert first_quick == second_quick


def test_standard_set_when_built_has_required_distribution() -> None:
    # Given a generated standard item set.
    itemsets = build_itemsets(DEFAULT_SEED)
    standard = itemsets.standard
    quick = itemsets.quick

    # When summarizing template, category, and difficulty distribution.
    by_template = Counter(str(item["template"]) for item in standard)
    by_category = Counter(str(item["category"]) for item in standard)
    by_difficulty = Counter(str(item["difficulty"]) for item in standard)
    template_categories = Counter(template.category for template in TEMPLATES)

    # Then the suite satisfies the public distribution contract.
    assert len(TEMPLATES) >= 60
    assert all(count >= 6 for count in template_categories.values())
    assert len(standard) == 120
    assert len(quick) == 40
    assert len({str(item["id"]) for item in standard}) == 120
    assert all(count <= 2 for count in by_template.values())
    assert all(count >= 10 for count in by_category.values())
    assert 30 <= by_difficulty["easy"] <= 42
    assert 45 <= by_difficulty["medium"] <= 65
    assert 20 <= by_difficulty["hard"] <= 40
    assert {str(item["id"]) for item in quick} <= {str(item["id"]) for item in standard}


def test_standard_items_when_built_have_audit_fields() -> None:
    # Given generated standard items.
    standard = build_itemsets(DEFAULT_SEED).standard

    # When inspecting each row.
    for item in standard:
        answer: Answer = item["answer"]

        # Then the JSONL audit contract is present and numeric.
        assert str(item["id"]).startswith("genmath-v0-")
        assert item["template"]
        assert item["category"]
        assert item["difficulty"]
        assert str(item["statement"]).endswith(
            (
                "Give your final answer as a single number.",
                "Give your final answer as a single number or fraction.",
            ),
        )
        assert isinstance(answer, str)
        assert item["params"]
