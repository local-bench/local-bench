from __future__ import annotations

from dataclasses import dataclass

from localbench._types import JsonObject


@dataclass(frozen=True, slots=True)
class ReferenceEdition:
    edition_id: str
    family: str
    artifact_sha256: str
    tokenizer_sha256: str
    template_sha256: str
    class_label: str
    created_utc: str
    checkset_edition: str
    execution_edition: str

    def as_dict(self) -> JsonObject:
        return {
            "artifact_sha256": self.artifact_sha256,
            "checkset_edition": self.checkset_edition,
            "class_label": self.class_label,
            "created_utc": self.created_utc,
            "edition_id": self.edition_id,
            "execution_edition": self.execution_edition,
            "family": self.family,
            "template_sha256": self.template_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
        }


class CheckError(RuntimeError):
    pass
