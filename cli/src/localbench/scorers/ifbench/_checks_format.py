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


def check_parentheses(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    levels: list[str] = []
    max_depth = 0
    for char in response:
        if char in "([{":
            levels.append(char)
            max_depth = max(max_depth, len(levels))
        elif char in ")]}":
            if levels and ((levels[-1] == "(" and char == ")") or (levels[-1] == "[" and char == "]") or (levels[-1] == "{" and char == "}")):
                levels.pop()
                if max_depth >= 5 and len(levels) < max_depth:
                    return True
            else:
                levels = []
                max_depth = 0
    return False


def check_quotes(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    levels: list[str] = []
    reached_depth = 0
    current_depth = 0
    for char in response:
        if levels and char == levels[-1]:
            levels.pop()
            current_depth -= 1
            if reached_depth - current_depth >= 3:
                return True
        elif char in {"'", '"'}:
            levels.append(char)
            current_depth += 1
            reached_depth = max(reached_depth, current_depth)
    return False


def check_options(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    options_text = _str(kwargs.get("options"))
    strict = re.match(r"\W*[aA]\W*[bB]\W*[cC]\W*", options_text) is not None
    if "/" in options_text:
        separator = "/"
    elif "or" in options_text:
        separator = "or"
    else:
        separator = ","
    options = [option.strip() for option in options_text.split(separator)]
    if strict:
        return response in options
    value = response.strip(string.punctuation + " ").lower()
    return any(option.strip(string.punctuation + " ").lower() == value for option in options)


def check_newline(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    value = _util.remove_punctuation(response)
    lines = [line for line in value.strip().split("\n") if line]
    return len(lines) == len(value.strip().split())


def check_emoji(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    for index, sentence in enumerate(sentences):
        stripped = sentence.translate(str.maketrans("", "", string.punctuation)).strip()
        if not stripped:
            return False
        last_char = stripped[-1]
        second_last_char = stripped[-2] if len(stripped) > 1 else stripped[-1]
        if _util.is_emoji(last_char) or _util.is_emoji(second_last_char):
            continue
        if index >= len(sentences) - 1:
            return False
        next_sentence = sentences[index + 1].translate(str.maketrans("", "", string.punctuation)).strip()
        if not next_sentence or not _util.is_emoji(next_sentence[0]):
            return False
    return True


def check_line_indent(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    lines = [line for line in response.split("\n") if line.strip()]
    for index in range(len(lines) - 1):
        if _indent(lines[index + 1]) <= _indent(lines[index]):
            return False
    return True


def check_quote_unquote(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    value = response.replace("'\"'", "")
    value = "".join(value.split())
    if '""' in value:
        return False
    stripped = value.strip(string.digits + string.punctuation.replace('"', ""))
    return not stripped or stripped[-1] != '"'


def check_list(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    marker = _str(kwargs.get("sep"))
    return len(re.findall(re.escape(marker), response)) >= 2


def check_thesis(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    start = response.find("<i>")
    close = "</i>"
    if start == -1:
        start = response.find("<em>")
        close = "</em>"
    if start == -1:
        return False
    value = response[start:]
    end = value.find(close)
    if end == -1:
        return False
    thesis = value[3:end]
    text = value[end + len(close) :]
    return bool(thesis.strip() and text.strip())


def check_sub_bullets(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    bullets = response.split("*")
    return all("-" in bullet for bullet in bullets[1:])


def check_no_bullets_bullets(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    lines = response.split("\n")
    before_bullets = True
    sentence_count = 0
    bullet_count = 0
    for line in lines:
        if line.strip().startswith("*"):
            before_bullets = False
            if sentence_count < 2:
                return False
            bullet_count += 1
        elif before_bullets:
            sentence_count += len(_util.sentence_split(line.strip()))
        else:
            return False
    return bullet_count >= 2


def check_title_case(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    for word in _util.punctuation_tokens(response):
        if not word or not word[0].isalpha():
            continue
        if len(word) == 1:
            if word[0].islower():
                return False
            continue
        if word[0].isupper() and word[1:].islower():
            continue
        if word[0].islower() and word[1:].isupper():
            return False
        if word[0].islower() and word[1:].islower():
            return False
    return True


def check_output_template(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    return "My Answer:" in response and "My Conclusion:" in response and "Future Outlook:" in response


def check_no_whitespace(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    return not any(char.isspace() for char in response)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string value")
