from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from localbench.checkset.build import build_t2_scaffold, emit_manifest
from localbench.checkset.gates import build_sanity_gates
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    ModuleRecord,
)
from localbench.checkset.stateful import build_stateful


def _locked_modules() -> tuple[ModuleRecord, ...]:
    counts = {
        "knowledge": 198,
        "coding": 96,
        "instruction": 120,
        "math": 60,
        "tools-single": 54,
        "tools-stateful": 48,
        "sanity-gates": 18,
    }
    modules: list[ModuleRecord] = []
    repo_root = Path(__file__).resolve().parents[2]
    authored_stateful, _ = build_stateful(repo_root)
    authored_gates, _ = build_sanity_gates(repo_root)
    for name, count in counts.items():
        items = tuple(ItemRecord(f"{name}-{index:03d}", f"{index:064x}") for index in range(count))
        if name == "math":
            items = items[:30] + tuple(
                ItemRecord(f"olymmath-en-easy-{index:05d}", f"{index + 1000:064x}")
                for index in range(30)
            )
        if name == "tools-stateful":
            modules.append(authored_stateful)
            continue
        if name == "sanity-gates":
            modules.append(authored_gates)
            continue
        modules.append(
            ModuleRecord(
            name=name,
            scored=count,
            items=items,
            source={"dataset": f"test/{name}", "revision": "d" * 64, "split": "test"},
            scorer={"name": f"test-{name}", "version": "test-v1"},
            selection={"algorithm": "test-v1", "inputs_sha256": "e" * 64, "seed": 20260802},
        )
        )
    return tuple(modules)


def _stateful_metadata() -> JsonObject:
    _, metadata = build_stateful(Path(__file__).resolve().parents[2])
    return metadata


def _sanity_gates_metadata() -> JsonObject:
    _, metadata = build_sanity_gates(Path(__file__).resolve().parents[2])
    return metadata


def _source_metadata() -> JsonObject:
    return {
        "gpqa": {
            "repository": "Idavidrein/gpqa",
            "config": "gpqa_diamond",
            "revision": "633f5ee89ab8ad4522a9f850766b73f62147ffdd",
        },
        "gpqa_canary_strip_log": [
            {
                "field": "Canary String",
                "item_id": f"knowledge-{index:03d}",
                "removed_sha256": "b" * 64,
            }
            for index in range(198)
        ],
        "math_aime": {
            "repository": "RUC-AIBOX/OlymMATH",
            "config": "en-easy",
            "revision": "2c6532ea2cf929ac1c421532af5951553eaee727",
            "selected": [
                {
                    "content_sha256": f"{index + 1000:064x}",
                    "subject": f"subject-{index % 3}",
                    "upstream_index": index,
                }
                for index in range(30)
            ],
        },
    }


def _pool_exclusions() -> tuple[JsonObject, ...]:
    return tuple(
        {"item_id": item_id, "module": "coding", "reason": "sandbox-unscoreable"}
        for item_id in ("bcbh-006", "bcbh-007", "bcbh-014", "bcbh-035", "bcbh-074", "bcbh-096", "bcbh-104")
    )


def _emit(output: Path, *, modules: tuple[ModuleRecord, ...] | None = None, stateful: JsonObject | None = None, source_metadata: JsonObject | None = None) -> JsonObject:
    return emit_manifest(
        output,
        modules=modules or _locked_modules(),
        stateful=stateful or _stateful_metadata(),
        sanity_gates=_sanity_gates_metadata(),
        source_metadata=source_metadata or _source_metadata(),
        pool_exclusions=_pool_exclusions(),
    )


def test_scaffold_records_t3_dependency_without_claiming_authored_totals(tmp_path: Path) -> None:
    # Given no T3 authored-content file.
    output = tmp_path / "check-set-v1.t2-draft.json"

    # When the T2 scaffold is built from a minimal injected selection set.
    module = ModuleRecord(name="coding", scored=1, items=(ItemRecord("x", "b" * 64),))
    result = build_t2_scaffold(output, modules=(module,), knowledge_status="pending_fetch", knowledge_error="gated")

    # Then the artifact is explicitly incomplete and byte-stable on a second write.
    first_bytes = output.read_bytes()
    build_t2_scaffold(output, modules=(module,), knowledge_status="pending_fetch", knowledge_error="gated")
    assert output.read_bytes() == first_bytes
    assert result["draft"] is True
    assert result["status"] == "pending_dependencies"
    assert result["pending_dependencies"] == ["tools-stateful", "sanity-gates"]


def test_scaffold_pins_the_fetched_wikitext_corpus_digest(tmp_path: Path) -> None:
    # Given the repository's committed Wikitext-2 test provenance.
    repo_root = Path(__file__).resolve().parents[2]
    corpus_config = json.loads((repo_root / "checkset" / "kld-corpus.json").read_text(encoding="utf-8"))

    # When a scaffold is emitted.
    document = build_t2_scaffold(
        tmp_path / "draft.json", modules=(), knowledge_status="pending_fetch", knowledge_error="offline"
    )

    # Then the KLD policy embeds the exact fetched source and materialized-corpus digests.
    assert document["kld"]["corpus"] == corpus_config


def test_final_emit_rejects_non_locked_authored_totals(tmp_path: Path) -> None:
    # Given an incomplete module list.
    modules = (ModuleRecord(name="knowledge", scored=198, items=()),)

    # When final manifest emission is attempted, then it fails loudly.
    with pytest.raises(ValueError, match=r"576 scored \+ 18 gates \+ 6 spares = 600"):
        emit_manifest(
            tmp_path / "manifest.json",
            modules=modules,
            stateful={},
            sanity_gates={},
            source_metadata={},
        )


def test_final_emit_rejects_declared_counts_without_authored_items(tmp_path: Path) -> None:
    # Given every locked counter but no authored item records.
    modules = tuple(ModuleRecord(name=module.name, scored=module.scored, items=()) for module in _locked_modules())

    # When final emission is attempted, then item-list validation rejects the nominal 600.
    with pytest.raises(ValueError, match="module item list"):
        emit_manifest(
            tmp_path / "manifest.json",
            modules=modules,
            stateful=_stateful_metadata(),
            sanity_gates=_sanity_gates_metadata(),
            source_metadata={},
        )


def test_final_emit_writes_canonical_sidecar_and_is_byte_identical(tmp_path: Path) -> None:
    # Given real locked module items, T3 stateful metadata, and upstream provenance.
    modules = _locked_modules()
    stateful = _stateful_metadata()
    source_metadata = _source_metadata()
    output = tmp_path / "manifest.json"

    # When the final draft is emitted twice.
    _emit(output, modules=modules, stateful=stateful, source_metadata=source_metadata)
    first_bytes = output.read_bytes()
    _emit(output, modules=modules, stateful=stateful, source_metadata=source_metadata)

    # Then canonical bytes and their sha256 sidecar are stable.
    assert output.read_bytes() == first_bytes
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["draft"] is True
    assert document["source_metadata"] == source_metadata
    assert (tmp_path / "manifest.json.sha256").read_text(encoding="ascii").endswith("  manifest.json\n")


@pytest.mark.parametrize("case", ("unexpected-top-level", "unexpected-gpqa-field"))
def test_final_emit_rejects_unallowlisted_source_metadata(tmp_path: Path, case: str) -> None:
    # Given otherwise valid source metadata containing an unallowlisted plaintext field.
    metadata = deepcopy(_source_metadata())
    target = metadata if case == "unexpected-top-level" else metadata["gpqa"]
    assert isinstance(target, dict)
    target["question"] = "hidden plaintext"

    # When final emission validates the source boundary, then it rejects the extra field.
    with pytest.raises(ChecksetBuildError, match="source metadata"):
        _emit(tmp_path / "manifest.json", source_metadata=metadata)


@pytest.mark.parametrize(
    "case",
    ("wrong-gpqa-revision", "nonhex-module-sha", "nonhex-stateful-sha", "nonhex-canary-sha"),
)
def test_final_emit_rejects_invalid_sha_or_provenance(tmp_path: Path, case: str) -> None:
    # Given a final-manifest boundary with one malformed digest or source pin.
    modules = _locked_modules()
    stateful = _stateful_metadata()
    metadata = _source_metadata()
    if case == "wrong-gpqa-revision":
        gpqa = metadata["gpqa"]
        assert isinstance(gpqa, dict)
        gpqa["revision"] = "0" * 40
    elif case == "nonhex-module-sha":
        first = modules[0]
        modules = (replace(first, items=(ItemRecord(first.items[0].item_id, "g" * 64), *first.items[1:])), *modules[1:])
    elif case == "nonhex-stateful-sha":
        instances = stateful["instances"]
        assert isinstance(instances, list) and isinstance(instances[0], dict)
        instances[0]["content_sha256"] = "g" * 64
    else:
        log = metadata["gpqa_canary_strip_log"]
        assert isinstance(log, list) and isinstance(log[0], dict)
        log[0]["removed_sha256"] = "g" * 64

    # When final emission runs, then it rejects the malformed boundary value.
    with pytest.raises(ChecksetBuildError):
        _emit(tmp_path / "manifest.json", modules=modules, stateful=stateful, source_metadata=metadata)


def test_final_emit_rejects_math_provenance_disconnected_from_module_items(tmp_path: Path) -> None:
    # Given a syntactically valid AIME selection log whose content hash does not match the published module item.
    metadata = _source_metadata()
    math_aime = metadata["math_aime"]
    assert isinstance(math_aime, dict)
    selected = math_aime["selected"]
    assert isinstance(selected, list) and isinstance(selected[0], dict)
    selected[0]["content_sha256"] = "f" * 64

    # When final emission validates provenance, then it rejects the disconnected attestation.
    with pytest.raises(ChecksetBuildError, match="math AIME-band selections must match"):
        _emit(tmp_path / "manifest.json", source_metadata=metadata)


def test_final_manifest_carries_required_module_source_scorer_selection_contracts(tmp_path: Path) -> None:
    # Given a complete locked manifest input.
    document = _emit(tmp_path / "manifest.json")

    # When module records are inspected, then every inherited rev-2 contract is present.
    for module in document["modules"]:
        assert isinstance(module, dict)
        assert set(module) == {"items", "name", "scored", "scorer", "selection", "source", "status"}
        assert set(module["source"]) == {"dataset", "revision", "split"}
        assert set(module["scorer"]) == {"name", "version"}
        assert set(module["selection"]) == {"algorithm", "inputs_sha256", "seed"}


def test_final_manifest_carries_required_execution_and_statistics_contracts(tmp_path: Path) -> None:
    # Given a complete locked manifest input, when final emission succeeds.
    document = _emit(tmp_path / "manifest.json")

    # Then execution and statistics expose the locked machine-readable policy.
    assert document["execution"]["edition"] == "LCE-1"
    assert document["execution"]["llama_cpp_build"] == "b10076"
    assert document["execution"]["think_budget_tokens"] == 4096
    assert document["statistics"]["margins_pp"] == {
        "coding": 5.0,
        "instruction": 4.0,
        "knowledge": 3.0,
        "math": 6.0,
        "tools": 4.0,
    }
    assert document["statistics"]["bootstrap"]["resamples"] == 100000
    assert document["statistics"]["bootstrap"]["seed"] == 20260802
    assert document["statistics"]["practical_margin_pp"] == 2.0


@pytest.mark.parametrize("case", ("eleven-templates", "five-plus-three-cluster", "orphan-cluster-entry"))
def test_final_emit_rejects_stateful_layout_outside_twelve_by_four(tmp_path: Path, case: str) -> None:
    # Given 48 authored records with a malformed template or cluster layout.
    stateful = _stateful_metadata()
    templates = stateful["templates"]
    cluster_map = stateful["cluster_map"]
    assert isinstance(templates, list) and isinstance(cluster_map, dict)
    if case == "eleven-templates":
        templates.pop()
    elif case == "five-plus-three-cluster":
        cluster_map["tools-stateful-000"] = "template-01"
    else:
        cluster_map["orphan"] = "template-00"

    # When final emission validates stateful authorship, then it rejects the layout.
    with pytest.raises(ChecksetBuildError, match="stateful"):
        _emit(tmp_path / "manifest.json", stateful=stateful)
