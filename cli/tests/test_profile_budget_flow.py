from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from localbench._types import BenchmarkItem, JsonObject
from localbench.bounded_final_forcing import (
    _profile_owned_static_budget,
    run_bounded_final_forced_item,
)
from localbench.bounded_final_profiles import (
    BoundedFinalProfileChoice,
    BoundedFinalProfileRuntime,
    resolve_bounded_final_profile_from_introspection,
)
from localbench.execution_contract import _DEEP_BUDGET_PROFILE_IDS
from localbench import execution_contract as execution_contract_mod
from localbench.lane_spec import BOUNDED_FINAL_MIN_FINAL, bounded_final_think_budget
from localbench.orchestrate import _budget_audit
from localbench.prompt_rendering import TemplateIntrospection
from localbench.reasoning_registry import GENERIC_THINK_TAGS_PROFILE
from profile_budget_flow_support import capacity_probe_calls_for_profile


_PROFILE_CASES: tuple[tuple[BoundedFinalProfileChoice, bool], ...] = (
    ("generic_think_tags_32768_v1", True),
    ("gemma4_channel_32768_v1", True),
    ("generic_think_tags_8192_v1", False),
    ("gemma4_channel_8192_v1", False),
    ("answer_only_v1", False),
)
_SUITE_ITEM_PATH = Path(__file__).resolve().parents[2] / "suite" / "v1" / "amo.jsonl"
_PROFILE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "localbench"
    / "submissions"
    / "schemas"
    / "accepted_result_projection_v2.schema.json"
)


class _Renderer:
    def render(self, messages: list[dict[str, str]]) -> str:
        return "rendered-prompt"


@dataclass(frozen=True, slots=True)
class _FlowObservation:
    original_max_tokens: int
    configured_answer_reserve: int
    legacy_final_reserve: int
    item_max_tokens: int
    request_caps: tuple[int, ...]
    audit_promise: int


def _runtime(profile: BoundedFinalProfileChoice) -> BoundedFinalProfileRuntime:
    return resolve_bounded_final_profile_from_introspection(
        profile,
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=True,
        ),
    )


def _suite_item() -> BenchmarkItem:
    raw = json.loads(_SUITE_ITEM_PATH.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(raw["id"], str)
    assert isinstance(raw["statement"], str)
    assert isinstance(raw["sampling_params"], dict)
    assert isinstance(raw["max_tokens"], int)
    return {
        "id": raw["id"],
        "messages": [{"role": "user", "content": raw["statement"]}],
        "sampling_params": raw["sampling_params"],
        "max_tokens": raw["max_tokens"],
    }


def _observe_profile_flow(profile: BoundedFinalProfileChoice) -> _FlowObservation:
    runtime = _runtime(profile)
    forcing_format = runtime.forcing or GENERIC_THINK_TAGS_PROFILE.forcing
    assert forcing_format is not None
    item = _suite_item()
    original_max_tokens = item["max_tokens"]
    configured_answer_reserve = item.get("answer_reserve", BOUNDED_FINAL_MIN_FINAL)
    legacy_think_budget = bounded_final_think_budget(
        original_max_tokens,
        answer_reserve=configured_answer_reserve,
    )
    legacy_final_reserve = original_max_tokens - legacy_think_budget
    request_caps: list[int] = []

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            cap = body["max_tokens"]
            request_caps.append(cap)
            first_pass = len(request_caps) == 1
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "text": "reasoning" if first_pass else "Answer: A",
                            "finish_reason": "length" if first_pass else "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": cap if first_pass else 1,
                        "total_tokens": cap + 1 if first_pass else 2,
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await run_bounded_final_forced_item(
                client=client,
                base_url="http://local/v1",
                headers={},
                model="demo",
                item=item,
                semaphore=asyncio.Semaphore(1),
                max_attempts=1,
                backoff_base=0.0,
                prompt_renderer=_Renderer(),
                forcing_format=forcing_format,
                execution_contract=runtime.contract,
            )

    asyncio.run(scenario())
    item_max_tokens = item["max_tokens"]
    audit = _budget_audit(
        [
            {
                "bench": "amo",
                "id": item["id"],
                "max_tokens": item_max_tokens,
                "generated_tokens": {"total": 2},
            }
        ],
    )
    audit_promise = audit["per_bench"]["amo"]["max_promised_total"]
    assert isinstance(audit_promise, int)
    return _FlowObservation(
        original_max_tokens=original_max_tokens,
        configured_answer_reserve=configured_answer_reserve,
        legacy_final_reserve=legacy_final_reserve,
        item_max_tokens=item_max_tokens,
        request_caps=tuple(request_caps),
        audit_promise=audit_promise,
    )


@pytest.mark.parametrize(("profile", "is_deep"), _PROFILE_CASES)
def test_profile_budget_flow_overrides_only_deep_item_promises(
    profile: BoundedFinalProfileChoice,
    is_deep: bool,
) -> None:
    observation = _observe_profile_flow(profile)

    expected = 49152 if is_deep else observation.original_max_tokens
    assert observation.item_max_tokens == expected


@pytest.mark.parametrize(("profile", "is_deep"), _PROFILE_CASES)
def test_profile_budget_flow_preserves_legacy_per_item_request_arithmetic(
    profile: BoundedFinalProfileChoice,
    is_deep: bool,
) -> None:
    observation = _observe_profile_flow(profile)

    expected = (
        (32768, 16384)
        if is_deep
        else (
            bounded_final_think_budget(
                observation.original_max_tokens,
                answer_reserve=observation.configured_answer_reserve,
            ),
            observation.legacy_final_reserve,
        )
    )
    assert observation.request_caps == expected


@pytest.mark.parametrize(("profile", "is_deep"), _PROFILE_CASES)
def test_profile_budget_flow_audits_deep_and_legacy_item_promises(
    profile: BoundedFinalProfileChoice,
    is_deep: bool,
) -> None:
    observation = _observe_profile_flow(profile)

    expected = 49152 if is_deep else observation.original_max_tokens
    assert observation.audit_promise == expected


def test_deep_budget_profile_predicate_matches_the_frozen_pair() -> None:
    actual = {
        profile
        for profile, _is_deep in _PROFILE_CASES
        if execution_contract_mod.is_deep_budget_profile(profile)
    }

    assert actual == set(_DEEP_BUDGET_PROFILE_IDS)


@pytest.mark.parametrize(("profile", "is_deep"), _PROFILE_CASES)
def test_static_budget_exists_if_and_only_if_profile_is_deep(
    profile: BoundedFinalProfileChoice,
    is_deep: bool,
) -> None:
    runtime = _runtime(profile)

    assert (_profile_owned_static_budget(runtime.contract) is not None) is is_deep


def _profile_schema_errors(profile: JsonObject) -> list[str]:
    schema = json.loads(_PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/executionProfile",
        }
    )
    return [error.message for error in validator.iter_errors(profile)]


@pytest.mark.parametrize("profile", _DEEP_BUDGET_PROFILE_IDS)
def test_deep_profile_v2_projection_round_trips_schema(profile: str) -> None:
    projected = execution_contract_mod.execution_profile_record(_runtime(profile).contract)

    assert _profile_schema_errors(projected) == []


@pytest.mark.parametrize("profile", _DEEP_BUDGET_PROFILE_IDS)
def test_deep_profile_legacy_shape_is_rejected_by_schema(profile: str) -> None:
    projected = execution_contract_mod.execution_profile_record(_runtime(profile).contract)
    legacy_shaped = {
        field: projected[field]
        for field in execution_contract_mod._PUBLIC_EXECUTION_PROFILE_FIELDS
    }

    assert _profile_schema_errors(legacy_shaped) != []


def test_legacy_profile_v1_projection_still_round_trips_schema() -> None:
    projected = execution_contract_mod.execution_profile_record(
        _runtime("generic_think_tags_8192_v1").contract
    )

    assert "schema_version" not in projected
    assert _profile_schema_errors(projected) == []


@pytest.mark.parametrize(("profile", "is_deep"), _PROFILE_CASES)
def test_runner_arms_capacity_probe_only_for_deep_profiles(
    profile: BoundedFinalProfileChoice,
    is_deep: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity_calls = capacity_probe_calls_for_profile(
        _runtime(profile),
        profile,
        tmp_path,
        monkeypatch,
    )

    assert capacity_calls == ([65536] if is_deep else [])
