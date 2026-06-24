"""Run-record schema identity for localbench JSON outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from localbench._types import JsonValue

RUN_SCHEMA_VERSION: Final = "localbench.run.v1"


class RunSchemaVersionError(ValueError):
    """Raised when a run record has no supported schema_version."""


def check_run_schema_version(record: Mapping[str, JsonValue]) -> None:
    """Fail closed when a run record does not declare the current schema version."""
    if record.get("schema_version") != RUN_SCHEMA_VERSION:
        raise RunSchemaVersionError(
            f"run record schema_version must be {RUN_SCHEMA_VERSION}",
        )
