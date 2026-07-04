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

"""Utility functions adapted from Google Research IFEval."""

from __future__ import annotations

import re
from typing import Final

_ALPHABETS: Final = r"([A-Za-z])"
_PREFIXES: Final = r"(Mr|St|Mrs|Ms|Dr)[.]"
_SUFFIXES: Final = r"(Inc|Ltd|Jr|Sr|Co)"
_STARTERS: Final = (
    r"(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|"
    r"Our\s|We\s|But\s|However\s|That\s|This\s|Wherever)"
)
_ACRONYMS: Final = r"([A-Z][.][A-Z][.](?:[A-Z][.])?)"
_WEBSITES: Final = r"[.](com|net|org|io|gov|edu|me)"
_DIGITS: Final = r"([0-9])"
_MULTIPLE_DOTS: Final = r"\.{2,}"
_WORD_RE: Final = re.compile(r"\w+")
_TOKEN_RE: Final = re.compile(r"\b\w+(?:-\w+)*\b|[^\w\s]", flags=re.UNICODE)


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using the official IFEval regex rules."""
    working = f" {text}  ".replace("\n", " ")
    working = re.sub(_PREFIXES, r"\1<prd>", working)
    working = re.sub(_WEBSITES, r"<prd>\1", working)
    working = re.sub(_DIGITS + r"[.]" + _DIGITS, r"\1<prd>\2", working)
    working = re.sub(
        _MULTIPLE_DOTS,
        lambda match: "<prd>" * len(match.group(0)) + "<stop>",
        working,
    )
    working = working.replace("Ph.D.", "Ph<prd>D<prd>")
    working = re.sub(r"\s" + _ALPHABETS + r"[.] ", r" \1<prd> ", working)
    working = re.sub(_ACRONYMS + " " + _STARTERS, r"\1<stop> \2", working)
    working = re.sub(
        _ALPHABETS + r"[.]" + _ALPHABETS + r"[.]" + _ALPHABETS + r"[.]",
        r"\1<prd>\2<prd>\3<prd>",
        working,
    )
    working = re.sub(
        _ALPHABETS + r"[.]" + _ALPHABETS + r"[.]",
        r"\1<prd>\2<prd>",
        working,
    )
    working = re.sub(" " + _SUFFIXES + r"[.] " + _STARTERS, r" \1<stop> \2", working)
    working = re.sub(" " + _SUFFIXES + r"[.]", r" \1<prd>", working)
    working = re.sub(" " + _ALPHABETS + r"[.]", r" \1<prd>", working)
    working = working.replace(".”", "”.").replace('."', '".')
    working = working.replace('!"', '"!').replace('?"', '"?')
    working = working.replace(".", ".<stop>")
    working = working.replace("?", "?<stop>")
    working = working.replace("!", "!<stop>")
    working = working.replace("<prd>", ".")
    sentences = [sentence.strip() for sentence in working.split("<stop>")]
    if sentences and not sentences[-1]:
        sentences = sentences[:-1]
    return sentences


def count_sentences(text: str) -> int:
    """Count sentences without the NLTK runtime dependency."""
    return len(split_into_sentences(text))


def count_words(text: str) -> int:
    """Count words with the official IFEval ``\\w+`` token rule."""
    return len(_WORD_RE.findall(text))


def word_tokenize(text: str) -> list[str]:
    """Tokenize enough like NLTK for IFEval capital-word checks."""
    return _TOKEN_RE.findall(text)
