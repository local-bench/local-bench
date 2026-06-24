from __future__ import annotations

import getpass
import socket
from pathlib import Path

from board_fixtures import FROZEN_AT, object_value, read_json, run_record, sha256, source, write_inputs, write_run


def test_manifest_hash_matches_written_board_and_frozen_timestamp_is_reproducible(
    tmp_path: Path,
) -> None:
    # Given: stable inputs and a frozen timestamp.
    from localbench.scoring.board import write_board

    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    write_run(paths["runs"] / "fixture.json", run_record())
    first = tmp_path / "first" / "board_v1.json"
    second = tmp_path / "second" / "board_v1.json"

    # When: the board is written twice.
    first_result = write_board(
        runs_dir=paths["runs"],
        out=first,
        curation_path=paths["curation"],
        frozen_timestamp=FROZEN_AT,
        check_parity=False,
        bootstrap_iters=50,
    )
    second_result = write_board(
        runs_dir=paths["runs"],
        out=second,
        curation_path=paths["curation"],
        frozen_timestamp=FROZEN_AT,
        check_parity=False,
        bootstrap_iters=50,
    )

    # Then: the sidecar hash matches the exact bytes and repeats deterministically.
    first_manifest = object_value(read_json(first_result.manifest_path))
    second_manifest = object_value(read_json(second_result.manifest_path))
    assert first_manifest["board_sha256"] == sha256(first)
    assert second_manifest["board_sha256"] == sha256(second)
    assert first_manifest["board_sha256"] == second_manifest["board_sha256"]
    assert first.read_bytes() == second.read_bytes()


def test_board_artifact_contains_no_operator_identity(tmp_path: Path) -> None:
    # Given: sensitive run metadata that must not leak into the release board.
    from localbench.scoring.board import write_board

    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    run = run_record()
    run["output_path"] = r"C:\Users\operator\local-bench\cli\runs\fixture.json"
    object_value(object_value(run["manifest"])["endpoint"])["runtime_reported_model"] = "github.com/private/model"
    write_run(paths["runs"] / "fixture.json", run)
    out = tmp_path / "board" / "board_v1.json"

    # When: the board is written.
    write_board(
        runs_dir=paths["runs"],
        out=out,
        curation_path=paths["curation"],
        frozen_timestamp=FROZEN_AT,
        check_parity=False,
        bootstrap_iters=50,
    )

    # Then: local paths, host identity, and git remotes are absent.
    text = out.read_text(encoding="utf-8")
    forbidden = [
        r"C:\\Users\\",
        "/home/",
        "/Users/",
        getpass.getuser(),
        socket.gethostname(),
        "github.com",
        "gitlab.com",
    ]
    assert not [value for value in forbidden if value and value in text]
