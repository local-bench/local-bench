# /// script
# dependencies = ["datasets>=2.20"]
# ///

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

try:
    from datasets import Dataset, load_dataset
    from huggingface_hub import HfApi
except ModuleNotFoundError as error:
    message = (
        "Missing build dependency. Run "
        "`cli/.venv/Scripts/python -m pip install -e cli[build]` from the repo root."
    )
    raise SystemExit(message) from error

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_DIR: Final = ROOT / "suite" / "v1"

AMO_REPO: Final = "meituan-longcat/AMO-Bench"
AMO_REVISION: Final = "2f422616c25d862984408fbbfaed63a961e8e025"
AMO_LICENSE: Final = "mit"
AMO_INCLUDED_ANSWER_TYPES: Final = frozenset({"number", "set", "variable"})
AMO_DROPPED_ANSWER_TYPES: Final = frozenset({"description"})
AMO_EXPECTED_TOTAL: Final = 50
AMO_EXPECTED_INCLUDED: Final = 39

OLYMMATH_REPO: Final = "RUC-AIBOX/OlymMATH"
OLYMMATH_CONFIG: Final = "en-hard"
OLYMMATH_REVISION: Final = "2c6532ea2cf929ac1c421532af5951553eaee727"
OLYMMATH_LICENSE: Final = "mit"
OLYMMATH_EXPECTED_TOTAL: Final = 100

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class BuildError(RuntimeError):
    pass


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _require_license(AMO_REPO, AMO_REVISION, AMO_LICENSE)
    _require_license(OLYMMATH_REPO, OLYMMATH_REVISION, OLYMMATH_LICENSE)

    amo_rows = _load_rows(AMO_REPO, None, "test", AMO_REVISION)
    olympmath_rows = _load_rows(OLYMMATH_REPO, OLYMMATH_CONFIG, "test", OLYMMATH_REVISION)

    _write_jsonl(OUT_DIR / "amo.jsonl", _build_amo_items(amo_rows))
    _write_jsonl(OUT_DIR / "olymmath_hard.jsonl", _build_olymmath_items(olympmath_rows))
    return 0


def _require_license(repo_id: str, revision: str, expected_license: str) -> None:
    info = HfApi().dataset_info(repo_id, revision=revision)
    card_data = info.cardData
    license_value = getattr(card_data, "license", None)
    if license_value != expected_license:
        raise BuildError(
            f"{repo_id}@{revision} license is {license_value!r}, expected {expected_license!r}."
        )


def _load_rows(repo_id: str, config: str | None, split: str, revision: str) -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(repo_id, config, split=split, revision=revision)
    if not isinstance(dataset, Dataset):
        raise BuildError(f"Expected Dataset for {repo_id}/{config or 'default'}/{split}.")
    return [dict(row) for row in dataset]


def _build_amo_items(rows: list[Mapping[str, JsonValue]]) -> list[JsonObject]:
    if len(rows) != AMO_EXPECTED_TOTAL:
        raise BuildError(f"Expected {AMO_EXPECTED_TOTAL} AMO rows, found {len(rows)}.")

    items: list[JsonObject] = []
    dropped = 0
    for row in rows:
        answer_type = _required_str(row, "answer_type")
        if answer_type in AMO_DROPPED_ANSWER_TYPES:
            dropped += 1
            continue
        if answer_type not in AMO_INCLUDED_ANSWER_TYPES:
            raise BuildError(f"Unexpected AMO answer_type {answer_type!r}.")

        item_number = len(items) + 1
        items.append(
            {
                "id": f"amo-{item_number:03d}",
                "statement": _amo_statement(_required_str(row, "prompt")),
                "answer": _normalize_answer(_required_str(row, "answer"), answer_type=answer_type),
            }
        )

    if len(items) != AMO_EXPECTED_INCLUDED:
        raise BuildError(f"Expected {AMO_EXPECTED_INCLUDED} AMO items, built {len(items)}.")
    if dropped != AMO_EXPECTED_TOTAL - AMO_EXPECTED_INCLUDED:
        raise BuildError(f"Expected {AMO_EXPECTED_TOTAL - AMO_EXPECTED_INCLUDED} AMO drops, got {dropped}.")
    return items


def _build_olymmath_items(rows: list[Mapping[str, JsonValue]]) -> list[JsonObject]:
    if len(rows) != OLYMMATH_EXPECTED_TOTAL:
        raise BuildError(f"Expected {OLYMMATH_EXPECTED_TOTAL} OlymMATH rows, found {len(rows)}.")
    return [
        {
            "id": f"olymmath-hard-{index:03d}",
            "statement": _required_str(row, "problem").strip(),
            "answer": _normalize_answer(_required_str(row, "answer"), answer_type=None),
        }
        for index, row in enumerate(rows, start=1)
    ]


def _amo_statement(prompt: str) -> str:
    marker = "\nAfter solving the above problem"
    if marker not in prompt:
        raise BuildError("AMO prompt is missing the expected answer-format marker.")
    return prompt.split(marker, 1)[0].strip()


def _normalize_answer(answer: str, *, answer_type: str | None) -> str:
    token = _strip_math_wrappers(answer)
    boxed = _last_boxed_content(token)
    if boxed is not None:
        token = _strip_math_wrappers(boxed)

    token = token.replace(r"\left", "")
    token = token.replace(r"\right", "")
    token = token.replace(r"\,", "")
    token = token.replace(r"\!", "")
    token = token.replace(r"\cdot", "*")
    token = token.replace(r"\times", "*")
    token = token.replace(r"\pi", "pi")
    token = token.replace(r"\infty", "oo")
    token = token.replace("+oo", "oo")
    token = token.replace(r"\{", "{")
    token = token.replace(r"\}", "}")
    token = token.replace(r"^{\circ}", "")
    token = token.replace(r"^\circ", "")

    previous = ""
    while token != previous:
        previous = token
        token = _replace_latex_fractions(token)
        token = _replace_latex_roots(token)
        token = _replace_grouped_exponents(token)

    if answer_type != "set":
        token = token.replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", token).strip()


def _strip_math_wrappers(value: str) -> str:
    token = value.strip()
    changed = True
    while changed:
        changed = False
        if token.startswith("$$") and token.endswith("$$"):
            token = token[2:-2].strip()
            changed = True
        if token.startswith("$") and token.endswith("$"):
            token = token[1:-1].strip()
            changed = True
    return token


def _last_boxed_content(text: str) -> str | None:
    contents: list[str] = []
    position = 0
    while True:
        start = text.find(r"\boxed", position)
        if start == -1:
            return contents[-1] if contents else None
        brace_index = _next_nonspace_index(text, start + len(r"\boxed"))
        if brace_index is not None and brace_index < len(text) and text[brace_index] == "{":
            content = _balanced_content(text, brace_index, "{", "}")
            if content is not None:
                contents.append(content[0])
                position = content[1]
                continue
        position = start + len(r"\boxed")


def _replace_latex_fractions(text: str) -> str:
    token = text.replace(r"\dfrac", r"\frac")
    while True:
        start = token.find(r"\frac")
        if start == -1:
            return token
        numerator_start = _next_nonspace_index(token, start + len(r"\frac"))
        if numerator_start is None or token[numerator_start] != "{":
            return token
        numerator = _balanced_content(token, numerator_start, "{", "}")
        if numerator is None:
            return token
        denominator_start = _next_nonspace_index(token, numerator[1])
        if denominator_start is None or token[denominator_start] != "{":
            return token
        denominator = _balanced_content(token, denominator_start, "{", "}")
        if denominator is None:
            return token
        replacement = f"({numerator[0]})/({denominator[0]})"
        token = token[:start] + replacement + token[denominator[1] :]


def _replace_latex_roots(text: str) -> str:
    token = text
    while True:
        start = token.find(r"\sqrt")
        if start == -1:
            return token
        position = start + len(r"\sqrt")
        degree: str | None = None
        if position < len(token) and token[position] == "[":
            degree_end = token.find("]", position + 1)
            if degree_end == -1:
                return token
            degree = token[position + 1 : degree_end].strip()
            position = degree_end + 1
        radicand_start = _next_nonspace_index(token, position)
        if radicand_start is None or token[radicand_start] != "{":
            return token
        radicand = _balanced_content(token, radicand_start, "{", "}")
        if radicand is None:
            return token
        replacement = f"sqrt({radicand[0]})" if degree is None else f"({radicand[0]})^(1/{degree})"
        token = token[:start] + replacement + token[radicand[1] :]


def _replace_grouped_exponents(text: str) -> str:
    token = text
    while True:
        start = token.find("^{")
        if start == -1:
            return token
        exponent = _balanced_content(token, start + 1, "{", "}")
        if exponent is None:
            return token
        token = token[:start] + f"^({exponent[0]})" + token[exponent[1] :]


def _balanced_content(text: str, opening_index: int, left: str, right: str) -> tuple[str, int] | None:
    depth = 0
    escaped = False
    content_start = opening_index + 1
    for index, character in enumerate(text[opening_index:], start=opening_index):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == left:
            depth += 1
        elif character == right:
            depth -= 1
            if depth == 0:
                return text[content_start:index], index + 1
    return None


def _next_nonspace_index(text: str, start: int) -> int | None:
    for index in range(start, len(text)):
        if not text[index].isspace():
            return index
    return None


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise BuildError(f"{key} must be a string.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
