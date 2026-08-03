from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

from localbench._types import JsonObject
from localbench.check.types import CheckError
from localbench.coding_exec.artifacts import (
    code_artifact_for_generation,
    verified_artifact,
    verdict_from_runner_result,
)
from localbench.coding_exec.ast_gate import check_ast_gate
from localbench.check.live_coding_sandbox import CodingVerifierError, execute_verifier_tasks
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.sandbox import OPT_IN_WARNING


class _ModuleItem(Protocol):
    @property
    def module(self) -> str: ...


def require_coding_consent(
    items: Iterable[_ModuleItem],
    *,
    allow_untrusted_code: bool,
) -> None:
    if not allow_untrusted_code and any(item.module == "coding" for item in items):
        raise CheckError(f"{OPT_IN_WARNING} Refusing to continue without --allow-untrusted-code.")


def verify_coding_rows(rows: list[JsonObject], *, allow_untrusted_code: bool) -> None:
    pending: dict[str, JsonObject] = {}
    tasks: list[JsonObject] = []
    for row in rows:
        if row.get("module") != "coding":
            continue
        item_id = _required_str(row, "item_id")
        source = _required_object(row, "source_item")
        generation = _required_object(row, "candidate")
        text = generation.get("text")
        result: JsonObject = {"response_text": text if isinstance(text, str) else ""}
        prompt = source.get("instruct_prompt")
        benchmark: JsonObject = {
            "messages": [
                {
                    "content": prompt if isinstance(prompt, str) else "",
                    "role": "user",
                }
            ]
        }
        artifact = cast(
            JsonObject,
            dict(code_artifact_for_generation(source, benchmark, result)),
        )
        generation["code_artifact"] = artifact
        code = artifact.get("sanitized_code")
        test = source.get("test")
        entry_point = source.get("entry_point")
        if (
            isinstance(code, str)
            and isinstance(test, str)
            and isinstance(entry_point, str)
            and check_ast_gate(code).accepted
        ):
            tasks.append(
                {
                    "id": item_id,
                    "program": assemble_program(code, test, entry_point),
                }
            )
            pending[item_id] = generation
    if not tasks:
        return
    try:
        results, image = execute_verifier_tasks(
            tasks,
            allow_untrusted_code=allow_untrusted_code,
        )
    except CodingVerifierError as error:
        raise CheckError(f"coding sandbox infrastructure failed: {error}") from error
    by_id = {
        _required_str(verdict_row, "id"): verdict_row
        for verdict_row in results
    }
    for item_id, generation in pending.items():
        verdict_row = by_id.get(item_id)
        artifact = generation.get("code_artifact")
        if verdict_row is None or not isinstance(artifact, dict):
            raise CheckError(f"coding sandbox returned no verdict for {item_id}")
        generation["code_artifact"] = cast(
            JsonObject,
            dict(
                verified_artifact(
                    cast(JsonObject, artifact),
                    verdict=verdict_from_runner_result(verdict_row),
                    image_digest=image,
                )
            ),
        )


def _required_object(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise CheckError(f"coding live row field {key!r} must be an object")
    return cast(JsonObject, value)


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"coding live row field {key!r} must be a non-empty string")
    return value
