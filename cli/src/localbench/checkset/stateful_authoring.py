from __future__ import annotations

import hashlib
import random
import re

from localbench.checkset.models import ChecksetBuildError, JsonObject, JsonValue
from localbench.checkset.select import SELECTION_SEED
from localbench.submissions.canon import canonical_json_bytes


def generate_instance(definition: JsonObject, *, ordinal: int, spare: bool) -> JsonObject:
    template = require_str(definition, "name")
    slug = re.sub(r"[^a-z0-9]+", "-", template).strip("-")
    seed_material = hashlib.sha256(f"{SELECTION_SEED}:{template}:{ordinal}:{spare}".encode()).digest()
    rng = random.Random(int.from_bytes(seed_material[:8], "big"))
    transitions = require_objects(definition, "transitions")
    path_variants = require_objects(definition, "path_variants")
    path_variant = path_variants[ordinal % len(path_variants)]
    path_tools = require_strings(path_variant, "tools")
    path_transitions = [_transition_for_tool(transitions, tool) for tool in path_tools]
    primary_argument = require_str(definition, "primary_id_argument")
    related_arguments = require_strings(definition, "related_id_arguments")
    features = require_strings(definition, "features")
    hidden_arguments = optional_strings(definition, "inspect_hidden_arguments")
    argument_names = {primary_argument, *related_arguments}
    for transition in transitions:
        argument_names.update(require_strings(transition, "required"))
    values = {name: _argument_value(name, slug=slug, ordinal=ordinal, rng=rng) for name in sorted(argument_names)}
    required_arguments: JsonObject = {
        require_str(transition, "tool"): {
            name: values[name] for name in require_strings(transition, "required")
        }
        for transition in transitions
    }
    inspect_tool = f"inspect_{slug.replace('-', '_')}"
    required_arguments[inspect_tool] = {primary_argument: values[primary_argument]}
    calls: list[JsonValue] = [
        {"name": tool, "arguments": required_arguments[tool]}
        for tool in path_tools
    ]
    inspect_call: JsonObject = {"name": inspect_tool, "arguments": required_arguments[inspect_tool]}
    inspect_required = "inspect-first" in features
    canonical_calls = [inspect_call, *calls] if inspect_required else calls
    equivalent_calls = [inspect_call, *canonical_calls]
    attributes: JsonObject = {"nonce": rng.randrange(10000, 99999), "variant": ordinal % 4}
    selector_key = require_str(path_variant, "selector_key")
    selector_value = require_str(path_variant, "selector_value")
    attributes[selector_key] = selector_value
    item_id = f"stateful-{'spare-' if spare else ''}{slug}-{ordinal:03d}"
    transition_values: list[JsonValue] = [transition for transition in transitions]
    nodes: list[JsonValue] = [
        {"argument": name, "id": values[name]} for name in [primary_argument, *related_arguments]
    ]
    initial_state, canonical_state = _states_for_instance(
        definition,
        attributes=attributes,
        primary_entity=values[primary_argument],
        related_values=values,
        first_transition=path_transitions[0],
        last_transition=path_transitions[-1],
    )
    canonical_values: list[JsonValue] = [call for call in canonical_calls]
    equivalent_values: list[JsonValue] = [call for call in equivalent_calls]
    accepted: list[JsonValue] = [canonical_values, equivalent_values]
    distractor_tools: list[JsonValue] = [
        require_str(transition, "tool")
        for transition in transitions
        if transition.get("kind") in {"trap", "distractor"}
    ]
    record: JsonObject = {
        "item_id": item_id,
        "template": template,
        "ordinal": ordinal,
        "spare": spare,
        "prompt": f"Bring {values[primary_argument]} to {_final_state_description(canonical_state)} using only the declared tools.",
        "initial_state": initial_state,
        "entity_graph": {
            "nodes": nodes,
            "root": values[primary_argument],
            "selector": {"key": selector_key, "value": selector_value},
        },
        "tool_schemas": _tool_schemas(transitions, inspect_tool=inspect_tool, required_arguments=required_arguments),
        "required_arguments": required_arguments,
        "transitions": transition_values,
        "inspect_tool": inspect_tool,
        "inspect_required": inspect_required,
        "inspect_output": {name: values[name] for name in hidden_arguments},
        "distractor_tools": distractor_tools,
        "canonical_final_state": canonical_state,
        "accepted_equivalent_trajectories": accepted,
        "turn_budget": {
            "answer_budget_tokens_per_turn": 512,
            "max_turns": max(len(canonical_calls), len(equivalent_calls)) + 1,
            "semantics": "one tool call per assistant turn; final answer consumes the last turn",
        },
    }
    record["content_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def topology_signature(definition: JsonObject) -> str:
    states = require_strings(definition, "states")
    state_indexes = {state: index for index, state in enumerate(states)}
    edges: list[str] = []
    for transition in require_objects(definition, "transitions"):
        source = require_str(transition, "from")
        target = require_str(transition, "to")
        entity = transition.get("entity")
        lane = entity if isinstance(entity, str) else "single"
        if source not in state_indexes or target not in state_indexes:
            raise ChecksetBuildError("Stateful transition references an undeclared state.")
        edges.append(f"{lane}:{state_indexes[source]}>{state_indexes[target]}")
    return f"{len(states)}|{','.join(sorted(edges))}"


def definitions(document: JsonObject) -> list[JsonObject]:
    if document.get("schema_version") != "localbench-stateful-templates-v1":
        raise ChecksetBuildError("Unsupported stateful template schema.")
    raw = document.get("templates")
    if not isinstance(raw, list) or not all(isinstance(value, dict) for value in raw):
        raise ChecksetBuildError("Stateful template source must contain object definitions.")
    return [value for value in raw if isinstance(value, dict)]


def require_objects(row: JsonObject, key: str) -> list[JsonObject]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ChecksetBuildError(f"Stateful field {key!r} must be a list of objects.")
    return [item for item in value if isinstance(item, dict)]


def require_strings(row: JsonObject, key: str) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ChecksetBuildError(f"Stateful field {key!r} must be a list of strings.")
    return [item for item in value if isinstance(item, str)]


def require_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ChecksetBuildError(f"Stateful field {key!r} must be a non-empty string.")
    return value


def optional_strings(row: JsonObject, key: str) -> list[str]:
    value = row.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ChecksetBuildError(f"Stateful field {key!r} must be a list of strings when present.")
    return [item for item in value if isinstance(item, str)]


def _tool_schemas(
    transitions: list[JsonObject],
    *,
    inspect_tool: str,
    required_arguments: JsonObject,
) -> list[JsonValue]:
    names = [*(require_str(transition, "tool") for transition in transitions), inspect_tool]
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


def _states_for_instance(
    definition: JsonObject,
    *,
    attributes: JsonObject,
    primary_entity: JsonValue,
    related_values: JsonObject,
    first_transition: JsonObject,
    last_transition: JsonObject,
) -> tuple[JsonObject, JsonObject]:
    multi = definition.get("multi_entity")
    if not isinstance(multi, dict):
        return (
            {"attributes": attributes, "current": first_transition["from"], "entity_id": primary_entity},
            {"attributes": attributes, "current": last_transition["to"], "entity_id": primary_entity},
        )
    secondary_argument = require_str(multi, "secondary_argument")
    secondary_entity = related_values[secondary_argument]
    initial: JsonObject = {
        "attributes": attributes,
        "entities": {
            "primary": {"current": require_str(multi, "primary_initial"), "entity_id": primary_entity},
            "secondary": {"current": require_str(multi, "secondary_initial"), "entity_id": secondary_entity},
        },
    }
    final: JsonObject = {
        "attributes": attributes,
        "entities": {
            "primary": {"current": require_str(multi, "primary_final"), "entity_id": primary_entity},
            "secondary": {"current": require_str(multi, "secondary_final"), "entity_id": secondary_entity},
        },
    }
    return initial, final


def _final_state_description(state: JsonObject) -> str:
    current = state.get("current")
    return current if isinstance(current, str) else "all declared target states"


def _transition_for_tool(transitions: list[JsonObject], tool: str) -> JsonObject:
    matches = [transition for transition in transitions if transition.get("tool") == tool]
    if len(matches) != 1:
        raise ChecksetBuildError(f"Stateful path tool {tool!r} must identify exactly one transition.")
    return matches[0]
