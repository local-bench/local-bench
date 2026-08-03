from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast, override

import httpx

from localbench._types import JsonObject, JsonValue
from localbench._response import ResponseParseError


@dataclass(frozen=True, slots=True)
class StreamingStatusError(RuntimeError):
    status_code: int
    body: str

    @override
    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.body}"


async def post_streaming_completion(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    body: JsonObject,
    timeout: httpx.Timeout,
) -> JsonObject:
    text_parts: list[str] = []
    finish_reason: str | None = None
    usage: JsonObject | None = None
    timings: JsonObject | None = None
    async with client.stream("POST", url, headers=headers, json=body, timeout=timeout) as response:
        if response.status_code >= 400:
            content = (await response.aread()).decode("utf-8", errors="replace")
            raise StreamingStatusError(response.status_code, content)
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                raw_chunk = cast(object, json.loads(payload))
            except json.JSONDecodeError as error:
                raise ResponseParseError("streaming completion emitted invalid JSON") from error
            if not isinstance(raw_chunk, dict):
                raise ResponseParseError("streaming completion chunk is not an object")
            chunk = cast(JsonObject, raw_chunk)
            raw_choices = chunk.get("choices")
            if isinstance(raw_choices, list) and raw_choices:
                choice = raw_choices[0]
                if isinstance(choice, dict):
                    choice_object = cast(JsonObject, choice)
                    raw_text = choice_object.get("text")
                    if isinstance(raw_text, str):
                        text_parts.append(raw_text)
                    raw_finish = choice_object.get("finish_reason")
                    if isinstance(raw_finish, str):
                        finish_reason = raw_finish
            raw_usage = chunk.get("usage")
            if isinstance(raw_usage, dict):
                usage = dict(cast(JsonObject, raw_usage))
            raw_timings = chunk.get("timings")
            if isinstance(raw_timings, dict):
                timings = dict(cast(JsonObject, raw_timings))
    choice_values: list[JsonValue] = [{"finish_reason": finish_reason, "text": "".join(text_parts)}]
    result: JsonObject = {"choices": choice_values}
    if usage is not None:
        result["usage"] = usage
    if timings is not None:
        result["timings"] = timings
    return result
