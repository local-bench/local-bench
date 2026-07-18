from __future__ import annotations

import json
import os
from types import TracebackType
from collections.abc import Callable
from pathlib import Path

from auto_validator_model import JsonObject, json_object, pid_alive as process_alive, scrub_text, text, utc_now


class RotatingLog:
    def __init__(self, path: Path, secret: str) -> None:
        self.path = path
        self.secret = secret

    def __call__(self, message: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size >= 5 * 1024 * 1024:
            self._rotate()
        with self.path.open("a", encoding="utf-8", buffering=1) as handle:
            handle.write(f"{utc_now()} {scrub_text(message, self.secret)}\n")

    def _rotate(self) -> None:
        self.path.with_suffix(self.path.suffix + ".3").unlink(missing_ok=True)
        for index in (2, 1):
            source = self.path.with_suffix(self.path.suffix + f".{index}")
            if source.exists():
                source.replace(self.path.with_suffix(self.path.suffix + f".{index + 1}"))
        self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))


class AlreadyRunningError(RuntimeError):
    pass


class PidLock:
    def __init__(
        self,
        path: Path,
        *,
        pid: int | None = None,
        is_alive: Callable[[int], bool] | None = None,
        log: Callable[[str], None] | None = None,
        pid_alive: Callable[[int], bool] | None = None,
    ) -> None:
        self.path = path
        self.pid = pid or os.getpid()
        self.is_alive = is_alive or pid_alive or process_alive
        self.log = log or (lambda _message: None)

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                owner = int(self.path.read_text(encoding="utf-8").strip())
            except ValueError:
                owner = -1
            if owner > 0 and self.is_alive(owner):
                raise AlreadyRunningError(f"auto-validator already running with pid {owner}")
            self.log(f"warning: replacing stale lock pid={owner}")
        self.path.write_text(str(self.pid), encoding="utf-8")

    def release(self) -> None:
        try:
            if self.path.read_text(encoding="utf-8").strip() == str(self.pid):
                self.path.unlink()
        except FileNotFoundError:
            return

    def __enter__(self) -> PidLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


class IntentJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: JsonObject) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", buffering=1) as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def dangling(self) -> list[JsonObject]:
        if not self.path.exists():
            return []
        attempts: dict[str, JsonObject] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json_object(json.loads(line))
            attempt = text(record.get("attempt_id"))
            if attempt is None:
                continue
            if "intent" in record:
                attempts[attempt] = record
            elif "outcome" in record:
                intent = attempts.get(attempt)
                if intent is not None:
                    intent["recorded_outcome"] = record["outcome"]
            elif "decision_logged" in record:
                attempts.pop(attempt, None)
        return [
            intent
            for intent in attempts.values()
            if intent.get("recorded_outcome") != "conflict"
        ]
