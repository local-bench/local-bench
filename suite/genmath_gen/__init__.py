"""Standalone generated-math benchmark package."""

from __future__ import annotations

from genmath_gen.algebra import templates as algebra_templates
from genmath_gen.arithmetic import templates as arithmetic_templates
from genmath_gen.combinatorics import templates as combinatorics_templates
from genmath_gen.geometry import templates as geometry_templates
from genmath_gen.number_theory import templates as number_theory_templates
from genmath_gen.probability import templates as probability_templates
from genmath_gen.rates_word import templates as rates_word_templates
from genmath_gen.models import Answer, ParamMap, Params, Template
from genmath_gen.models import answer_to_string

TEMPLATES: tuple[Template, ...] = tuple(
    arithmetic_templates()
    + number_theory_templates()
    + algebra_templates()
    + combinatorics_templates()
    + probability_templates()
    + geometry_templates()
    + rates_word_templates()
)

__all__ = [
    "Answer",
    "ParamMap",
    "Params",
    "TEMPLATES",
    "Template",
    "answer_to_string",
]
