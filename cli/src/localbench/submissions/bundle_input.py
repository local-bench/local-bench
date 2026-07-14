from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.archive import unpack_bundle
from localbench.submissions.strict_json import StrictJsonError, strict_json_loads
from localbench.submissions.validate import SubmissionValidationError


@dataclass(frozen=True, slots=True)
class ResultBundleInput:
    record: JsonObject
    attestations: list[JsonObject]
    source_bytes: bytes


def load_result_bundle_input(path: Path) -> ResultBundleInput:
    if zipfile.is_zipfile(path):
        bundle = unpack_bundle(path)
        if bundle.run_original is None:
            raise SubmissionValidationError("run.original.json missing from submission bundle")
        return ResultBundleInput(
            record=bundle.run_original,
            attestations=bundle.attestations,
            source_bytes=bundle.files["run.original.json"],
        )
    source_bytes = path.read_bytes()
    return ResultBundleInput(record=_read_json_bytes(source_bytes), attestations=[], source_bytes=source_bytes)


def _read_json_bytes(source_bytes: bytes) -> JsonObject:
    try:
        data = strict_json_loads(source_bytes, "result bundle")
    except StrictJsonError as error:
        raise SubmissionValidationError(str(error)) from error
    if not isinstance(data, dict):
        raise SubmissionValidationError("result bundle must be a JSON object")
    return data
