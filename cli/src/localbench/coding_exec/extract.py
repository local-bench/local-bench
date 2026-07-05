from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

EXTRACTOR_REV: Final = "bigcodebench-extractor-v2"

ExtractionFailure: TypeAlias = Literal[
    "empty_response",
    "thinking_tags_present",
    "malformed_fence",
    "truncated_fence",
    "empty_code_block",
    "no_extractable_code",
]
ExtractionStatus: TypeAlias = Literal["ok", "ambiguous"]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    status: ExtractionStatus
    extracted_code: str | None
    failure: ExtractionFailure | None = None


@dataclass(frozen=True, slots=True)
class _FenceBlock:
    lang: str
    body: str


def extract_code_result(response: str | None) -> ExtractionResult:
    if response is None or not response.strip():
        return _ambiguous("empty_response")
    if "<think" in response.casefold() or "</think" in response.casefold():
        return _ambiguous("thinking_tags_present")
    fence_status = _fenced_blocks(response)
    if isinstance(fence_status, str):
        return _ambiguous(fence_status)
    if fence_status:
        python_blocks = [block for block in fence_status if block.lang in {"python", "py", "python3"}]
        chosen = python_blocks[-1] if python_blocks else fence_status[-1]
        code = chosen.body.strip("\n")
        if not code.strip():
            return _ambiguous("empty_code_block")
        return ExtractionResult(status="ok", extracted_code=code)
    raw = response.strip()
    if _is_parseable_python(raw):
        return ExtractionResult(status="ok", extracted_code=raw)
    return _ambiguous("no_extractable_code")


def extract_code(response: str | None) -> str | None:
    result = extract_code_result(response)
    return result.extracted_code if result.status == "ok" else None


def _fenced_blocks(response: str) -> list[_FenceBlock] | ExtractionFailure:
    blocks: list[_FenceBlock] = []
    lines = response.splitlines()
    in_fence = False
    lang = ""
    body: list[str] = []
    saw_malformed = False
    for line in lines:
        stripped = line.strip()
        if not in_fence:
            if stripped.startswith("```"):
                suffix = stripped[3:].strip()
                if suffix and any(char.isspace() for char in suffix):
                    saw_malformed = True
                    continue
                in_fence = True
                lang = suffix.casefold()
                body = []
            continue
        if stripped == "```":
            blocks.append(_FenceBlock(lang=lang, body="\n".join(body)))
            in_fence = False
            lang = ""
            body = []
            continue
        body.append(line)
    if saw_malformed:
        return "malformed_fence"
    if in_fence:
        return "truncated_fence"
    return blocks


def _is_parseable_python(value: str) -> bool:
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return True


def _ambiguous(failure: ExtractionFailure) -> ExtractionResult:
    return ExtractionResult(status="ambiguous", extracted_code=None, failure=failure)
