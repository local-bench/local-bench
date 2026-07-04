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
import unicodedata
from typing import Final

WORD_RE: Final = re.compile(r"\b\w+\b", re.UNICODE)
TOKEN_RE: Final = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SENTENCE_RE: Final = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$", re.UNICODE)
JAPANESE_RE: Final = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
VOWEL_RE: Final = re.compile(r"[aeiouy]+", re.IGNORECASE)

STOP_WORDS: Final = frozenset("a about above after again against all am an and any are as at be because been before being below between both but by can did do does doing down during each few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with you your yours yourself yourselves".split())
PERSON_NAMES: Final = frozenset("Emma Liam Sophia Jackson Olivia Noah Ava Lucas Isabella Mason Mia Ethan Charlotte Alexander Amelia Benjamin Harper Leo Zoe Daniel Chloe Samuel Lily Matthew Grace Owen Abigail Gabriel Ella Jacob Scarlett Nathan Victoria Elijah Layla Nicholas Audrey David Hannah Christopher Penelope Thomas Nora Andrew Aria Joseph Claire Ryan Stella Jonathan".split())
PRONOUNS: Final = frozenset("i me we us you he him she her it they them my mine our ours your yours his hers its their theirs myself ourselves yourself yourselves himself herself itself themselves this that these those who whom whose which what whoever whomever whatever whichever anybody anyone anything everybody everyone everything nobody nothing somebody someone something each either neither both all some any none".split())
COMMON_VERBS: Final = frozenset("answer ask build compare create describe do does explain give go include list make name provide respond run say tell use write".split())
SYLLABLE_OVERRIDES: Final = {"children": 2, "little": 2, "regret": 2, "enjoy": 2, "sunshine": 2}


def sentence_split(text: str) -> list[str]:
    return [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]


def word_tokens(text: str) -> list[str]:
    return WORD_RE.findall(text)


def word_tokens_without_punctuation(text: str) -> list[str]:
    return [token for token in word_tokens(text) if any(char.isalnum() for char in token)]


def punctuation_tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def count_words(text: str) -> int:
    return len(word_tokens(text))


def count_stopwords(text: str) -> int:
    return sum(1 for token in word_tokens(text) if token.lower() in STOP_WORDS)


def strip_word(text: str) -> str:
    return text.strip(string.punctuation + " ")


def remove_punctuation(text: str) -> str:
    return text.translate(str.maketrans("", "", string.punctuation))


def normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")


def char_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    if len(text) < n:
        return set()
    return {tuple(text[index : index + n]) for index in range(len(text) - n + 1)}


def is_japanese(text: str) -> bool:
    return bool(JAPANESE_RE.search(text))


def is_emoji(char: str) -> bool:
    if not char:
        return False
    codepoint = ord(char[0])
    return (
        0x1F300 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2300 <= codepoint <= 0x23FF
    )


def count_syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 0
    if cleaned in SYLLABLE_OVERRIDES:
        return SYLLABLE_OVERRIDES[cleaned]
    groups = VOWEL_RE.findall(cleaned)
    count = len(groups)
    if cleaned.endswith("e") and count > 1 and not cleaned.endswith(("le", "ye")):
        count -= 1
    return max(count, 1)
