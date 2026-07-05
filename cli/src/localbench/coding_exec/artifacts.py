from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, NotRequired, TypedDict, cast

from localbench._types import JsonObject, JsonValue
from localbench.coding_exec import runner as runner_module
from localbench.coding_exec.extract import EXTRACTOR_REV, extract_code_result
from localbench.coding_exec.program import assemble_program

ASSEMBLY_RECIPE_ID: Final = "bigcodebench-python-unittest-v1"
HARNESS_REV: Final = hashlib.sha256(Path(runner_module.__file__).resolve().read_bytes()).hexdigest()


class CodeVerdict(TypedDict):
    passed: bool
    timeout: bool
    oom: bool
    runtime_ms: int | None
    stdout_tail: str
    stderr_tail: str


class CodeArtifact(TypedDict):
    raw_text_sha256: str | None
    extracted_code: str | None
    sanitized_code: str | None
    assembly_recipe_id: str
    assembled_program_sha256: str | None
    item_record_sha: str
    prompt_content_sha: str
    test_sha: str
    extractor_rev: str
    harness_rev: str
    image_digest: str | None
    verdict: CodeVerdict | None
    verdict_source: str | None
    extraction_status: NotRequired[JsonObject]
    verdict_sig: NotRequired[str]


def code_artifact_for_generation(
    source_item: Mapping[str, JsonValue],
    benchmark_item: Mapping[str, JsonValue],
    result: Mapping[str, JsonValue],
) -> CodeArtifact:
    raw_text = _string(result.get("response_text"))
    extraction = extract_code_result(raw_text)
    sanitized_code = extraction.extracted_code.rstrip() if extraction.extracted_code is not None else None
    test = _string(source_item.get("test")) or ""
    entry_point = _string(source_item.get("entry_point")) or "task_func"
    assembled_sha = None
    if sanitized_code is not None:
        assembled = assemble_program(sanitized_code, test, entry_point)
        assembled_sha = _sha256_text(assembled)
    artifact: CodeArtifact = {
        "raw_text_sha256": _sha256_text(raw_text) if raw_text is not None else None,
        "extracted_code": extraction.extracted_code,
        "sanitized_code": sanitized_code,
        "assembly_recipe_id": ASSEMBLY_RECIPE_ID,
        "assembled_program_sha256": assembled_sha,
        "item_record_sha": canonical_item_sha(source_item),
        "prompt_content_sha": _sha256_text(_prompt_content(benchmark_item)),
        "test_sha": _sha256_text(test),
        "extractor_rev": EXTRACTOR_REV,
        "harness_rev": HARNESS_REV,
        "image_digest": None,
        "verdict": None,
        "verdict_source": None,
    }
    if extraction.status != "ok":
        artifact["extraction_status"] = {
            "status": extraction.status,
            "failure": extraction.failure,
        }
    return artifact


def canonical_item_sha(source_item: Mapping[str, JsonValue]) -> str:
    blob = json.dumps(source_item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(blob)


def verified_artifact(
    artifact: Mapping[str, JsonValue],
    *,
    verdict: CodeVerdict,
    image_digest: str | None,
) -> CodeArtifact:
    updated = dict(artifact)
    updated["verdict"] = dict(verdict)
    updated["verdict_source"] = "verifier"
    updated["image_digest"] = image_digest
    return cast(CodeArtifact, updated)


def verdict_from_runner_result(result: Mapping[str, JsonValue]) -> CodeVerdict:
    return {
        "passed": bool(result.get("passed")),
        "timeout": bool(result.get("timed_out") or result.get("timeout")),
        "oom": bool(result.get("oom")),
        "runtime_ms": _optional_int(result.get("runtime_ms")),
        "stdout_tail": _string(result.get("stdout_tail")) or "",
        "stderr_tail": _string(result.get("stderr_tail")) or "",
    }


def _prompt_content(benchmark_item: Mapping[str, JsonValue]) -> str:
    messages = benchmark_item.get("messages")
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            parts.append(message["content"])
    return "\n\n".join(parts)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
