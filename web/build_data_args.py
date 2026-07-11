from __future__ import annotations

from pathlib import Path

from build_data_support import DataBuildError, fail


def parse_args(
    argv: list[str],
    *,
    root: Path,
    default_iters: int,
    default_benches: tuple[str, ...],
    default_weights: dict[str, float],
) -> tuple[Path, Path, int, tuple[str, ...], dict[str, float], Path | None]:
    sources = root / "web" / "data_sources.json"
    out_dir = root / "web" / "public" / "data"
    iters = default_iters
    benches = default_benches
    weights = default_weights
    publication_bundle: Path | None = None
    index = 0
    while index < len(argv):
        match argv[index]:
            case "--sources":
                sources = Path(_next_arg(argv, index)).resolve()
            case "--out":
                out_dir = Path(_next_arg(argv, index)).resolve()
            case "--iters":
                iters = _positive_int(_next_arg(argv, index), "--iters")
            case "--benches":
                benches = _bench_list(_next_arg(argv, index))
                weights = {bench: 1.0 for bench in benches}
            case "--publication-bundle":
                publication_bundle = Path(_next_arg(argv, index)).resolve()
            case "--help" | "-h":
                print("usage: python web/build_data.py [--sources PATH] [--out PATH] [--iters N] [--benches a,b,c] [--publication-bundle PATH]")
                raise SystemExit(0)
            case other:
                raise DataBuildError(f"unknown argument {other}")
        index += 2
    return sources, out_dir, iters, benches, weights, publication_bundle


def _next_arg(argv: list[str], index: int) -> str:
    return argv[index + 1] if index + 1 < len(argv) else fail(f"{argv[index]} requires a value")


def _positive_int(value: str, context: str) -> int:
    if not value.isdecimal() or int(value) <= 0:
        fail(f"{context} must be a positive integer")
    return int(value)


def _bench_list(value: str) -> tuple[str, ...]:
    benches = tuple(bench.strip() for bench in value.split(",") if bench.strip())
    if not benches:
        fail("--benches must include at least one bench")
    if len(set(benches)) != len(benches):
        fail("--benches must not contain duplicates")
    return benches
