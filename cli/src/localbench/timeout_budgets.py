from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Protocol

import httpx

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.loop_config import (
    TASK_FINALIZE_TEARDOWN_RESERVE_S,
)

MIN_GENERATION_TOKENS_PER_SECOND: Final = 10
HTTP_CONNECT_TIMEOUT_S: Final = 10.0
HTTP_WRITE_TIMEOUT_S: Final = 30.0
HTTP_POOL_TIMEOUT_S: Final = 10.0
HTTP_READ_FINALIZE_RESERVE_S: Final = 30
STATIC_REQUEST_MAX_ATTEMPTS: Final = 3
AGENTIC_CAMPAIGN_MAX_RUNS: Final = 3
STATIC_ITEM_FINALIZE_RESERVE_S: Final = 60
CAMPAIGN_STARTUP_RESERVE_S: Final = 300
CAMPAIGN_FINALIZATION_RESERVE_S: Final = 300
KEEP_AWAKE_TEARDOWN_RESERVE_S: Final = 60
TIMEOUT_PROVENANCE: Final = "profile-derived-10-tokens-per-second"


class ExecutionTimeoutProfile(Protocol):
    @property
    def static_think_tokens(self) -> int: ...

    @property
    def static_final_tokens(self) -> int: ...

    @property
    def per_task_timeout_s(self) -> int: ...


@dataclass(frozen=True, slots=True)
class TimeoutBudget:
    profile: ExecutionTimeoutProfile
    remaining_static_items: int
    remaining_agentic_tasks: int
    connect_seconds: float = HTTP_CONNECT_TIMEOUT_S
    write_seconds: float = HTTP_WRITE_TIMEOUT_S
    pool_seconds: float = HTTP_POOL_TIMEOUT_S
    provenance: str = TIMEOUT_PROVENANCE

    def generation_seconds(self, output_tokens: int) -> int:
        return math.ceil(max(0, output_tokens) / MIN_GENERATION_TOKENS_PER_SECOND)

    def request_read_seconds(self, output_tokens: int) -> float:
        return float(self.generation_seconds(output_tokens) + HTTP_READ_FINALIZE_RESERVE_S)

    @property
    def agentic_task_transport_seconds(self) -> float:
        return max(
            0.0,
            float(self.profile.per_task_timeout_s) - TASK_FINALIZE_TEARDOWN_RESERVE_S,
        )

    @property
    def static_item_seconds(self) -> float:
        return (
            STATIC_REQUEST_MAX_ATTEMPTS
            * (
                self.request_read_seconds(self.profile.static_think_tokens)
                + self.request_read_seconds(self.profile.static_final_tokens)
            )
            + STATIC_ITEM_FINALIZE_RESERVE_S
        )

    @property
    def no_progress_seconds(self) -> float:
        return max(self.static_item_seconds, float(self.profile.per_task_timeout_s))

    @property
    def keepawake_lease_seconds(self) -> float:
        return self.no_progress_seconds + KEEP_AWAKE_TEARDOWN_RESERVE_S

    @property
    def campaign_seconds(self) -> float:
        remaining_work_seconds = (
            self.remaining_static_items * self.static_item_seconds
            + self.remaining_agentic_tasks
            * self.profile.per_task_timeout_s
            * AGENTIC_CAMPAIGN_MAX_RUNS
        )
        return (
            CAMPAIGN_STARTUP_RESERVE_S
            + max(remaining_work_seconds, self.no_progress_seconds)
            + CAMPAIGN_FINALIZATION_RESERVE_S
        )

    def httpx_timeout(self, output_tokens: int) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_seconds,
            read=self.request_read_seconds(output_tokens),
            write=self.write_seconds,
            pool=self.pool_seconds,
        )

    def as_record(self) -> JsonObject:
        return {
            "provenance": self.provenance,
            "minimum_generation_tokens_per_second": MIN_GENERATION_TOKENS_PER_SECOND,
            "connect_seconds": self.connect_seconds,
            "write_seconds": self.write_seconds,
            "pool_seconds": self.pool_seconds,
            "read_finalize_reserve_seconds": HTTP_READ_FINALIZE_RESERVE_S,
            "static_request_max_attempts": STATIC_REQUEST_MAX_ATTEMPTS,
            "agentic_campaign_max_runs": AGENTIC_CAMPAIGN_MAX_RUNS,
            "agentic_task_finalize_teardown_reserve_seconds": (
                TASK_FINALIZE_TEARDOWN_RESERVE_S
            ),
            "agentic_task_transport_seconds": self.agentic_task_transport_seconds,
            "static_item_finalize_reserve_seconds": STATIC_ITEM_FINALIZE_RESERVE_S,
            "campaign_startup_reserve_seconds": CAMPAIGN_STARTUP_RESERVE_S,
            "campaign_finalization_reserve_seconds": CAMPAIGN_FINALIZATION_RESERVE_S,
            "keepawake_teardown_reserve_seconds": KEEP_AWAKE_TEARDOWN_RESERVE_S,
            "no_progress_seconds": self.no_progress_seconds,
            "keepawake_lease_seconds": self.keepawake_lease_seconds,
            "campaign_seconds": self.campaign_seconds,
        }


def derive_timeout_budget(
    profile: ExecutionTimeoutProfile,
    *,
    remaining_static_items: int,
    remaining_agentic_tasks: int,
) -> TimeoutBudget:
    return TimeoutBudget(
        profile=profile,
        remaining_static_items=max(0, remaining_static_items),
        remaining_agentic_tasks=max(0, remaining_agentic_tasks),
    )
