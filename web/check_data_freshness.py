from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from build_data_support import ROOT

GENERATED_INDEX: Final = ROOT / "web" / "public" / "data" / "index.json"
WATCHED_PATHS: Final = (
    ROOT / "web" / "data_sources.json",
    ROOT / "cli" / "runs",
    ROOT / "cli" / "runs" / "board",
)


class FreshnessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StaleInput:
    path: Path
    input_mtime_ns: int
    generated_mtime_ns: int


def stale_inputs(
    *,
    generated: Path = GENERATED_INDEX,
    watched: Sequence[Path] = WATCHED_PATHS,
) -> tuple[StaleInput, ...]:
    generated_path = generated.resolve()
    if not generated_path.is_file():
        raise FreshnessError(f"generated index is missing: {generated_path}")
    generated_mtime_ns = generated_path.stat().st_mtime_ns
    seen: set[Path] = set()
    stale: list[StaleInput] = []
    for input_path in _input_files(watched):
        resolved = input_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        input_mtime_ns = resolved.stat().st_mtime_ns
        if input_mtime_ns > generated_mtime_ns:
            stale.append(
                StaleInput(
                    path=resolved,
                    input_mtime_ns=input_mtime_ns,
                    generated_mtime_ns=generated_mtime_ns,
                ),
            )
    return tuple(sorted(stale, key=lambda item: item.path.as_posix()))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args in (["--help"], ["-h"]):
        print("usage: python web/check_data_freshness.py")
        return 0
    if args:
        print(f"check_data_freshness: unknown argument {args[0]}", file=sys.stderr)
        return 2
    try:
        stale = stale_inputs()
    except FreshnessError as exc:
        print(f"check_data_freshness: {exc}", file=sys.stderr)
        return 2
    if stale:
        print("check_data_freshness: generated site data is stale; run python web/build_data.py", file=sys.stderr)
        for item in stale[:20]:
            print(f"- {_display_path(item.path)} is newer than {_display_path(GENERATED_INDEX)}", file=sys.stderr)
        if len(stale) > 20:
            print(f"- ...and {len(stale) - 20} more newer input files", file=sys.stderr)
        return 1
    print("check_data_freshness: generated site data is fresh")
    return 0


def _input_files(paths: Sequence[Path]) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists():
            raise FreshnessError(f"watched path is missing: {resolved}")
        if resolved.is_file():
            files.append(resolved)
            continue
        files.extend(sorted(item for item in resolved.rglob("*") if item.is_file()))
    return tuple(files)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
