from __future__ import annotations

from pathlib import Path

from board_fixtures import FROZEN_AT, objects_value, run_record, source, string_value, write_inputs, write_run


def test_quant_provenance_surfaces_when_curated_and_omits_when_absent(tmp_path: Path) -> None:
    # Given: one curated source has publisher/repo provenance and one source has none.
    from localbench.scoring.board import build_board

    curated = source(
        "Provenance Model",
        "provenance.json",
        family="Provenance",
        model_id="provenance/model",
    )
    curated["publisher"] = "unsloth"
    curated["gguf_repo"] = "unsloth/gemma-4-12b-it-GGUF"
    sources = [
        curated,
        source(
            "Plain Model",
            "plain.json",
            family="Plain",
            model_id="plain/model",
        ),
    ]
    paths = write_inputs(tmp_path, sources)
    write_run(paths["runs"] / "provenance.json", run_record())
    write_run(paths["runs"] / "plain.json", run_record())

    # When: the board is built through the public scorer surface.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: present provenance is surfaced and absent provenance is omitted, not nulled.
    models = {string_value(model["model_label"]): model for model in objects_value(board["models"])}
    provenance = models["Provenance Model"]
    provenance_system = objects_value(provenance["systems"])[0]
    assert provenance["publisher"] == "unsloth"
    assert provenance["gguf_repo"] == "unsloth/gemma-4-12b-it-GGUF"
    assert provenance_system["publisher"] == "unsloth"
    assert provenance_system["gguf_repo"] == "unsloth/gemma-4-12b-it-GGUF"

    plain = models["Plain Model"]
    plain_system = objects_value(plain["systems"])[0]
    assert "publisher" not in plain
    assert "gguf_repo" not in plain
    assert "publisher" not in plain_system
    assert "gguf_repo" not in plain_system
