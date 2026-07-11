from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.canon import canonical_json_bytes, sha256_bytes
from localbench.submissions.foundation import (
    migrate_accepted_result_projection_v1,
    validate_accepted_result_projection,
)
from localbench.submissions.projection import projection_object_sha256
from localbench.submissions.validate import SubmissionValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_golden_v1_to_v2_migration_is_exact_and_valid() -> None:
    migrated = migrate_accepted_result_projection_v1(_fixture("accepted_projection_v1_golden.json"))
    assert migrated == _fixture("accepted_projection_v2_golden.json")
    validate_accepted_result_projection(migrated)


def test_object_hash_and_semantic_hash_are_explicitly_distinct_domains() -> None:
    projection = _fixture("accepted_projection_v2_golden.json")
    object_hash = projection_object_sha256(projection)
    assert object_hash == sha256_bytes(canonical_json_bytes(projection))
    assert object_hash != projection["artifact_hashes"]["projection_sha256"]  # type: ignore[index]


@pytest.mark.parametrize("mutation", ["extra", "nan", "digest", "suite_pair"])
def test_v2_schema_fails_closed_on_adversarial_contract_mutations(mutation: str) -> None:
    projection = _fixture("accepted_projection_v2_golden.json")
    if mutation == "extra":
        projection["model"]["catalog_slug"] = "protected"  # type: ignore[index]
    elif mutation == "nan":
        projection["scores"]["partial_composite"] = float("nan")  # type: ignore[index]
    elif mutation == "digest":
        projection["artifact_hashes"]["bundle_sha256"] = "BAD"  # type: ignore[index]
    else:
        projection["suite_manifest_sha256"] = "0" * 64
    with pytest.raises(SubmissionValidationError, match="accepted projection invalid"):
        validate_accepted_result_projection(projection)
