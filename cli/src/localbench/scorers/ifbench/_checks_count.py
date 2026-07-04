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

import re
import string

from localbench.scorers.ifbench import _util
from localbench.scorers.ifbench._types import InstructionKwargs


def check_word_count_range(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    min_words = _int(kwargs.get("min_words"))
    max_words = _int(kwargs.get("max_words"))
    return min_words <= _util.count_words(response) <= max_words


def check_unique_word_count(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = _int(kwargs.get("N"))
    words = {word.strip(string.punctuation + " ") for word in response.lower().split()}
    return len(words) >= expected


def check_conjunctions(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = _int(kwargs.get("small_n"))
    conjunctions = {
        _util.strip_word(word).lower()
        for word in response.split()
        if _util.strip_word(word).lower() in {"and", "but", "for", "nor", "or", "so", "yet"}
    }
    return len(conjunctions) >= expected


def check_person_names(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = _int(kwargs.get("N"))
    names = {
        name
        for name in _util.PERSON_NAMES
        if re.search(rf"\b{re.escape(name)}\b", response)
    }
    return len(names) >= expected


def check_numbers(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = _int(kwargs.get("N"))
    text = response.translate(str.maketrans("", "", string.punctuation))
    return len(re.findall(r"\d+", text)) == expected


def check_pronouns(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = _int(kwargs.get("N"))
    words = _util.word_tokens(response.replace("/", " ").lower())
    return sum(1 for word in words if word in _util.PRONOUNS) >= expected


def check_keywords_multiple(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    expected = [1, 2, 3, 5, 7]
    keywords = [_str(kwargs.get(f"keyword{index}")).strip() for index in range(1, 6)]
    text = response.lower()
    return all(text.count(keyword.lower()) == count for keyword, count in zip(keywords, expected, strict=True))


def check_words_japanese(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    nth = _int(kwargs.get("N"))
    if nth <= 0:
        return False
    for index, word in enumerate(response.split(), start=1):
        stripped = _util.strip_word(word)
        if index % nth == 0 and stripped and not stripped.isdigit() and not _util.is_japanese(stripped):
            return False
    return True


def check_punctuation(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    punctuation = {".", ",", "!", "?", ";", ":"}
    if "!?" not in response and "?!" not in response and "‽" not in response:
        return False
    reduced = response.replace("?!", "", 1)
    if len(reduced) == len(response):
        reduced = response.replace("!?", "", 1)
    for char in reduced:
        punctuation.discard(char)
    return not punctuation


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError("expected integer-compatible value")


def _str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string value")
