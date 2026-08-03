from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from localbench.checkset.models import JsonObject, JsonValue, ModuleRecord
from localbench.checkset.stateful import (
    TEMPLATE_NAMES,
    build_stateful,
    score_trajectory,
    simulate_trajectory,
)


@pytest.fixture(scope="module")
def authored_stateful() -> tuple[ModuleRecord, JsonObject]:
    repo_root = Path(__file__).resolve().parents[2]
    module, metadata = build_stateful(repo_root)
    return module, metadata


def _objects(value: JsonValue) -> list[JsonObject]:
    assert isinstance(value, list)
    rows: list[JsonObject] = []
    for item in value:
        assert isinstance(item, dict)
        rows.append(item)
    return rows


def _trajectories(value: JsonValue) -> list[list[JsonObject]]:
    assert isinstance(value, list)
    paths: list[list[JsonObject]] = []
    for item in value:
        paths.append(_objects(item))
    return paths


def _string(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_each_stateful_template_accepts_canonical_and_rejects_wrong_trajectory(
    authored_stateful: tuple[ModuleRecord, JsonObject],
    template_name: str,
) -> None:
    _, metadata = authored_stateful
    instances = _objects(metadata["instances"])
    instance = next(record for record in instances if record.get("template") == template_name)
    accepted = _trajectories(instance["accepted_equivalent_trajectories"])
    trajectory = accepted[0]

    assert simulate_trajectory(instance, trajectory) == instance["canonical_final_state"]
    assert score_trajectory(instance, trajectory) is True

    equivalent = accepted[1]
    assert score_trajectory(instance, equivalent) is True

    distractor_tools = instance["distractor_tools"]
    required_arguments = instance["required_arguments"]
    assert isinstance(distractor_tools, list) and len(distractor_tools) >= 2
    assert isinstance(required_arguments, dict)
    trap_tool = distractor_tools[0]
    assert isinstance(trap_tool, str)
    trap_arguments = required_arguments[trap_tool]
    assert isinstance(trap_arguments, dict)
    wrong: list[JsonObject] = []
    if instance["inspect_required"] is True:
        wrong.append(deepcopy(trajectory[0]))
    wrong.append({"name": trap_tool, "arguments": deepcopy(trap_arguments)})
    assert simulate_trajectory(instance, wrong) != instance["canonical_final_state"]
    assert score_trajectory(instance, wrong) is False


def test_stateful_generation_is_deterministic_and_exactly_twelve_by_four_plus_six() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    first = build_stateful(repo_root)
    second = build_stateful(repo_root)

    assert first == second
    module, metadata = first
    assert module.scored == 48
    assert len(module.items) == 48
    assert metadata["templates"] == list(TEMPLATE_NAMES)
    instances = _objects(metadata["instances"])
    spares = _objects(metadata["spares_ordered"])
    cluster_map = metadata["cluster_map"]
    assert len(instances) == 48
    assert len(spares) == 6
    assert isinstance(cluster_map, dict)
    cluster_names = [_string(value) for value in cluster_map.values()]
    assert len(set(cluster_names)) == 12


def test_stateful_instances_change_seeded_state_entity_graph_and_required_arguments() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _, metadata = build_stateful(repo_root)
    instances = _objects(metadata["instances"])
    booking = [record for record in instances if record["template"] == "booking ledger"]

    assert len({str(record["initial_state"]) for record in booking}) == 4
    assert len({str(record["entity_graph"]) for record in booking}) == 4
    assert len({str(record["required_arguments"]) for record in booking}) == 4


def test_stateful_templates_cover_distinct_locked_topologies_and_depths(
    authored_stateful: tuple[ModuleRecord, JsonObject],
) -> None:
    _, metadata = authored_stateful
    definitions = _objects(metadata["template_definitions"])
    instances = _objects(metadata["instances"])

    signatures = [_string(definition["topology_signature"]) for definition in definitions]
    assert len(set(signatures)) == 12

    feature_counts: dict[str, int] = {}
    for definition in definitions:
        features = definition["features"]
        assert isinstance(features, list)
        for feature in features:
            assert isinstance(feature, str)
            feature_counts[feature] = feature_counts.get(feature, 0) + 1

    assert feature_counts["linear-with-guard"] >= 3
    assert feature_counts["branching"] >= 3
    assert feature_counts["inspect-first"] >= 2
    assert feature_counts["trap-transition"] >= 2
    assert feature_counts["cyclic-with-guard"] == 1
    assert feature_counts["multi-entity"] == 1

    canonical_depths: list[int] = []
    for instance in instances:
        accepted = _trajectories(instance["accepted_equivalent_trajectories"])
        canonical_depths.append(len(accepted[0]))
    assert all(3 <= depth <= 6 for depth in canonical_depths)
    assert sum(depth >= 5 for depth in canonical_depths) >= 16


def test_stateful_branch_paths_vary_and_turn_budgets_are_explicit(
    authored_stateful: tuple[ModuleRecord, JsonObject],
) -> None:
    _, metadata = authored_stateful
    definitions = _objects(metadata["template_definitions"])
    instances = _objects(metadata["instances"])
    branching: set[str] = set()
    for definition in definitions:
        features = definition["features"]
        assert isinstance(features, list)
        if "branching" in features:
            branching.add(_string(definition["name"]))

    for template_name in branching:
        paths = {
            tuple(
                _string(call["name"])
                for call in _trajectories(record["accepted_equivalent_trajectories"])[0]
            )
            for record in instances
            if record["template"] == template_name
        }
        assert len(paths) >= 2

    for record in instances:
        accepted = _trajectories(record["accepted_equivalent_trajectories"])
        turn_budget = record["turn_budget"]
        assert turn_budget == {
            "answer_budget_tokens_per_turn": 512,
            "max_turns": max(len(path) for path in accepted) + 1,
            "semantics": "one tool call per assistant turn; final answer consumes the last turn",
        }


def test_inspect_first_templates_hide_required_values_until_inspection(
    authored_stateful: tuple[ModuleRecord, JsonObject],
) -> None:
    _, metadata = authored_stateful
    instances = _objects(metadata["instances"])
    inspect_first = [record for record in instances if record.get("inspect_required") is True]
    assert len(inspect_first) >= 8

    for record in inspect_first:
        accepted = _trajectories(record["accepted_equivalent_trajectories"])
        inspect_output = record["inspect_output"]
        assert isinstance(inspect_output, dict) and inspect_output
        assert accepted[0][0]["name"] == record["inspect_tool"]
        prompt = _string(record["prompt"])
        assert all(str(value) not in prompt for value in inspect_output.values())
        assert score_trajectory(record, accepted[0][1:]) is False
