from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from localbench.checkset.input_runs import read_json
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.checkset.select import SELECTION_SEED
from localbench.submissions.canon import canonical_json_bytes

TEMPLATE_NAMES: Final = (
    "booking ledger",
    "inventory",
    "ticket triage",
    "bank-lite ops",
    "calendar constraints",
    "config migration",
    "shipment tracking",
    "library loans",
    "seat allocation",
    "subscription lifecycle",
    "warehouse picking",
    "access-control admin",
)


def build_stateful(repo_root: Path) -> tuple[ModuleRecord, JsonObject]:
    source_path = repo_root / "checkset" / "stateful-templates.json"
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    definitions = _definitions(read_json(source_path))
    if tuple(_required_str(definition, "name") for definition in definitions) != TEMPLATE_NAMES:
        raise ChecksetBuildError("Stateful template names or ordering differ from the locked twelve-template set.")
    instances = [
        _generate_instance(definition, ordinal=ordinal, spare=False)
        for definition in definitions
        for ordinal in range(4)
    ]
    spares = [
        _generate_instance(definitions[index], ordinal=100 + index, spare=True)
        for index in range(6)
    ]
    definition_values: list[JsonValue] = [definition for definition in definitions]
    instance_values: list[JsonValue] = [record for record in instances]
    spare_values: list[JsonValue] = [record for record in spares]
    module = ModuleRecord(
        name="tools-stateful",
        scored=48,
        items=tuple(ItemRecord(_required_str(record, "item_id"), _required_str(record, "content_sha256")) for record in instances),
        source={"dataset": "checkset/stateful-templates.json", "revision": source_sha256, "split": "authored"},
        scorer={"name": "state-machine-exact", "version": "localbench-v1"},
        selection={"algorithm": "seeded-state-machine-4-per-template-v1", "inputs_sha256": source_sha256, "seed": SELECTION_SEED},
    )
    metadata: JsonObject = {
        "status": "ready",
        "generator": {
            "algorithm": "seeded-state-machine-4-per-template-v1",
            "seed": SELECTION_SEED,
            "source_sha256": source_sha256,
        },
        "templates": list(TEMPLATE_NAMES),
        "template_definitions": definition_values,
        "instances": instance_values,
        "spares_ordered": spare_values,
        "cluster_map": {
            _required_str(record, "item_id"): _required_str(record, "template") for record in instances
        },
        "replacement_policy": "predeclared-mechanical-validity-defect-only",
    }
    return module, metadata


def simulate_trajectory(instance: JsonObject, trajectory: Sequence[JsonObject]) -> JsonObject:
    initial = instance.get("initial_state")
    required_arguments = instance.get("required_arguments")
    transitions = instance.get("transitions")
    if not isinstance(initial, dict) or not isinstance(required_arguments, dict) or not isinstance(transitions, list):
        raise ChecksetBuildError("Stateful instance is missing simulator inputs.")
    state = dict(initial)
    inspect_tool = _required_str(instance, "inspect_tool")
    for call in trajectory:
        tool = _required_str(call, "name")
        arguments = call.get("arguments")
        expected_arguments = required_arguments.get(tool)
        if not isinstance(arguments, dict) or not isinstance(expected_arguments, dict) or arguments != expected_arguments:
            raise ChecksetBuildError(f"Stateful call {tool!r} has incorrect required arguments.")
        if tool == inspect_tool:
            continue
        transition = _matching_transition(transitions, tool=tool, current=state.get("current"))
        state["current"] = transition["to"]
    return state


def score_trajectory(instance: JsonObject, trajectory: Sequence[JsonObject]) -> bool:
    accepted = instance.get("accepted_equivalent_trajectories")
    canonical = instance.get("canonical_final_state")
    if not isinstance(accepted, list) or not isinstance(canonical, dict) or list(trajectory) not in accepted:
        return False
    try:
        return simulate_trajectory(instance, trajectory) == canonical
    except ChecksetBuildError:
        return False


def _generate_instance(definition: JsonObject, *, ordinal: int, spare: bool) -> JsonObject:
    template = _required_str(definition, "name")
    slug = re.sub(r"[^a-z0-9]+", "-", template).strip("-")
    seed_material = hashlib.sha256(f"{SELECTION_SEED}:{template}:{ordinal}:{spare}".encode()).digest()
    rng = random.Random(int.from_bytes(seed_material[:8], "big"))
    states = _required_strings(definition, "states")
    transitions = _required_objects(definition, "transitions")
    primary_argument = _required_str(definition, "primary_id_argument")
    related_arguments = _required_strings(definition, "related_id_arguments")
    argument_names = {primary_argument, *related_arguments}
    for transition in transitions:
        argument_names.update(_required_strings(transition, "required"))
    values = {name: _argument_value(name, slug=slug, ordinal=ordinal, rng=rng) for name in sorted(argument_names)}
    required_arguments: JsonObject = {
        _required_str(transition, "tool"): {
            name: values[name] for name in _required_strings(transition, "required")
        }
        for transition in transitions
    }
    inspect_tool = f"inspect_{slug.replace('-', '_')}"
    required_arguments[inspect_tool] = {primary_argument: values[primary_argument]}
    calls: list[JsonValue] = [
        {"name": _required_str(transition, "tool"), "arguments": required_arguments[_required_str(transition, "tool")]}
        for transition in transitions
    ]
    inspect_call: JsonObject = {"name": inspect_tool, "arguments": required_arguments[inspect_tool]}
    attributes: JsonObject = {"nonce": rng.randrange(10000, 99999), "variant": ordinal % 4}
    item_id = f"stateful-{'spare-' if spare else ''}{slug}-{ordinal:03d}"
    transition_values: list[JsonValue] = [transition for transition in transitions]
    nodes: list[JsonValue] = [
        {"argument": name, "id": values[name]} for name in [primary_argument, *related_arguments]
    ]
    record: JsonObject = {
        "item_id": item_id,
        "template": template,
        "ordinal": ordinal,
        "spare": spare,
        "prompt": f"Move {values[primary_argument]} from {states[0]} to {states[-1]} using only the declared tools.",
        "initial_state": {"attributes": attributes, "current": states[0], "entity_id": values[primary_argument]},
        "entity_graph": {
            "nodes": nodes,
            "root": values[primary_argument],
        },
        "tool_schemas": _tool_schemas(transitions, inspect_tool=inspect_tool, required_arguments=required_arguments),
        "required_arguments": required_arguments,
        "transitions": transition_values,
        "inspect_tool": inspect_tool,
        "canonical_final_state": {"attributes": attributes, "current": states[-1], "entity_id": values[primary_argument]},
        "accepted_equivalent_trajectories": [calls, [inspect_call, *calls]],
    }
    record["content_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def _tool_schemas(
    transitions: list[JsonObject],
    *,
    inspect_tool: str,
    required_arguments: JsonObject,
) -> list[JsonValue]:
    names = [*(_required_str(transition, "tool") for transition in transitions), inspect_tool]
    schemas: list[JsonValue] = []
    for name in names:
        arguments = required_arguments[name]
        if not isinstance(arguments, dict):
            raise ChecksetBuildError("Stateful required arguments must be objects.")
        properties: JsonObject = {
            key: {"type": "integer" if isinstance(value, int) else "string"} for key, value in arguments.items()
        }
        schemas.append(
            {
                "name": name,
                "input_schema": {"additionalProperties": False, "properties": properties, "required": list(arguments), "type": "object"},
            }
        )
    return schemas


def _argument_value(name: str, *, slug: str, ordinal: int, rng: random.Random) -> JsonValue:
    if name.endswith("_id"):
        return f"{slug[:8]}-{name[:-3]}-{ordinal:03d}-{rng.randrange(100, 999)}"
    if name in {"quantity", "revision", "due_day", "start_day"}:
        return 1 + rng.randrange(1, 28)
    if name == "amount_cents":
        return 1000 + rng.randrange(100, 9000)
    return f"{name}-{ordinal:03d}-{rng.randrange(100, 999)}"


def _matching_transition(transitions: list[JsonValue], *, tool: str, current: JsonValue) -> JsonObject:
    for transition in transitions:
        if isinstance(transition, dict) and transition.get("tool") == tool and transition.get("from") == current:
            return transition
    raise ChecksetBuildError(f"Stateful call {tool!r} is invalid from state {current!r}.")


def _definitions(document: JsonObject) -> list[JsonObject]:
    if document.get("schema_version") != "localbench-stateful-templates-v1":
        raise ChecksetBuildError("Unsupported stateful template schema.")
    raw = document.get("templates")
    if not isinstance(raw, list) or not all(isinstance(value, dict) for value in raw):
        raise ChecksetBuildError("Stateful template source must contain object definitions.")
    return [value for value in raw if isinstance(value, dict)]


def _required_objects(row: JsonObject, key: str) -> list[JsonObject]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ChecksetBuildError(f"Stateful field {key!r} must be a list of objects.")
    return [item for item in value if isinstance(item, dict)]


def _required_strings(row: JsonObject, key: str) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ChecksetBuildError(f"Stateful field {key!r} must be a list of strings.")
    return [item for item in value if isinstance(item, str)]


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ChecksetBuildError(f"Stateful field {key!r} must be a non-empty string.")
    return value
