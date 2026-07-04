from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.archive import unpack_bundle
from localbench.submissions.validate import SubmissionValidationError


@dataclass(frozen=True, slots=True)
class ResultBundleInput:
    record: JsonObject
    attestations: list[JsonObject]


def load_result_bundle_input(path: Path) -> ResultBundleInput:
    if zipfile.is_zipfile(path):
        bundle = unpack_bundle(path)
        if bundle.run_original is None:
            raise SubmissionValidationError("run.original.json missing from submission bundle")
        return ResultBundleInput(record=bundle.run_original, attestations=bundle.attestations)
    return ResultBundleInput(record=_read_json(path), attestations=[])


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SubmissionValidationError("result bundle must be a JSON object")
    return data
