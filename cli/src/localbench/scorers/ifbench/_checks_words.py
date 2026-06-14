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

import string

from localbench.scorers.ifbench import _util
from localbench.scorers.ifbench._types import InstructionKwargs


def check_alphabet(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    words = _util.remove_punctuation(response).strip(string.punctuation + " ").split()
    if not words:
        return False
    alphabet = string.ascii_lowercase
    expected = words[0][0].lower()
    if expected not in alphabet:
        return False
    for word in words[1:]:
        cleaned = word.strip(string.punctuation + " ").lower()
        if not cleaned:
            continue
        expected = alphabet[(alphabet.index(expected) + 1) % 26]
        if cleaned[0] != expected:
            return False
    return True


def check_vowel(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    paragraphs = response.strip().split("\n")
    if len(paragraphs) != 1:
        return False
    vowels = {char for char in paragraphs[0].lower() if char in "aeiou"}
    return len(vowels) <= 3


def check_consonants(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    consonants = set("bcdfghjklmnpqrstvwxyz")
    for word in response.lower().strip().split():
        cluster = any(word[index] in consonants and word[index + 1] in consonants for index in range(len(word) - 1))
        if not cluster:
            return False
    return True


def check_palindrome(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    words = _util.remove_punctuation(response).lower().split()
    palindromes = [word for word in words if word == word[::-1] and len(word) >= 5]
    return len(palindromes) >= 10


def check_prime_lengths(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97}
    return all(len(word) in primes for word in _util.remove_punctuation(response).split())


def check_repeats(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    maximum = _int(kwargs.get("small_n"))
    counts: dict[str, int] = {}
    for word in _util.remove_punctuation(response).lower().split():
        counts[word] = counts.get(word, 0) + 1
        if counts[word] > maximum:
            return False
    return True


def check_odd_even_syllables(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    syllables = [
        _util.count_syllables(word) % 2
        for word in _util.remove_punctuation(response).lower().split()
        if word.strip()
    ]
    return all(syllables[index] != syllables[index + 1] for index in range(len(syllables) - 1))


def check_paragraph_last_first(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    for paragraph in response.split("\n"):
        cleaned = paragraph.strip().lower()
        if not cleaned:
            continue
        words = cleaned.strip(string.punctuation + " ").split()
        if words and words[0] != words[-1]:
            return False
    return True


def check_no_consecutive(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    words = _util.remove_punctuation(response).lower().split()
    return all(words[index][0] != words[index + 1][0] for index in range(len(words) - 1))


def check_keywords_specific_position(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    keyword = _str(kwargs.get("keyword"))
    nth_sentence = _int(kwargs.get("n"))
    nth_word = _int(kwargs.get("m"))
    sentences = _util.sentence_split(response)
    if len(sentences) < nth_sentence:
        return False
    words = _util.word_tokens_without_punctuation(sentences[nth_sentence - 1])
    return len(words) >= nth_word and words[nth_word - 1].lower() == keyword.lower()


def check_words_position(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    keyword = _str(kwargs.get("keyword")).lower()
    words = _util.punctuation_tokens(response)
    if len(words) < 2:
        return False
    if words[-1] in string.punctuation:
        return len(words) >= 3 and words[1].lower() == words[-3].lower() == keyword
    return words[1].lower() == words[-2].lower() == keyword


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
