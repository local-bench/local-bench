from __future__ import annotations

import hashlib

from localbench.coding_exec.artifacts import (
    ASSEMBLY_RECIPE_ID,
    HARNESS_REV,
    code_artifact_for_generation,
)
from localbench.coding_exec.extract import EXTRACTOR_REV
from localbench.coding_exec.program import assemble_program


def test_code_artifact_for_generation_records_unverified_provenance() -> None:
    source_item = {
        "id": "bcbh-001",
        "instruct_prompt": "Write task_func.",
        "entry_point": "task_func",
        "test": "assert task_func(1) == 2",
    }
    benchmark_item = {
        "id": "bcbh-001",
        "messages": [{"role": "user", "content": "Write task_func."}],
        "sampling_params": {"temperature": 0},
        "max_tokens": 16384,
    }
    raw = "```python\ndef task_func(x):\n    return x + 1\n```"
    result = {"id": "bcbh-001", "response_text": raw, "error": None}

    artifact = code_artifact_for_generation(source_item, benchmark_item, result)

    sanitized = "def task_func(x):\n    return x + 1"
    program = assemble_program(sanitized, source_item["test"], source_item["entry_point"])
    assert artifact == {
        "raw_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "extracted_code": sanitized,
        "sanitized_code": sanitized,
        "assembly_recipe_id": ASSEMBLY_RECIPE_ID,
        "assembled_program_sha256": hashlib.sha256(program.encode("utf-8")).hexdigest(),
        "item_record_sha": artifact["item_record_sha"],
        "prompt_content_sha": hashlib.sha256(b"Write task_func.").hexdigest(),
        "test_sha": hashlib.sha256(source_item["test"].encode("utf-8")).hexdigest(),
        "extractor_rev": EXTRACTOR_REV,
        "harness_rev": HARNESS_REV,
        "image_digest": None,
        "verdict": None,
        "verdict_source": None,
    }
    assert len(artifact["item_record_sha"]) == 64


def test_code_artifact_records_ambiguous_extraction_without_zero_scoring() -> None:
    source_item = {
        "id": "bcbh-001",
        "instruct_prompt": "Write task_func.",
        "entry_point": "task_func",
        "test": "assert task_func(1) == 2",
    }
    benchmark_item = {
        "id": "bcbh-001",
        "messages": [{"role": "user", "content": "Write task_func."}],
        "sampling_params": {"temperature": 0},
        "max_tokens": 16384,
    }
    result = {"id": "bcbh-001", "response_text": "I cannot solve it.", "error": None}

    artifact = code_artifact_for_generation(source_item, benchmark_item, result)

    assert artifact["extracted_code"] is None
    assert artifact["sanitized_code"] is None
    assert artifact["assembled_program_sha256"] is None
    assert artifact["extraction_status"] == {
        "status": "ambiguous",
        "failure": "no_extractable_code",
    }
    assert artifact["verdict"] is None
    assert artifact["verdict_source"] is None
