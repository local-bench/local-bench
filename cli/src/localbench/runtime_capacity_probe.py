from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from localbench._types import JsonObject, JsonValue
from localbench.persistence import atomic_write_json
from localbench.runtime_capacity_log import assess_llama_startup_capacity
from localbench.submissions.strict_json import strict_json_loads

CAPACITY_PROBE_FILENAME: Final = "runtime-capacity-probe.json"
CAPACITY_PROBE_MISMATCH: Final = "runtime_capacity_probe_mismatch"
_EXPECTED_SLOT_COUNT: Final = 1
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)


@dataclass(frozen=True, slots=True)
class CapacityProbeMismatchError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"{CAPACITY_PROBE_MISMATCH}: {self.detail}"


async def verify_llama_cpp_capacity(
    *,
    base_url: str,
    api_key: str,
    required_context_tokens: int,
    run_dir: Path,
    serve_log_path: Path,
    launch_argv: list[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> JsonObject:
    responses: dict[str, httpx.Response] = {}
    startup_log_sha256: str | None = None
    evidence: JsonObject
    try:
        startup_log_bytes = serve_log_path.read_bytes()
        startup_log_sha256 = hashlib.sha256(startup_log_bytes).hexdigest()
        startup_log = startup_log_bytes.decode("utf-8")
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
            transport=transport,
            follow_redirects=True,
        ) as client:
            for path in ("/props", "/v1/models", "/slots"):
                response = await client.get(path)
                _ = response.raise_for_status()
                responses[path] = response
        props = _json_value(responses["/props"])
        models = _json_value(responses["/v1/models"])
        slots = _json_value(responses["/slots"])
        evidence = _capacity_evidence(
            props=props,
            models=models,
            slots=slots,
            required_context_tokens=required_context_tokens,
            responses=responses,
            startup_log=startup_log,
            startup_log_sha256=startup_log_sha256,
            launch_argv=launch_argv,
        )
    except (httpx.HTTPError, KeyError, OSError, TypeError, UnicodeError, ValueError) as error:
        failure_reasons: list[JsonValue] = [
            f"capacity endpoint evidence unavailable: {error}",
        ]
        evidence = {
            "schema": "localbench.runtime_capacity_probe.v1",
            "passed": False,
            "required_context_tokens": required_context_tokens,
            "response_sha256": _response_hashes(responses),
            "startup_log_sha256": startup_log_sha256,
            "failure_reasons": failure_reasons,
        }
    atomic_write_json(evidence, run_dir / CAPACITY_PROBE_FILENAME)
    failures = evidence["failure_reasons"]
    if isinstance(failures, list) and failures:
        raise CapacityProbeMismatchError("; ".join(str(reason) for reason in failures))
    return evidence


def _capacity_evidence(
    *,
    props: JsonValue,
    models: JsonValue,
    slots: JsonValue,
    required_context_tokens: int,
    responses: dict[str, httpx.Response],
    startup_log: str,
    startup_log_sha256: str,
    launch_argv: list[str],
) -> JsonObject:
    failures: list[str] = []
    props_object = _required_object(props, "/props", failures)
    models_object = _required_object(models, "/v1/models", failures)
    slot_objects = _required_slots(slots, failures)
    default_settings = _nested_object(props_object, "default_generation_settings")
    model_meta = _first_model_meta(models_object, failures)

    effective_context = _positive_int(default_settings.get("n_ctx"))
    total_slots = _positive_int(props_object.get("total_slots"))
    model_context = _positive_int(model_meta.get("n_ctx"))
    native_context = _positive_int(model_meta.get("n_ctx_train"))
    slot_contexts = [_positive_int(slot.get("n_ctx")) for slot in slot_objects]
    startup = assess_llama_startup_capacity(
        startup_log,
        launch_argv,
        required_context_tokens,
    )
    failures.extend(startup.failures)

    _require_exact_context(
        "effective context",
        effective_context,
        required_context_tokens,
        failures,
    )
    _require_exact_context(
        "model effective context",
        model_context,
        required_context_tokens,
        failures,
    )
    if native_context is None or native_context < required_context_tokens:
        failures.append(
            f"n_ctx_train must be at least {required_context_tokens}; observed {native_context!r}",
        )
    if total_slots != _EXPECTED_SLOT_COUNT:
        failures.append(f"capacity profile requires a single slot; observed {total_slots!r}")
    if len(slot_objects) != _EXPECTED_SLOT_COUNT:
        failures.append(
            f"slot allocation must report exactly one slot; observed {len(slot_objects)}",
        )
    for slot_context in slot_contexts:
        _require_exact_context(
            "slot context",
            slot_context,
            required_context_tokens,
            failures,
        )

    effective: JsonObject = {
        "context_tokens": effective_context,
        "model_context_tokens": model_context,
        "native_context_tokens": native_context,
        "logged_context_tokens": startup.context_tokens,
        "logged_slot_context_tokens": startup.slot_context_tokens,
        "logged_parallel_slots": startup.parallel_slots,
        "cache_type_k": startup.cache_type_k,
        "cache_type_v": startup.cache_type_v,
        "fit": startup.fit,
        "flash_attn": startup.flash_attn,
        "total_slots": total_slots,
        "slot_context_tokens": [value for value in slot_contexts],
    }
    failure_reasons: list[JsonValue] = [failure for failure in failures]
    return {
        "schema": "localbench.runtime_capacity_probe.v1",
        "passed": not failures,
        "required_context_tokens": required_context_tokens,
        "response_sha256": _response_hashes(responses),
        "startup_log_sha256": startup_log_sha256,
        "effective": effective,
        "failure_reasons": failure_reasons,
    }


def _json_value(response: httpx.Response) -> JsonValue:
    return strict_json_loads(response.content, response.request.url.path)


def _required_object(
    value: JsonValue,
    endpoint: str,
    failures: list[str],
) -> JsonObject:
    if isinstance(value, dict):
        return value
    failures.append(f"{endpoint} response is not an object")
    return {}


def _required_slots(value: JsonValue, failures: list[str]) -> list[JsonObject]:
    if not isinstance(value, list):
        failures.append("/slots response is not an array")
        return []
    slot_objects = [slot for slot in value if isinstance(slot, dict)]
    if len(slot_objects) != len(value):
        failures.append("slot allocation contains a malformed slot")
    if not slot_objects:
        failures.append("slot allocation is missing")
    return slot_objects


def _nested_object(container: JsonObject, key: str) -> JsonObject:
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _first_model_meta(models: JsonObject, failures: list[str]) -> JsonObject:
    data = models.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        failures.append("/v1/models must report exactly one model")
        return {}
    meta = data[0].get("meta")
    if not isinstance(meta, dict):
        failures.append("/v1/models omitted model meta")
        return {}
    return meta


def _positive_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _require_exact_context(
    label: str,
    observed: int | None,
    required: int,
    failures: list[str],
) -> None:
    if observed != required:
        failures.append(f"{label} must equal {required}; observed {observed!r}")


def _response_hashes(responses: dict[str, httpx.Response]) -> JsonObject:
    return {
        path.removeprefix("/").replace("/", "_"): hashlib.sha256(
            response.content,
        ).hexdigest()
        for path, response in sorted(responses.items())
    }
