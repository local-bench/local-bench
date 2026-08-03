from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from localbench.checkset.models import ChecksetBuildError, JsonObject, JsonValue


def simulate_trajectory(instance: JsonObject, trajectory: Sequence[JsonObject]) -> JsonObject:
    initial = instance.get("initial_state")
    required_arguments = instance.get("required_arguments")
    transitions = instance.get("transitions")
    if not isinstance(initial, dict) or not isinstance(required_arguments, dict) or not isinstance(transitions, list):
        raise ChecksetBuildError("Stateful instance is missing simulator inputs.")
    state = deepcopy(initial)
    inspect_tool = _required_str(instance, "inspect_tool")
    inspect_required = instance.get("inspect_required") is True
    inspected = False
    for call in trajectory:
        tool = _required_str(call, "name")
        arguments = call.get("arguments")
        expected_arguments = required_arguments.get(tool)
        if not isinstance(arguments, dict) or not isinstance(expected_arguments, dict) or arguments != expected_arguments:
            raise ChecksetBuildError(f"Stateful call {tool!r} has incorrect required arguments.")
        if tool == inspect_tool:
            inspected = True
            continue
        if inspect_required and not inspected:
            raise ChecksetBuildError(f"Stateful call {tool!r} requires inspection first.")
        transition = _matching_transition(transitions, tool=tool, state=state)
        _apply_transition(state, transition)
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


def _matching_transition(transitions: list[JsonValue], *, tool: str, state: JsonObject) -> JsonObject:
    for transition in transitions:
        if not isinstance(transition, dict) or transition.get("tool") != tool:
            continue
        entity = transition.get("entity")
        entity_name = entity if isinstance(entity, str) else None
        if transition.get("from") != _entity_current(state, entity_name):
            continue
        guard = transition.get("guard")
        if isinstance(guard, dict):
            guard_entity = _required_str(guard, "entity")
            if _entity_current(state, guard_entity) != _required_str(guard, "state"):
                raise ChecksetBuildError(f"Stateful call {tool!r} failed its cross-entity guard.")
        return transition
    raise ChecksetBuildError(f"Stateful call {tool!r} is invalid from the current state.")


def _apply_transition(state: JsonObject, transition: JsonObject) -> None:
    entity = transition.get("entity")
    if not isinstance(entity, str):
        state["current"] = transition["to"]
        return
    entities = state.get("entities")
    if not isinstance(entities, dict):
        raise ChecksetBuildError("Multi-entity state is missing entity records.")
    entity_state = entities.get(entity)
    if not isinstance(entity_state, dict):
        raise ChecksetBuildError(f"Multi-entity state is missing {entity!r}.")
    entity_state["current"] = transition["to"]


def _entity_current(state: JsonObject, entity: str | None) -> JsonValue:
    if entity is None:
        return state.get("current")
    entities = state.get("entities")
    entity_state = entities.get(entity) if isinstance(entities, dict) else None
    return entity_state.get("current") if isinstance(entity_state, dict) else None


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ChecksetBuildError(f"Stateful field {key!r} must be a non-empty string.")
    return value
