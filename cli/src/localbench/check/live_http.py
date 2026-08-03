from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import cast

import httpx

from localbench._types import BenchmarkItem, ChatMessage, JsonObject, JsonValue
from localbench.budget_forcing import run_forced_item
from localbench.check.budget import THINK_BUDGET, generation_parameters
from localbench.check.types import CheckError, ConstructionDefect
from localbench.prompt_rendering import LlamaApplyTemplatePromptRenderer, PromptRenderer


@dataclass(frozen=True, slots=True)
class LiveHttpConfig:
    base_url: str
    api_key: str
    model_id: str
    server_start_id: str


@dataclass(frozen=True, slots=True)
class _RendererAdapter:
    renderer: LlamaApplyTemplatePromptRenderer

    def render(self, messages: list[ChatMessage]) -> str:
        rendered_messages: list[JsonObject] = [
            {"content": message["content"], "role": message["role"]} for message in messages
        ]
        return self.renderer.render(rendered_messages)


def build_live_prompt_renderer(config: LiveHttpConfig, props: JsonObject) -> PromptRenderer:
    template = props.get("chat_template")
    if not isinstance(template, str) or not template:
        raise CheckError("llama-server /props did not expose a chat template")
    renderer = LlamaApplyTemplatePromptRenderer(
        base_url=config.base_url,
        api_key=config.api_key,
        template=template,
        contract_raw_template_sha256=hashlib.sha256(template.encode()).hexdigest(),
        chat_template_kwargs={"enable_thinking": True},
    )
    return _RendererAdapter(renderer)


def generate_live_item(
    config: LiveHttpConfig,
    *,
    module: str,
    item_id: str,
    source: JsonObject,
    prompt_renderer: PromptRenderer,
) -> JsonObject:
    return asyncio.run(
        _generate_live_item(
            config,
            module=module,
            item_id=item_id,
            source=source,
            prompt_renderer=prompt_renderer,
        )
    )


def live_prompt_character_count(module: str, source: JsonObject) -> int:
    return sum(len(message["content"]) for message in _messages(module, source))


def render_live_prompt(module: str, source: JsonObject, prompt_renderer: PromptRenderer) -> str:
    return prompt_renderer.render(_messages(module, source))


def tokenize_live_prompt(config: LiveHttpConfig, prompt: str) -> int:
    headers = {"Authorization": f"Bearer {config.api_key}"}
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.post(
            f"{config.base_url}/tokenize",
            headers=headers,
            json={"add_special": False, "content": prompt},
        )
        _ = response.raise_for_status()
        return len(_token_ids(response.json()))


async def _generate_live_item(
    config: LiveHttpConfig,
    *,
    module: str,
    item_id: str,
    source: JsonObject,
    prompt_renderer: PromptRenderer,
) -> JsonObject:
    params = generation_parameters(module)
    answer_budget = params.get("answer_budget_tokens")
    max_tokens = params.get("max_tokens")
    if not isinstance(answer_budget, int) or not isinstance(max_tokens, int):
        raise CheckError(f"module {module!r} has invalid generation parameters")
    benchmark: BenchmarkItem = {
        "id": item_id,
        "messages": _messages(module, source),
        "sampling_params": {
            "cache_prompt": False,
            "frequency_penalty": 0,
            "min_p": 0,
            "n": 1,
            "presence_penalty": 0,
            "repeat_penalty": 1,
            "seed": 1234,
            "temperature": 0,
            "top_k": 1,
            "top_p": 1,
        },
        "max_tokens": max_tokens,
        "think_budget": THINK_BUDGET,
        "answer_reserve": answer_budget,
    }
    headers = {"Authorization": f"Bearer {config.api_key}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
        result = await run_forced_item(
            client=client,
            base_url=f"{config.base_url}/v1",
            headers=headers,
            model=config.model_id,
            item=benchmark,
            semaphore=asyncio.Semaphore(1),
            max_attempts=1,
            backoff_base=0,
            prompt_renderer=prompt_renderer,
            stream=True,
        )
        error = result.get("error")
        if isinstance(error, str):
            detail = f"live completion failed for {item_id}: {error}"
            if "exceed_context_size_error" in error:
                raise ConstructionDefect("execution", detail)
            raise CheckError(detail)
        response = result.get("response_text")
        reasoning = result.get("reasoning_text")
        if not isinstance(response, str):
            raise CheckError(f"live completion returned no text for {item_id}")
        generated_text = f"{reasoning if isinstance(reasoning, str) else ''}{response}"
        token_ids = await _tokenize(client, config, generated_text)
    parsed_calls = _parse_tool_calls(response)
    raw_usage = result.get("usage")
    usage: JsonObject = {
        key: raw_usage.get(key)
        for key in ("completion_tokens", "prompt_tokens", "reasoning_tokens", "total_tokens")
    }
    generation: JsonObject = {
        "finish_reason": result.get("finish_reason"),
        "latency_seconds": result.get("latency_seconds"),
        "parsed_tool_calls": parsed_calls,
        "protocol_flag": _protocol_flag(reasoning, result.get("thinking_forced")),
        "reasoning_text": reasoning,
        "server_start_id": config.server_start_id,
        "text": response,
        "token_ids": token_ids,
        "usage": usage,
    }
    if source.get("category") == "determinism":
        generation["scorer_result"] = {"correct": _determinism_primary(source, generation)}
    return generation


async def _tokenize(client: httpx.AsyncClient, config: LiveHttpConfig, text: str) -> list[JsonValue]:
    response = await client.post(
        f"{config.base_url}/tokenize",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={"add_special": False, "content": text},
    )
    _ = response.raise_for_status()
    return _token_ids(response.json())


def _token_ids(raw_response: JsonValue) -> list[JsonValue]:
    raw_payload = cast(object, raw_response)
    payload = cast(JsonObject, raw_payload) if isinstance(raw_payload, dict) else None
    tokens = payload.get("tokens") if isinstance(payload, dict) else None
    if not isinstance(tokens, list) or not all(isinstance(token, int) for token in tokens):
        raise CheckError("llama-server /tokenize returned invalid token ids")
    return [token for token in tokens if isinstance(token, int)]


def _messages(module: str, source: JsonObject) -> list[ChatMessage]:
    system = "Return only the requested answer. Do not add commentary."
    if source.get("stateful_final") is True:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": _source_text(source, "prompt")},
        ]
    if module in {"tools-single", "tools-stateful"} or isinstance(source.get("tools"), list):
        system = (
            "Return canonical JSON only: {\"calls\":[{\"name\":string,\"arguments\":object}]}. "
            "Use only the declared tools and include the complete required call sequence."
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": _prompt(module, source)}]


def _prompt(module: str, source: JsonObject) -> str:
    if module == "knowledge":
        question = _source_text(source, "question")
        choices = source.get("choices")
        if not isinstance(choices, list):
            raise CheckError("knowledge item has no choices")
        rendered = "\n".join(f"{chr(65 + index)}. {choice}" for index, choice in enumerate(choices))
        return f"{question}\n{rendered}\nReturn the single answer letter."
    if module == "instruction":
        return _source_text(source, "prompt")
    if module == "math":
        return _first_source_text(source, ("statement", "problem", "question", "prompt"))
    if module == "coding":
        return _first_source_text(source, ("instruct_prompt", "code_prompt"))
    if module == "tools-single" or isinstance(source.get("tools"), list):
        return f"{_source_text(source, 'prompt')}\nDeclared tools:\n{_canonical(source.get('tools'))}"
    if module == "tools-stateful":
        return f"{_source_text(source, 'prompt')}\nDeclared tools:\n{_canonical(source.get('tool_schemas'))}"
    return _source_text(source, "prompt")


def _parse_tool_calls(text: str) -> list[JsonValue]:
    try:
        raw_parsed = cast(object, json.loads(text))
    except json.JSONDecodeError:
        return []
    parsed = cast(JsonObject, raw_parsed) if isinstance(raw_parsed, dict) else None
    raw_calls = parsed.get("calls") if parsed is not None else None
    if not isinstance(raw_calls, list):
        return []
    return [dict(cast(JsonObject, call)) for call in raw_calls if isinstance(call, dict)]


def _determinism_primary(source: JsonObject, generation: JsonObject) -> bool:
    expected = source.get("expected")
    if not isinstance(expected, dict):
        return False
    answer = expected.get("answer")
    text = generation.get("text")
    if isinstance(answer, str):
        return isinstance(text, str) and answer in text
    tool = expected.get("tool")
    arguments = expected.get("arguments")
    calls = generation.get("parsed_tool_calls")
    return isinstance(tool, str) and isinstance(arguments, dict) and isinstance(calls, list) and {
        "name": tool,
        "arguments": arguments,
    } in calls


def _protocol_flag(reasoning: JsonValue | None, forced: JsonValue | None) -> str | None:
    if forced is True:
        return "think-budget-exhausted"
    return None if isinstance(reasoning, str) and "<think>" in reasoning else "think-markers-absent"


def _source_text(source: JsonObject, key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"source item has no {key!r} prompt text")
    return value


def _first_source_text(source: JsonObject, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    raise CheckError(f"source item has none of the required prompt fields: {', '.join(keys)}")


def _canonical(value: JsonValue | None) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
