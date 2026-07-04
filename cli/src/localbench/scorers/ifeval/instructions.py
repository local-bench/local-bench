# coding=utf-8
# Copyright 2026 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Official IFEval instruction-id registry.

Checker functions are reimplemented from Google Research IFEval in the sibling
``_checks_*`` modules so localbench can score without extra runtime packages.
"""

from __future__ import annotations

from typing import Final

from localbench.scorers.ifeval import _checks_format, _checks_keywords, _checks_length, _checks_misc
from localbench.scorers.ifeval._types import Checker

INSTRUCTION_DICT: Final[dict[str, Checker]] = {
    "keywords:existence": _checks_keywords.check_keyword_existence,
    "keywords:frequency": _checks_keywords.check_keyword_frequency,
    "keywords:forbidden_words": _checks_keywords.check_forbidden_words,
    "keywords:letter_frequency": _checks_keywords.check_letter_frequency,
    "language:response_language": _checks_keywords.check_response_language,
    "length_constraints:number_sentences": _checks_length.check_number_sentences,
    "length_constraints:number_paragraphs": _checks_length.check_number_paragraphs,
    "length_constraints:number_words": _checks_length.check_number_words,
    "length_constraints:nth_paragraph_first_word": _checks_length.check_nth_paragraph_first_word,
    "detectable_content:number_placeholders": _checks_length.check_number_placeholders,
    "detectable_content:postscript": _checks_length.check_postscript,
    "detectable_format:number_bullet_lists": _checks_format.check_number_bullets,
    "detectable_format:constrained_response": _checks_format.check_constrained_response,
    "detectable_format:number_highlighted_sections": _checks_format.check_number_highlights,
    "detectable_format:multiple_sections": _checks_format.check_multiple_sections,
    "detectable_format:json_format": _checks_format.check_json_format,
    "detectable_format:title": _checks_format.check_title,
    "combination:two_responses": _checks_misc.check_two_responses,
    "combination:repeat_prompt": _checks_misc.check_repeat_prompt,
    "startend:end_checker": _checks_misc.check_end,
    "change_case:capital_word_frequency": _checks_misc.check_capital_word_frequency,
    "change_case:english_capital": _checks_misc.check_english_capital,
    "change_case:english_lowercase": _checks_misc.check_english_lowercase,
    "punctuation:no_comma": _checks_misc.check_no_comma,
    "startend:quotation": _checks_misc.check_quotation,
}
