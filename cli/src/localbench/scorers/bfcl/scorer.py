from __future__ import annotations

import json
from collections.abc import Mapping

from localbench.scorers.bfcl._checker import check_bfcl_call
from localbench.scorers.bfcl._parser import decode_bfcl_response
from localbench.scorers.bfcl._types import BFCLScore, JsonObject, JsonValue


def score_bfcl(prompt_item: Mapping[str, JsonValue], response_text: str) -> BFCLScore:
    try:
        function_docs = _object_list(prompt_item.get("function"))
        possible_answer = _object_list(prompt_item.get("possible_answer"))
        category = prompt_item.get("category")
        response = response_text if isinstance(response_text, str) else ""
        if not function_docs or not possible_answer or not isinstance(category, str):
            return {"correct": False, "extracted": None}
        decoded = decode_bfcl_response(response)
        if decoded is None:
            return {"correct": False, "extracted": None}
        check = check_bfcl_call(function_docs, decoded, possible_answer, category)
        return {"correct": bool(check["valid"]), "extracted": _extracted(decoded)}
    except Exception:
        return {"correct": False, "extracted": None}


def _object_list(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extracted(decoded: list[JsonObject]) -> str:
    return json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
