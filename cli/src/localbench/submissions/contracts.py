from __future__ import annotations

import json
from importlib.resources import files
from typing import Final

from localbench._types import JsonObject

SUBMISSION_FORMAT: Final = "localbench.submission-bundle.v1"
MANIFEST_SCHEMA_VERSION: Final = "localbench.submission-manifest.v1"
ITEM_SCHEMA_VERSION: Final = "localbench.submission-item.v1"
VERIFICATION_SCHEMA_VERSION: Final = "localbench.submission-verification.v1"

MANIFEST_SCHEMA: Final = "submission_manifest_v1.schema.json"
ITEM_SCHEMA: Final = "submission_item_v1.schema.json"
VERIFICATION_SCHEMA: Final = "submission_verification_v1.schema.json"


def load_schema(name: str) -> JsonObject:
    schema_path = files("localbench.submissions.schemas").joinpath(name)
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
