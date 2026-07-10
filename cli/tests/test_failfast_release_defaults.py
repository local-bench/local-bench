from __future__ import annotations

from pathlib import Path

import localbench.cli as cli_mod
import pytest
from localbench.serving.options import ServeBenchOptions


def test_agentic_personal_path_defaults_are_absent_from_source_and_help(
    capsys,
) -> None:
    # Given the installed CLI source and its public bench help.
    source_root = Path(__file__).resolve().parents[1] / "src" / "localbench"
    repo_root = Path(__file__).resolve().parents[2]

    # When scanning source and rendering help.
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in source_root.rglob("*.py")
    )
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            repo_root / "README.md",
            repo_root / "cli" / "README.md",
            *(repo_root / "docs").rglob("*.md"),
        ]
    )
    with pytest.raises(SystemExit) as help_exit:
        cli_mod.main(["bench", "--help"])
    help_text = capsys.readouterr().out

    # Then no maintainer-specific path remains as a default or help/documentation copy.
    assert help_exit.value.code == 0
    assert "/home/michael" not in source
    assert "appworld-harness" not in source
    assert "/home/michael" not in docs
    assert "appworld-harness" not in docs
    assert "/home/michael" not in help_text
    assert "appworld-harness" not in help_text
    assert ServeBenchOptions.__dataclass_fields__["wsl_venv_python"].default is None
    assert ServeBenchOptions.__dataclass_fields__["appworld_root"].default is None
