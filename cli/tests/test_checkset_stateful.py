from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from localbench.checkset.models import JsonObject, ModuleRecord
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


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_each_stateful_template_accepts_canonical_and_rejects_wrong_trajectory(
    authored_stateful: tuple[ModuleRecord, JsonObject],
    template_name: str,
) -> None:
    _, metadata = authored_stateful
    instances = metadata["instances"]
    assert isinstance(instances, list)
    instance = next(
        record for record in instances if isinstance(record, dict) and record.get("template") == template_name
    )
    accepted = instance["accepted_equivalent_trajectories"]
    assert isinstance(accepted, list) and isinstance(accepted[0], list)
    assert all(isinstance(call, dict) for call in accepted[0])
    trajectory = [call for call in accepted[0] if isinstance(call, dict)]

    assert simulate_trajectory(instance, trajectory) == instance["canonical_final_state"]
    assert score_trajectory(instance, trajectory) is True

    wrong = deepcopy(trajectory)
    assert isinstance(wrong[0], dict)
    arguments = wrong[0]["arguments"]
    assert isinstance(arguments, dict)
    first_argument = next(iter(arguments))
    arguments[first_argument] = "wrong-value"
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
    instances = metadata["instances"]
    spares = metadata["spares_ordered"]
    cluster_map = metadata["cluster_map"]
    assert isinstance(instances, list) and len(instances) == 48
    assert isinstance(spares, list) and len(spares) == 6
    assert isinstance(cluster_map, dict) and len(set(cluster_map.values())) == 12


def test_stateful_instances_change_seeded_state_entity_graph_and_required_arguments() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _, metadata = build_stateful(repo_root)
    instances = metadata["instances"]
    assert isinstance(instances, list)
    booking = [record for record in instances if isinstance(record, dict) and record["template"] == "booking ledger"]

    assert len({str(record["initial_state"]) for record in booking}) == 4
    assert len({str(record["entity_graph"]) for record in booking}) == 4
    assert len({str(record["required_arguments"]) for record in booking}) == 4
