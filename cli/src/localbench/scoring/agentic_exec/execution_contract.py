"""Canonical C0 execution-contract extraction, signing, and fail-closed verification."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import canonical_json_hash, write_json_file
from localbench.submissions.crypto import sign_manifest_payload, verify_manifest_signature

CONTRACT_ID: Final = "agentic-execution-contract-v1"
CONTRACT_SCHEMA: Final = "localbench.agentic_execution_contract.v1"
CONTRACT_FILENAME: Final = f"{CONTRACT_ID}.json"
CONTRACT_KEY_ID: Final = "localbench-agentic-contract-2026-07"
CONTRACT_PUBLIC_KEY_HEX: Final = "0becc292026a52fcb7a598cd3729bc45d3bfc31f9aec1b903acec5ddfdbaa6b0"
HISTORICAL_SCORED_RECEIPT_HASH: Final = (
    "1920064637cf2a780e0484fcdeb2752b200a247418148eeb9a172047fe7192ad"
)
HISTORICAL_BOARD_ROW_HASH: Final = (
    "7aabcf2af32300cf8769ce63cdc09353e7eab3a8681386d46fb0747950c85095"
)

_HOST_SOURCE_MODULES: Final = (
    "localbench.orchestrate",
    "localbench.serving.agentic_support",
    "localbench.scoring.agentic_exec.benchmark",
    "localbench.scoring.agentic_exec.block_introspect",
    "localbench.scoring.agentic_exec.block_parser",
    "localbench.scoring.agentic_exec.chat_client",
    "localbench.scoring.agentic_exec.funnel",
    "localbench.scoring.agentic_exec.loop_config",
    "localbench.scoring.agentic_exec.loop_types",
    "localbench.scoring.agentic_exec.model_client",
    "localbench.scoring.agentic_exec.prompt",
    "localbench.scoring.agentic_exec.protocol_c_loop",
    "localbench.scoring.agentic_exec.sandbox",
    "localbench.scoring.agentic_exec.score",
    "localbench.scoring.agentic_exec.task_pool",
    "localbench.scoring.agentic_exec.wsl_process",
    "localbench.scoring.agentic_exec.wsl_proxy",
    "localbench.scoring.agentic_exec.wsl_worker",
)


@dataclass(frozen=True, slots=True)
class ExecutionContractDriftError(RuntimeError):
    expected_digest: str
    actual_digest: str

    def __str__(self) -> str:
        return (
            f"agentic execution contract drift: expected {self.expected_digest}, "
            f"observed {self.actual_digest}"
        )


@dataclass(frozen=True, slots=True)
class TaskIdentityDriftError(RuntimeError):
    field: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"agentic task identity drift for {self.field}: expected {self.expected}, observed {self.actual}"


def extract_contract_payload(
    *,
    ordered_task_ids: list[str],
    semantic_task_contents: dict[str, JsonValue],
    appworld_identity: JsonObject,
    sandbox_identity: JsonObject,
) -> JsonObject:
    """Extract a deterministic contract payload from live code and pinned task content."""
    from localbench.scoring.agentic_exec import task_pool

    behavior, provenance = _extract_covered_behavior()
    ordered_hash = task_pool.ordered_task_ids_sha256(ordered_task_ids)
    recipe = {
        "split": "test_normal",
        "seed": 20260624,
        "selection_version": "v1",
    }
    semantic_hash = task_pool.semantic_task_sha256(semantic_task_contents)
    payload: JsonObject = {
        "schema": CONTRACT_SCHEMA,
        "contract_id": CONTRACT_ID,
        "covered_behavior": behavior,
        "covered_behavior_sha256": canonical_json_hash(behavior),
        "task_identity": {
            "ordered_task_ids": list(ordered_task_ids),
            "ordered_task_ids_sha256": ordered_hash,
            "selection_recipe": recipe,
            "selection_recipe_sha256": task_pool.selection_recipe_sha256(**recipe),
            "semantic_task_sha256": semantic_hash,
            "semantic_canonicalisation": (
                "tasks sorted by task_id; canonical JSON of instructions/specs, parsed JSONL DB "
                "setup, parsed ground-truth JSON, and LF-normalised evaluation.py"
            ),
            "historical_aliases": [
                {
                    "sha256": HISTORICAL_SCORED_RECEIPT_HASH,
                    "meaning": "pre-C0 mixed hash: scored selection recipe plus ordered IDs",
                },
                {
                    "sha256": HISTORICAL_BOARD_ROW_HASH,
                    "meaning": "pre-C0 mixed hash after injected split/seed mutation plus ordered IDs",
                },
            ],
        },
        "appworld_identity": dict(appworld_identity),
        "sandbox_identity": dict(sandbox_identity),
        "legacy_continuity": {
            "decision": "accepted_by_owner_fiat",
            "decided_on": "2026-07-11",
            "legacy_bridge_required": False,
            "real_model_ab_required": False,
            "anchor_reruns_required": False,
        },
        "packaging_correctness_gate": {
            "required": True,
            "kind": "scripted_agent_current_harness_vs_appliance_differential",
            "equal_fields": ["per_turn_requests", "sandbox_ops", "verdicts", "aggregates"],
            "gpu_required": False,
        },
        "provenance": {
            "schema": "cli/src/localbench/scoring/agentic_exec/execution_contract.py:17-18",
            "contract_id": "cli/src/localbench/scoring/agentic_exec/execution_contract.py:17-18",
            "covered_behavior_sha256": (
                "cli/src/localbench/scoring/agentic_exec/execution_contract.py:95"
            ),
            **provenance,
            "task_identity.ordered_task_ids": (
                "runs/bench/ranked-5axis-capped-2026-07-03/agentic/localbench-run/"
                "gemma-4-12b-it-qat-ud-q4-k-xl.scored.run1.json:24"
            ),
            "task_identity.selection_recipe": (
                "cli/src/localbench/scoring/agentic_exec/funnel.py:57-71"
            ),
            "task_identity.ordered_task_ids_sha256": (
                "cli/src/localbench/scoring/agentic_exec/task_pool.py:14-16"
            ),
            "task_identity.selection_recipe_sha256": (
                "cli/src/localbench/scoring/agentic_exec/task_pool.py:19-29"
            ),
            "task_identity.semantic_task_sha256": (
                "$APPWORLD_ROOT/data/tasks/<task_id>/{specs.json,dbs/*,ground_truth/*}:1"
            ),
            "task_identity.semantic_canonicalisation": (
                "cli/src/localbench/scoring/agentic_exec/task_pool.py:30-91"
            ),
            "task_identity.historical_aliases": "scratchpad/appliance-spec-v3.md:84-94",
            "appworld_identity": "cli/src/localbench/scoring/agentic_exec/wsl_worker.py:166-200",
            "sandbox_identity": "cli/src/localbench/scoring/agentic_exec/sandbox.py:101-120,328-359",
            "legacy_continuity": "scratchpad/appliance-spec-v3.md:95-99",
            "packaging_correctness_gate": "scratchpad/appliance-spec-v3.md:100-107",
        },
    }
    payload["provenance"] = _leaf_provenance(payload, _object(payload["provenance"]))
    return payload


def signed_contract(payload: JsonObject, signing_key: Path) -> JsonObject:
    return {
        "payload": payload,
        "payload_sha256": canonical_json_hash(payload),
        "signature": {
            "key_id": CONTRACT_KEY_ID,
            **sign_manifest_payload(payload, signing_key),
        },
    }


def write_signed_contract(path: Path, payload: JsonObject, signing_key: Path) -> JsonObject:
    contract = signed_contract(payload, signing_key)
    write_json_file(path, contract)
    return contract


def load_execution_contract(path: Path | None = None) -> JsonObject:
    if path is None:
        resource = resources.files("localbench").joinpath("data", "contracts", CONTRACT_FILENAME)
        raw = resource.read_text(encoding="utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ExecutionContractDriftError("signed-object", type(parsed).__name__)
    contract: JsonObject = parsed
    payload = contract.get("payload")
    signature = contract.get("signature")
    trusted_signature = (
        isinstance(signature, dict)
        and signature.get("key_id") == CONTRACT_KEY_ID
        and signature.get("public_key") == CONTRACT_PUBLIC_KEY_HEX
    )
    if not isinstance(payload, dict) or not trusted_signature or not verify_manifest_signature(contract):
        raise ExecutionContractDriftError("valid-ed25519-signature", "invalid")
    expected = contract.get("payload_sha256")
    actual = canonical_json_hash(payload)
    if not isinstance(expected, str) or expected != actual:
        raise ExecutionContractDriftError(str(expected), actual)
    return contract


def assert_execution_contract(path: Path | None = None) -> str:
    """Fail closed when currently imported score-affecting behavior differs from C0."""
    contract = load_execution_contract(path)
    payload = _object(contract["payload"])
    expected_behavior = _object(payload["covered_behavior"])
    actual_behavior, _provenance = _extract_covered_behavior()
    expected = canonical_json_hash(expected_behavior)
    actual = canonical_json_hash(actual_behavior)
    if expected != actual:
        raise ExecutionContractDriftError(expected, actual)
    return str(contract["payload_sha256"])


def assert_task_identity(
    task_ids: list[str],
    semantic_task_contents: dict[str, JsonValue],
    path: Path | None = None,
) -> None:
    from localbench.scoring.agentic_exec import task_pool

    payload = _object(load_execution_contract(path)["payload"])
    identity = _object(payload["task_identity"])
    checks = {
        "ordered_task_ids_sha256": task_pool.ordered_task_ids_sha256(task_ids),
        "semantic_task_sha256": task_pool.semantic_task_sha256(semantic_task_contents),
    }
    for field, actual in checks.items():
        expected = str(identity.get(field))
        if expected != actual:
            raise TaskIdentityDriftError(field, expected, actual)


def contract_task_ids(path: Path | None = None) -> list[str]:
    payload = _object(load_execution_contract(path)["payload"])
    identity = _object(payload["task_identity"])
    ids = identity.get("ordered_task_ids")
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise ExecutionContractDriftError("ordered string IDs", repr(ids))
    return list(ids)


def _extract_covered_behavior() -> tuple[JsonObject, JsonObject]:
    import localbench.orchestrate as orchestrate
    from localbench.reasoning_registry import (
        REASONING_REGISTRY,
        execution_profile_digest,
        execution_profile_payload,
    )
    from localbench.scoring.agentic_exec import (
        benchmark,  # noqa: F401 - imported source is covered by the bundle digest.
        block_introspect,  # noqa: F401 - imported source is covered by the bundle digest.
        block_parser,
        chat_client,
        funnel,
        loop_config,
        prompt,
        sandbox,
        wsl_process,
    )

    loop = loop_config.LoopConfig(
        max_output_tokens_per_turn=orchestrate._AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN,
    )
    wsl = wsl_process.WslWorkerConfig("", "", "")
    sandbox_cfg = sandbox.SandboxConfig()
    source_digest = _source_bundle_sha256(_HOST_SOURCE_MODULES)
    prompt_digest = canonical_json_hash(
        {
            "system_template": prompt._SYSTEM_TEMPLATE,
            "app_hint": prompt._DEFAULT_APP_HINT,
            "final_answer_sentinel": block_parser.FINAL_ANSWER_SENTINEL,
            "kickoff": "Begin.",
        },
    )
    parser_digest = _source_bundle_sha256(
        ("localbench.scoring.agentic_exec.block_parser",),
    )
    observation_digest = _source_bundle_sha256(
        (
            "localbench.scoring.agentic_exec.block_introspect",
            "localbench.scoring.agentic_exec.observations",
            "localbench.scoring.agentic_exec.prompt",
        ),
    )
    behavior: JsonObject = {
        "host_agent_loop_scorer_source_sha256": source_digest,
        "prompt_sha256": prompt_digest,
        "block_parser_sha256": parser_digest,
        "observation_canonicalisation_truncation_sha256": observation_digest,
        "budgets": {
            "max_turns": loop.max_turns,
            "max_output_tokens_per_turn": loop.max_output_tokens_per_turn,
            "max_observation_chars": loop.max_observation_chars,
            "context_window": loop.context_window,
            "temperature": loop.temperature,
            "top_p": loop.top_p,
            "seed": loop.seed,
            "model_call_timeout_s": loop.model_call_timeout_s,
            "model_call_timeout_enforced": False,
            "per_task_watchdog_s": loop.per_task_timeout_s,
            "finalize_teardown_reserve_s": loop_config.TASK_FINALIZE_TEARDOWN_RESERVE_S,
        },
        "timeouts": {
            "wsl_open_task_s": wsl.open_task_timeout_s,
            "wsl_operation_s": wsl.op_timeout_s,
            "wsl_finalize_s": wsl.finalize_timeout_s,
            "wsl_close_s": wsl.close_timeout_s,
            "sandbox_ready_s": sandbox_cfg.ready_timeout_s,
            "sandbox_block_wall_s": sandbox_cfg.block_wall_timeout_s,
            "sandbox_finalize_s": sandbox_cfg.finalize_timeout_s,
            "chat_client_floor_s": chat_client._MIN_REQUEST_TIMEOUT_S,
            "chat_min_generation_tokens_per_second": chat_client._MIN_GENERATION_TOKENS_PER_SECOND,
            "chat_task_transport_budget_s": chat_client._DEFAULT_TASK_TRANSPORT_BUDGET_S,
        },
        "transport_policy": {
            "requests_per_turn": 1,
            "retries": 0,
            "backoff": None,
            "clock_start": "before_sandbox_open",
            "deadline_scope": "one_monotonic_deadline_shared_by_all_turns",
            "cancellation": "close_active_http_connection_then_force_kill_sandbox",
            "teardown": "fresh_sandbox_per_task; context_manager_close; watchdog_waits_for_worker_exit",
        },
        "failure_to_score": {
            "success": 1,
            "cap_exceeded": 0,
            "no_final_answer": 0,
            "model_failure": 0,
            "model_no_progress": 0,
            "infra_timeout": 0,
            "infra_sandbox": 0,
            "harness_error": 0,
            "denominator": "all_manifest_tasks",
        },
        "run_aggregation": {
            "base_runs": funnel.RERUN_BASE_COUNT,
            "third_run_trigger": "max_abs_pairwise_asr_delta_pp > threshold_pp",
            "threshold_pp": funnel.DELTA_TRIGGER_PP,
            "reported_value": "arithmetic_mean_asr_over_all_executed_runs",
        },
        "chat_template_policy": {
            "request_semantics": "full_visible_conversation_per_turn",
            "kwargs_forwarding": "verbatim_when_nonempty",
            "answer-only": {"enable_thinking": False},
            "capped-thinking": {"enable_thinking": True},
            "api-uncapped": {},
            "bounded-final-profile-policy": {
                "answer_only_v1": {"enable_thinking": False},
                "generic_think_tags_8192_v1": {"enable_thinking": True},
                "gemma4_channel_8192_v1": {"enable_thinking": True},
            },
        },
        "execution_profiles": {
            entry.id: {
                "payload": execution_profile_payload(entry),
                "sha256": execution_profile_digest(entry),
            }
            for entry in REASONING_REGISTRY
        },
        "sandbox_policy": {
            "cpu_seconds": sandbox_cfg.cpu_seconds,
            "address_space_bytes": sandbox_cfg.address_space_bytes,
            "tmpfs_size_bytes": sandbox_cfg.tmpfs_size_bytes,
            "network": "unshared",
            "capabilities": "drop_all",
            "filesystem": "read_only_usr; empty_tmp_home; rpc_bind_only",
            "environment": {
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "TZ": "UTC",
                "LC_ALL": "C.UTF-8",
            },
        },
    }
    provenance: JsonObject = {
        "covered_behavior.host_agent_loop_scorer_source_sha256": (
            "cli/src/localbench/scoring/agentic_exec/execution_contract.py:29-48"
        ),
        "covered_behavior.prompt_sha256": "cli/src/localbench/scoring/agentic_exec/prompt.py:30-128",
        "covered_behavior.block_parser_sha256": (
            "cli/src/localbench/scoring/agentic_exec/block_parser.py:29-130"
        ),
        "covered_behavior.observation_canonicalisation_truncation_sha256": (
            "cli/src/localbench/scoring/agentic_exec/block_introspect.py:75-81;"
            "cli/src/localbench/scoring/agentic_exec/prompt.py:131-142"
        ),
        "covered_behavior.budgets.max_turns": _field_line(loop_config, "max_turns: int ="),
        "covered_behavior.budgets.max_output_tokens_per_turn": _field_line(
            orchestrate, "_AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN: Final ="
        ),
        "covered_behavior.budgets": "cli/src/localbench/scoring/agentic_exec/loop_config.py:19-72",
        "covered_behavior.timeouts": (
            "cli/src/localbench/scoring/agentic_exec/wsl_process.py:19-22;"
            "cli/src/localbench/scoring/agentic_exec/sandbox.py:51-53,114-120;"
            "cli/src/localbench/scoring/agentic_exec/chat_client.py:27-31,207-218"
        ),
        "covered_behavior.transport_policy": (
            "cli/src/localbench/scoring/agentic_exec/chat_client.py:141-269;"
            "cli/src/localbench/scoring/agentic_exec/benchmark.py:117-146"
        ),
        "covered_behavior.failure_to_score": (
            "cli/src/localbench/scoring/agentic_exec/benchmark.py:206-279,307-361"
        ),
        "covered_behavior.run_aggregation": (
            "cli/src/localbench/scoring/agentic_exec/funnel.py:425-428,465-541"
        ),
        "covered_behavior.chat_template_policy": (
            "cli/src/localbench/orchestrate.py:1735-1747;"
            "cli/src/localbench/scoring/agentic_exec/chat_client.py:105-130"
        ),
        "covered_behavior.execution_profiles": "cli/src/localbench/reasoning_registry.py:112-231",
        "covered_behavior.sandbox_policy": (
            "cli/src/localbench/scoring/agentic_exec/sandbox.py:101-120,328-359"
        ),
    }
    return behavior, provenance


def _source_bundle_sha256(module_names: tuple[str, ...]) -> str:
    files: JsonObject = {}
    for module_name in sorted(module_names):
        module = __import__(module_name, fromlist=["__name__"])
        source_path = inspect.getsourcefile(module)
        if source_path is None:
            raise RuntimeError(f"source unavailable for contract-covered module {module_name}")
        source = Path(source_path).read_bytes().replace(b"\r\n", b"\n")
        files[module_name] = hashlib.sha256(source).hexdigest()
    return canonical_json_hash(files)


def _field_line(module: object, needle: str) -> str:
    source_path = inspect.getsourcefile(module)
    if source_path is None:
        raise RuntimeError(f"source unavailable for {module!r}")
    for line_number, line in enumerate(Path(source_path).read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            relative = _display_source_path(Path(source_path))
            return f"{relative}:{line_number}"
    raise RuntimeError(f"source token {needle!r} not found in {source_path}")


def _display_source_path(path: Path) -> str:
    parts = path.resolve().parts
    try:
        index = parts.index("cli")
    except ValueError:
        return path.as_posix()
    return Path(*parts[index:]).as_posix()


def _leaf_provenance(payload: JsonObject, prefixes: JsonObject) -> JsonObject:
    """Expand section citations so every non-provenance leaf has an exact source citation."""
    refs = {key: value for key, value in prefixes.items() if isinstance(value, str)}
    expanded: JsonObject = {}
    for path in _leaf_paths({key: value for key, value in payload.items() if key != "provenance"}):
        candidates = [
            prefix
            for prefix in refs
            if path == prefix or path.startswith(f"{prefix}.") or path.startswith(f"{prefix}[")
        ]
        if not candidates:
            raise RuntimeError(f"contract value has no file:line provenance: {path}")
        expanded[path] = refs[max(candidates, key=len)]
    return expanded


def _leaf_paths(value: JsonValue, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(_leaf_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_leaf_paths(child, f"{prefix}[{index}]"))
        return paths
    return [prefix]


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ExecutionContractDriftError("JSON object", type(value).__name__)
    return value


__all__ = [
    "CONTRACT_FILENAME",
    "CONTRACT_ID",
    "ExecutionContractDriftError",
    "TaskIdentityDriftError",
    "assert_execution_contract",
    "assert_task_identity",
    "contract_task_ids",
    "extract_contract_payload",
    "load_execution_contract",
    "signed_contract",
    "write_signed_contract",
]
