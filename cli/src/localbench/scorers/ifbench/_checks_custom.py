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

import csv
import io
import re
import string
from typing import Final

from localbench.scorers.ifbench import _util
from localbench.scorers.ifbench._types import InstructionKwargs

EUROPE_CAPITALS: Final = [
    "Reykjavik",
    "Helsinki",
    "Oslo",
    "Tallinn",
    "Stockholm",
    "Riga",
    "Moscow",
    "Copenhagen",
    "Vilnius",
    "Minsk",
    "Dublin",
    "Berlin",
    "Amsterdam",
    "Warsaw",
    "London",
    "Brussels",
    "Prague",
    "Luxembourg",
    "Paris",
    "Vienna",
    "Bratislava",
    "Budapest",
    "Vaduz",
    "Chisinau",
    "Bern",
    "Ljubljana",
    "Zagreb",
]


def check_multiples(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    numbers = re.findall(r"\d+", response.replace(",", ", "))
    return numbers == [str(number) for number in range(14, 51, 7)]


def check_mcq_count_length(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    if response[response.find("Question") :] != response:
        return False
    questions = re.split(r"\n*(?:Question \d+[\.\):;]?\s*)", response)
    if questions and questions[0] == "":
        questions = questions[1:]
    questions = [question.strip() for question in questions if question.strip()]
    if len(questions) != 4:
        return False
    lengths: list[int] = []
    for question in questions:
        text, option_count = _question_text_and_option_count(question)
        if option_count != 5:
            return False
        lengths.append(len(text.strip()))
    return all(lengths[index] < lengths[index + 1] for index in range(len(lengths) - 1))


def check_reverse_newline(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    lines = [line.strip(string.punctuation + " ") for line in response.split("\n") if line.strip(string.punctuation + " ")]
    start = _zimbabwe_index(lines)
    if start is None:
        return False
    target_lines = lines[start:]
    if len(target_lines) < 52:
        return False
    normalized = [_util.normalize_ascii(line) for line in target_lines]
    return normalized == sorted(normalized, reverse=True)


def check_word_reverse(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    value = _util.remove_punctuation(response.lower().strip())
    reversed_words = " ".join(value.split()[::-1])
    return "bald eagle" in reversed_words and reversed_words in _util.sentence_split(reversed_words)


def check_character_reverse(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    return "elgae dlab" in response.lower()


def check_european_capitals_sort(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    value = _util.normalize_ascii(response)
    capitals = [capital for capital in value.split(",") if capital.strip()]
    if len(capitals) != len(EUROPE_CAPITALS):
        return False
    return all(capital.strip() == expected for capital, expected in zip(capitals, EUROPE_CAPITALS, strict=True))


def check_csv_city(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    rows = list(csv.reader(io.StringIO(response)))
    if len(rows) != 8:
        return False
    if rows[0] != ["ID", "Country", "City", "Year", "Count"]:
        return False
    return all(len(row) == 5 for row in rows[1:])


def check_csv_special_character(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    header = response.split("\n")[0].strip()
    if re.match(r'^(ProductID|"ProductID"),[ \t]*(Category|"Category"),[ \t]*(Brand|"Brand"),[ \t]*(Price|"Price"),[ \t]*(Stock|"Stock")$', header) is None:
        return False
    rows = list(csv.reader(io.StringIO(response)))
    if len(rows) != 15:
        return False
    if any(len(row) != 5 for row in rows[1:]):
        return False
    return any(re.search(r'"[^"\n]*[^\d\w\s][^"\n]*"', line) for line in response.splitlines()[1:])


def check_csv_quotes(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    lines = response.splitlines()
    if len(lines) != 4:
        return False
    for line in lines:
        fields = [field.strip() for field in line.split("\t")]
        if len(fields) != 5:
            return False
        if not all(field.startswith('"') and field.endswith('"') for field in fields):
            return False
    return True


def check_date_format_list(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    for raw_date in response.strip().split(","):
        date = raw_date.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date) is None:
            return False
        year_raw, month_raw, day_raw = date.split("-")
        year = int(year_raw)
        month = int(month_raw)
        day = int(day_raw)
        if year < 1769 or year > 1821 or month > 12:
            return False
        if month in {1, 3, 5, 7, 8, 10, 12} and day > 31:
            return False
        if month in {4, 6, 9, 11} and day > 30:
            return False
        if month == 2 and day > 29:
            return False
    return True


def _question_text_and_option_count(question: str) -> tuple[str, int]:
    lines = question.split("\n")
    text = ""
    option_count = 0
    done_with_question = False
    for line in lines:
        if re.match(r"^[A-Ea-e][\.\)]\s*\w+", line.strip()):
            option_count += 1
            done_with_question = True
        elif not done_with_question:
            text += " " + line.strip()
    return text, option_count


def _zimbabwe_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if "Zimbabwe" in line:
            return index
    return None
