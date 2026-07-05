from __future__ import annotations

import pytest

from localbench.coding_exec.extract import ExtractionFailure, extract_code_result


@pytest.mark.parametrize(
    ("name", "response", "expected"),
    [
        (
            "raw_code",
            "def task_func(x):\n    return x + 1\n",
            "def task_func(x):\n    return x + 1",
        ),
        (
            "fenced",
            "```python\ndef task_func(x):\n    return x + 1\n```",
            "def task_func(x):\n    return x + 1",
        ),
        (
            "multiple_fences",
            "```python\ndef wrong():\n    pass\n```\n```python\ndef task_func(x):\n    return x\n```",
            "def task_func(x):\n    return x",
        ),
        (
            "prose_before",
            "Here is the implementation:\n```python\ndef task_func(x):\n    return x\n```",
            "def task_func(x):\n    return x",
        ),
        (
            "prose_after",
            "```python\ndef task_func(x):\n    return x\n```\nThis should pass.",
            "def task_func(x):\n    return x",
        ),
        (
            "backticks_inside_string_literal",
            "```python\ndef task_func():\n    return '``` not a fence'\n```",
            "def task_func():\n    return '``` not a fence'",
        ),
    ],
)
def test_code_extraction_golden_successes(name: str, response: str, expected: str) -> None:
    result = extract_code_result(response)

    assert result.status == "ok", name
    assert result.extracted_code == expected
    assert result.failure is None


@pytest.mark.parametrize(
    ("name", "response", "failure"),
    [
        ("no_fence", "I would solve this by using a dictionary.", "no_extractable_code"),
        ("malformed_fence", "```python def task_func(x):\n    return x\n```", "malformed_fence"),
        ("thinking_tags_left_over", "<think>reasoning</think>\n```python\ndef task_func():\n    return 1\n```", "thinking_tags_present"),
        ("truncated_mid_fence", "```python\ndef task_func(x):\n    return x", "truncated_fence"),
    ],
)
def test_code_extraction_golden_ambiguous_failures(
    name: str,
    response: str,
    failure: ExtractionFailure,
) -> None:
    result = extract_code_result(response)

    assert result.status == "ambiguous", name
    assert result.extracted_code is None
    assert result.failure == failure
