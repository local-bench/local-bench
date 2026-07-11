from __future__ import annotations

import json
from importlib.resources import files
from typing import Final

from localbench._types import JsonObject

SUBMISSION_FORMAT: Final = "localbench.submission-bundle.v1"
MANIFEST_SCHEMA_VERSION: Final = "localbench.submission-manifest.v1"
ITEM_SCHEMA_VERSION: Final = "localbench.submission-item.v1"
VERIFICATION_SCHEMA_VERSION: Final = "localbench.submission-verification.v1"
RESULT_BUNDLE_SCHEMA_VERSION: Final = "localbench.result_bundle.v1"
SUBMISSION_ENVELOPE_SCHEMA_VERSION: Final = "localbench.submission_envelope.v1"
ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION: Final = "localbench.accepted_result_projection.v2"
SUITE_RELEASE_MANIFEST_SCHEMA_VERSION: Final = "localbench.suite_release_manifest.v1"

MANIFEST_SCHEMA: Final = "submission_manifest_v1.schema.json"
ITEM_SCHEMA: Final = "submission_item_v1.schema.json"
VERIFICATION_SCHEMA: Final = "submission_verification_v1.schema.json"
RESULT_BUNDLE_SCHEMA: Final = "result_bundle_v1.schema.json"
SUBMISSION_ENVELOPE_SCHEMA: Final = "submission_envelope_v1.schema.json"
ACCEPTED_RESULT_PROJECTION_SCHEMA: Final = "accepted_result_projection_v2.schema.json"
SUITE_RELEASE_MANIFEST_SCHEMA: Final = "suite_release_manifest_v1.schema.json"


def load_schema(name: str) -> JsonObject:
    schema_path = files("localbench.submissions.schemas").joinpath(name)
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
