from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from localbench.checkset.input_runs import read_json
from localbench.checkset.stateful_authoring import (
    definitions,
    generate_instance,
    require_objects,
    require_str,
    require_strings,
    topology_signature,
)
from localbench.checkset.stateful_runtime import (
    score_trajectory as _score_trajectory,
    simulate_trajectory as _simulate_trajectory,
)
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.checkset.select import SELECTION_SEED

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
    template_definitions = definitions(read_json(source_path))
    if tuple(require_str(definition, "name") for definition in template_definitions) != TEMPLATE_NAMES:
        raise ChecksetBuildError("Stateful template names or ordering differ from the locked twelve-template set.")
    instances = [
        generate_instance(definition, ordinal=ordinal, spare=False)
        for definition in template_definitions
        for ordinal in range(4)
    ]
    spares = [
        generate_instance(template_definitions[index], ordinal=100 + index, spare=True)
        for index in range(6)
    ]
    enriched_definitions = [
        {**definition, "topology_signature": topology_signature(definition)}
        for definition in template_definitions
    ]
    _validate_authored_content(enriched_definitions, instances)
    definition_values: list[JsonValue] = [definition for definition in enriched_definitions]
    instance_values: list[JsonValue] = [record for record in instances]
    spare_values: list[JsonValue] = [record for record in spares]
    module = ModuleRecord(
        name="tools-stateful",
        scored=48,
        items=tuple(
            ItemRecord(
                require_str(record, "item_id"),
                require_str(record, "content_sha256"),
                "stateful",
            )
            for record in instances
        ),
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
            require_str(record, "item_id"): require_str(record, "template") for record in instances
        },
        "replacement_policy": "predeclared-mechanical-validity-defect-only",
    }
    return module, metadata


def simulate_trajectory(instance: JsonObject, trajectory: Sequence[JsonObject]) -> JsonObject:
    return _simulate_trajectory(instance, trajectory)


def score_trajectory(instance: JsonObject, trajectory: Sequence[JsonObject]) -> bool:
    return _score_trajectory(instance, trajectory)


def _validate_authored_content(definitions: list[JsonObject], instances: list[JsonObject]) -> None:
    signatures = [require_str(definition, "topology_signature") for definition in definitions]
    if len(set(signatures)) != len(TEMPLATE_NAMES):
        raise ChecksetBuildError("Stateful templates must have twelve distinct topology signatures.")
    feature_counts = Counter(
        feature
        for definition in definitions
        for feature in require_strings(definition, "features")
    )
    minima = {"linear-with-guard": 3, "branching": 3, "inspect-first": 2, "trap-transition": 2}
    if any(feature_counts[name] < minimum for name, minimum in minima.items()):
        raise ChecksetBuildError("Stateful topology mix does not meet the locked feature minima.")
    if feature_counts["cyclic-with-guard"] != 1 or feature_counts["multi-entity"] != 1:
        raise ChecksetBuildError("Stateful topology mix must contain exactly one cycle and one multi-entity machine.")
    for definition in definitions:
        features = require_strings(definition, "features")
        if "linear-with-guard" in features and len(require_strings(definition, "states")) < 4:
            raise ChecksetBuildError("Linear-with-guard templates require at least four states.")
        if "branching" in features and len(require_objects(definition, "path_variants")) < 2:
            raise ChecksetBuildError("Branching templates require at least two seeded paths.")
    canonical_depths: list[int] = []
    deep_templates: set[str] = set()
    for instance in instances:
        accepted = instance.get("accepted_equivalent_trajectories")
        distractors = instance.get("distractor_tools")
        if not isinstance(accepted, list) or not accepted or not isinstance(accepted[0], list):
            raise ChecksetBuildError("Stateful instance is missing accepted trajectories.")
        depth = len(accepted[0])
        canonical_depths.append(depth)
        if depth >= 5:
            deep_templates.add(require_str(instance, "template"))
        if not isinstance(distractors, list) or len(distractors) < 2:
            raise ChecksetBuildError("Every stateful instance requires two state-changing distractors.")
    if not all(3 <= depth <= 6 for depth in canonical_depths) or len(deep_templates) < 4:
        raise ChecksetBuildError("Stateful canonical trajectories must span three to six calls with four deep templates.")
