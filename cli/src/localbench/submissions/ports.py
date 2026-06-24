from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from localbench._types import JsonObject


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...


class StatusStore(Protocol):
    def write_status(self, submission_id: str, status: JsonObject) -> None: ...


class IdentityProvider(Protocol):
    def account_for_key(self, public_key: str) -> str | None: ...


class NonceStore(Protocol):
    def claim(self, nonce: str) -> bool: ...


class WorkQueue(Protocol):
    def enqueue(self, job: JsonObject) -> None: ...


class SecretProvider(Protocol):
    def hmac_secret(self) -> bytes: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...


class SignatureProvider(Protocol):
    def sign(self, payload: JsonObject) -> JsonObject: ...

    def verify(self, payload: JsonObject, signature: JsonObject) -> bool: ...


class ReviewSampler(Protocol):
    def sample_item_ids(self, submission_id: str, item_ids: Sequence[str]) -> tuple[str, ...]: ...
