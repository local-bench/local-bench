from __future__ import annotations

from typing import Literal

from localbench._types import JsonValue
from localbench.submissions.validate import SubmissionValidationError

SubmissionOrigin = Literal["project_anchor", "community"]


def normalize_origin(value: JsonValue | None) -> SubmissionOrigin:
    match value:
        case "project_anchor":
            return "project_anchor"
        case "community" | "community_submission":
            return "community"
        case _:
            raise SubmissionValidationError("submission origin is not supported")
