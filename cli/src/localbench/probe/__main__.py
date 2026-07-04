from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from localbench._types import JsonValue
from localbench.probe.discrimination import (
    AxisResult,
    RunLabelInput,
    analyze_discrimination,
)

POINT_BISERIAL_NOTE = (
    "point-biserial is a secondary diagnostic; with few models it is weak/indicative."
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the suite-v1 probe discrimination analysis CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        labels = _read_labels(args.labels)
        run_paths = _run_paths(args.runs)
        records = _read_runs(run_paths, labels)
        axes = _read_suite_axes(args.suite_dir)
    except json.JSONDecodeError as error:
        print(f"error      invalid JSON in {error.doc!r}: {error.msg}")
        return 2
    except FileNotFoundError as error:
        print(f"error      missing file: {error.filename}")
        return 2
    except ValueError as error:
        print(f"error      {error}")
        return 2
    results = analyze_discrimination(records, axes, labels)
    payload = {
        "schema": "localbench-probe-legA-v1",
        "point_biserial_note": POINT_BISERIAL_NOTE,
        "axes": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    _print_table(results)
    print(POINT_BISERIAL_NOTE)
    print(f"output {args.out}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m localbench.probe")
    parser.add_argument(
        "--runs",
        nargs="+",
        required=True,
        type=Path,
        help="Run record files or directories containing *.json run records.",
    )
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--suite-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _read_json(path: Path) -> JsonValue:
    with path.open(encoding="utf-8") as handle:
        data: JsonValue = json.load(handle)
    return data


def _read_labels(path: Path) -> dict[str, RunLabelInput]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("labels JSON must be an object")
    labels: dict[str, RunLabelInput] = {}
    for run_key, value in raw.items():
        if isinstance(value, Mapping):
            raw_label = value.get("label")
            raw_model = value.get("model_name")
            if isinstance(raw_label, str) and isinstance(raw_model, str):
                labels[run_key] = {"label": raw_label, "model_name": raw_model}
    return labels


def _read_suite_axes(suite_dir: Path) -> dict[str, Mapping[str, JsonValue]]:
    raw = _read_json(suite_dir / "suite.json")
    if not isinstance(raw, dict):
        raise ValueError("suite.json must be an object")
    raw_axes = raw.get("axes")
    if not isinstance(raw_axes, dict):
        raise ValueError("suite.json must contain an axes object")
    axes: dict[str, Mapping[str, JsonValue]] = {}
    for axis, spec in raw_axes.items():
        if isinstance(spec, Mapping):
            axes[axis] = spec
    if not axes:
        raise ValueError("suite.json axes object is empty")
    return axes


def _run_paths(inputs: Sequence[Path]) -> list[Path]:
    paths: list[Path] = []
    for raw_path in inputs:
        if raw_path.is_dir():
            paths.extend(sorted(raw_path.glob("*.json")))
        elif raw_path.is_file():
            paths.append(raw_path)
        else:
            raise FileNotFoundError(raw_path)
    if not paths:
        raise ValueError("--runs did not match any JSON run records")
    return paths


def _read_runs(
    paths: Sequence[Path],
    labels: Mapping[str, RunLabelInput],
) -> dict[str, Mapping[str, JsonValue]]:
    records: dict[str, Mapping[str, JsonValue]] = {}
    for path in paths:
        raw = _read_json(path)
        if not isinstance(raw, dict):
            raise ValueError(f"run record must be a JSON object: {path}")
        records[_label_key_for_path(path, labels)] = raw
    return records


def _label_key_for_path(path: Path, labels: Mapping[str, RunLabelInput]) -> str:
    resolved = path.resolve()
    candidates = (
        str(path),
        path.as_posix(),
        path.name,
        f"{path.parent.name}/{path.name}",
        str(Path(path.parent.name) / path.name),
        str(resolved),
        resolved.as_posix(),
    )
    for candidate in candidates:
        if candidate in labels:
            return candidate
    return path.name


def _print_table(results: Sequence[AxisResult]) -> None:
    print(
        "axis                     verdict              anchors       locals        "
        "spread   pbis    weight  benches",
    )
    for result in results:
        print(
            f"{result['axis']:<24} "
            f"{result['verdict']:<20} "
            f"{_range(result['anchor_min'], result['anchor_max']):<13} "
            f"{_range(result['local_min'], result['local_max']):<13} "
            f"{_metric(result['overall_spread']):>6} "
            f"{_metric(result['mean_point_biserial']):>7} "
            f"{result['suggested_weight']:>7.3f} "
            f"{','.join(result['benches'])}",
        )
        notes = result.get("notes", [])
        for note in notes:
            print(f"  note {result['axis']}: {note}")


def _range(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "n/a"
    return f"{low:.3f}..{high:.3f}"


def _metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


if __name__ == "__main__":
    sys.exit(main())
