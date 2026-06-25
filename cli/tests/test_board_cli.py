from __future__ import annotations


def test_board_subcommand_defaults_to_live_v2_artifact() -> None:
    # Given: the localbench CLI parser.
    from localbench.cli import _parser
    from localbench.scoring.board_support import DEFAULT_OUT_V2

    parser = _parser()

    # When: the board subcommand is parsed without an explicit output path.
    args = parser.parse_args(["board"])

    # Then: a bare localbench board targets the live v2 board, not frozen v1.
    assert args.out == DEFAULT_OUT_V2
