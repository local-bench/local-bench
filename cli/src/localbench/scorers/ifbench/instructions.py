# Copyright 2025 Allen Institute for AI.
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

from __future__ import annotations

from typing import Final

from localbench.scorers.ifbench import (
    _checks_count,
    _checks_custom,
    _checks_format,
    _checks_ratio,
    _checks_repeat,
    _checks_sentence,
    _checks_words,
)
from localbench.scorers.ifbench._types import Checker

INSTRUCTION_DICT: Final[dict[str, Checker]] = {
    "count:word_count_range": _checks_count.check_word_count_range,
    "count:unique_word_count": _checks_count.check_unique_word_count,
    "ratio:stop_words": _checks_ratio.check_stop_words,
    "ratio:sentence_type": _checks_ratio.check_sentence_type,
    "ratio:sentence_balance": _checks_ratio.check_sentence_balance,
    "count:conjunctions": _checks_count.check_conjunctions,
    "count:person_names": _checks_count.check_person_names,
    "ratio:overlap": _checks_ratio.check_overlap,
    "count:numbers": _checks_count.check_numbers,
    "words:alphabet": _checks_words.check_alphabet,
    "words:vowel": _checks_words.check_vowel,
    "words:consonants": _checks_words.check_consonants,
    "sentence:alliteration_increment": _checks_sentence.check_alliteration_increment,
    "words:palindrome": _checks_words.check_palindrome,
    "count:punctuation": _checks_count.check_punctuation,
    "format:parentheses": _checks_format.check_parentheses,
    "format:quotes": _checks_format.check_quotes,
    "words:prime_lengths": _checks_words.check_prime_lengths,
    "format:options": _checks_format.check_options,
    "format:newline": _checks_format.check_newline,
    "format:emoji": _checks_format.check_emoji,
    "ratio:sentence_words": _checks_ratio.check_sentence_words,
    "count:words_japanese": _checks_count.check_words_japanese,
    "words:repeats": _checks_words.check_repeats,
    "sentence:keyword": _checks_sentence.check_keyword,
    "count:pronouns": _checks_count.check_pronouns,
    "words:odd_even_syllables": _checks_words.check_odd_even_syllables,
    "words:last_first": _checks_sentence.check_last_first,
    "words:paragraph_last_first": _checks_words.check_paragraph_last_first,
    "sentence:increment": _checks_sentence.check_increment,
    "words:no_consecutive": _checks_words.check_no_consecutive,
    "format:line_indent": _checks_format.check_line_indent,
    "format:quote_unquote": _checks_format.check_quote_unquote,
    "format:list": _checks_format.check_list,
    "format:thesis": _checks_format.check_thesis,
    "format:sub-bullets": _checks_format.check_sub_bullets,
    "format:no_bullets_bullets": _checks_format.check_no_bullets_bullets,
    "custom:multiples": _checks_custom.check_multiples,
    "custom:mcq_count_length": _checks_custom.check_mcq_count_length,
    "custom:reverse_newline": _checks_custom.check_reverse_newline,
    "custom:word_reverse": _checks_custom.check_word_reverse,
    "custom:character_reverse": _checks_custom.check_character_reverse,
    "custom:sentence_alphabet": _checks_sentence.check_sentence_alphabet,
    "custom:european_capitals_sort": _checks_custom.check_european_capitals_sort,
    "custom:csv_city": _checks_custom.check_csv_city,
    "custom:csv_special_character": _checks_custom.check_csv_special_character,
    "custom:csv_quotes": _checks_custom.check_csv_quotes,
    "custom:date_format_list": _checks_custom.check_date_format_list,
    "count:keywords_multiple": _checks_count.check_keywords_multiple,
    "words:keywords_specific_position": _checks_words.check_keywords_specific_position,
    "words:words_position": _checks_words.check_words_position,
    "repeat:repeat_change": _checks_repeat.check_repeat_change,
    "repeat:repeat_simple": _checks_repeat.check_repeat_simple,
    "repeat:repeat_span": _checks_repeat.check_repeat_span,
    "format:title_case": _checks_format.check_title_case,
    "format:output_template": _checks_format.check_output_template,
    "format:no_whitespace": _checks_format.check_no_whitespace,
}
