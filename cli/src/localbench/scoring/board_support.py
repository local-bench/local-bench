"""Shared support helpers for board_v1 generation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.board_types import BoardBuildError

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
DEFAULT_RUNS_DIR: Final = REPO_ROOT / "cli" / "runs"
DEFAULT_OUT: Final = DEFAULT_RUNS_DIR / "board" / "board_v1.json"
DEFAULT_CURATION: Final = REPO_ROOT / "cli" / "src" / "localbench" / "data" / "board_sources.json"
DEFAULT_PARITY_INDEX: Final = REPO_ROOT / "web" / "public" / "data" / "index.json"
DEFAULT_BOOTSTRAP_ITERS: Final = 10_000
DEFAULT_BOOTSTRAP_SEED: Final = 0
INDEX_VERSION_FALLBACK: Final = "index-v1"
LANE_SCOPE: Final = "capped-thinking"
DATASET_VERSION: Final = "dataset-pins-via-suite-item-set-hashes"
# Bare basename: resolved by run_path() against the board's --runs-dir (now the absolute
# DEFAULT_RUNS_DIR by default, so the REAL board finds it under cli/runs regardless of cwd). Kept a
# basename (NOT a cli/runs/ prefix) so fixture tests with their own tmp_path runs_dir do NOT pick up
# the real gemma run file (a cli/runs/ prefix resolves via REPO_ROOT and would pollute fixtures).
GEMMA_FALLBACK_FILE: Final = "ladder-gemma4-31b-Q4_K_M.json"


def read_json(path: Path) -> JsonValue:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    path.write_bytes(data)


def run_path(raw: str, runs_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.parts[:2] == ("cli", "runs"):
        return REPO_ROOT / path
    return runs_dir / path


def is_superseded(path: Path) -> bool:
    return any(part.startswith("_superseded-") for part in path.parts)


def index_version(path: Path) -> str:
    if not path.exists():
        return INDEX_VERSION_FALLBACK
    data = object_value(read_json(path), str(path))
    return text_value(data.get("index_version")) or INDEX_VERSION_FALLBACK


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "model"


def percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] * (1.0 - (position - lower)) + values[upper] * (position - lower)


def object_value(value: JsonValue | None, context: str) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise BoardBuildError(f"{context} must be an object")


def object_or_empty(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def object_or_none(value: JsonValue | None) -> JsonObject | None:
    return value if isinstance(value, dict) else None


def objects_value(value: JsonValue | None, context: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise BoardBuildError(f"{context} must be a list")
    return [object_value(item, context) for item in value]


def list_value(value: JsonValue | None, context: str) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    raise BoardBuildError(f"{context} must be a list")


def string_value(value: JsonValue | None, context: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise BoardBuildError(f"{context} must be a non-empty string")


def text_value(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def bool_value(value: JsonValue | None, context: str) -> bool:
    if isinstance(value, bool):
        return value
    raise BoardBuildError(f"{context} must be a bool")


def bool_or_false(value: JsonValue | None) -> bool:
    return value if isinstance(value, bool) else False


def number_value(value: JsonValue | None, context: str) -> float:
    number = number_or_none(value)
    if number is not None:
        return number
    raise BoardBuildError(f"{context} must be a number")


def number_or_none(value: JsonValue | None) -> float | None:
    return None if isinstance(value, bool) else float(value) if isinstance(value, int | float) else None


def int_value(value: JsonValue | None, context: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise BoardBuildError(f"{context} must be an integer")
