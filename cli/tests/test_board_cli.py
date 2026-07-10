from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_board_subcommand_defaults_to_live_v2_artifact() -> None:
    # Given: the localbench CLI parser.
    from localbench.cli import _parser
    from localbench.scoring.board_support import DEFAULT_OUT_V2

    parser = _parser()

    # When: the board subcommand is parsed without an explicit output path.
    args = parser.parse_args(["board"])

    # Then: a bare localbench board targets the live v2 board, not frozen v1.
    assert args.out == DEFAULT_OUT_V2


def test_board_subcommand_is_available_from_module_entrypoint() -> None:
    # Given: automation can call the localbench CLI through Python module execution.
    result = subprocess.run(
        [sys.executable, "-m", "localbench.cli", "board", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: the module entrypoint reaches the board parser instead of silently no-oping.
    assert result.returncode == 0
    assert "--no-check-parity" in result.stdout


def test_land_run_subcommand_parses_maintainer_inputs() -> None:
    from localbench.cli import _parser

    args = _parser().parse_args(
        [
            "land-run", "--run", "incoming", "--coding-verified", "verified.json",
            "--gguf", "model.gguf", "--verifier-public-key", "ab" * 32, "--dry-run",
        ],
    )

    assert args.command == "land-run"
    assert args.run == Path("incoming")
    assert args.coding_verified == Path("verified.json")
    assert args.gguf == Path("model.gguf")
    assert args.verifier_public_key == "ab" * 32
    assert args.dry_run is True
