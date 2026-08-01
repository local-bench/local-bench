from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass
from typing import Callable, Final, Protocol, final

_ES_CONTINUOUS: Final = 0x80000000
_ES_SYSTEM_REQUIRED: Final = 0x00000001


class RenewableKeepAwakeLease(Protocol):
    def acquire(self, seconds: float) -> None: ...

    def renew(self, seconds: float) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class KeepAwakeLeaseExpiredError(RuntimeError):
    expired_at: float
    observed_at: float

@final
class PlatformKeepAwakeLease:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic: Callable[[], float] = monotonic
        self._expires_at: float | None = None
        self._active: bool = False

    def acquire(self, seconds: float) -> None:
        self._set_platform_state(active=True)
        self._expires_at = self._monotonic() + max(0.0, seconds)
        self._active = True

    def renew(self, seconds: float) -> None:
        now = self._monotonic()
        expires_at = self._expires_at
        if not self._active or expires_at is None or now > expires_at:
            raise KeepAwakeLeaseExpiredError(expires_at or now, now)
        self._set_platform_state(active=True)
        self._expires_at = now + max(0.0, seconds)

    def release(self) -> None:
        if self._active:
            self._set_platform_state(active=False)
        self._active = False
        self._expires_at = None

    @staticmethod
    def _set_platform_state(*, active: bool) -> None:
        if sys.platform != "win32":
            return
        flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED if active else _ES_CONTINUOUS
        if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0:
            raise OSError("SetThreadExecutionState failed")
