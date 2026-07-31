from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_CONTEXT_RE: Final = re.compile(r"\bllama_context:\s+n_ctx\s*=\s*(\d+)\b")
_SLOT_CONTEXT_RE: Final = re.compile(
    r"\bllama_context:\s+n_ctx_seq\s*=\s*(\d+)\b",
)
_PARALLEL_SLOTS_RE: Final = re.compile(
    r"\bllama_context:\s+n_seq_max\s*=\s*(\d+)\b",
)
_FLASH_ATTN_RE: Final = re.compile(
    r"\bllama_context:\s+flash_attn\s*=\s*([a-zA-Z0-9_-]+)\b",
)
_CACHE_TYPE_K_RE: Final = re.compile(r"\bllama_kv_cache:.*\bK \(([^)]+)\):")
_CACHE_TYPE_V_RE: Final = re.compile(r"\bllama_kv_cache:.*\bV \(([^)]+)\):")
_FIT_LOG_RE: Final = re.compile(r"\bcommon_params_fit(?:_impl)?:", re.IGNORECASE)
_EXPECTED_CACHE_TYPE: Final = "f16"
_EXPECTED_SLOT_COUNT: Final = 1
_FLASH_ARG_TO_LOG: Final[dict[str, str]] = {
    "auto": "auto",
    "off": "disabled",
    "on": "enabled",
}


@dataclass(frozen=True, slots=True)
class LlamaStartupCapacityEvidence:
    context_tokens: tuple[int, ...]
    slot_context_tokens: tuple[int, ...]
    parallel_slots: tuple[int, ...]
    cache_type_k: tuple[str, ...]
    cache_type_v: tuple[str, ...]
    flash_attn: tuple[str, ...]
    fit_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StartupCapacityAssessment:
    context_tokens: int | None
    slot_context_tokens: int | None
    parallel_slots: int | None
    cache_type_k: str | None
    cache_type_v: str | None
    fit: str | None
    flash_attn: str | None
    failures: tuple[str, ...]


def assess_llama_startup_capacity(
    text: str,
    launch_argv: list[str],
    required_context_tokens: int,
) -> StartupCapacityAssessment:
    parsed = parse_llama_startup_capacity(text)
    failures: list[str] = []
    context_tokens = _single_integer("logged context", parsed.context_tokens, failures)
    slot_context_tokens = _single_integer(
        "logged slot context",
        parsed.slot_context_tokens,
        failures,
    )
    parallel_slots = _single_integer(
        "logged parallel slots",
        parsed.parallel_slots,
        failures,
    )
    cache_type_k = _single_text("cache_type_k", parsed.cache_type_k, failures)
    cache_type_v = _single_text("cache_type_v", parsed.cache_type_v, failures)
    flash_attn = _single_text("flash_attn", parsed.flash_attn, failures)
    launch_fit = _launch_flag_value(launch_argv, "--fit")
    launch_flash_attn = _launch_flag_value(launch_argv, "--flash-attn")
    expected_flash_attn = (
        None if launch_flash_attn is None else _FLASH_ARG_TO_LOG.get(launch_flash_attn)
    )
    launch_cache_type_k = _launch_flag_value(launch_argv, "--cache-type-k")
    launch_cache_type_v = _launch_flag_value(launch_argv, "--cache-type-v")

    _require_exact("logged context", context_tokens, required_context_tokens, failures)
    _require_exact(
        "logged slot context",
        slot_context_tokens,
        required_context_tokens,
        failures,
    )
    _require_exact("logged parallel slots", parallel_slots, _EXPECTED_SLOT_COUNT, failures)
    if cache_type_k != _EXPECTED_CACHE_TYPE or launch_cache_type_k != _EXPECTED_CACHE_TYPE:
        failures.append(
            f"cache_type_k must be f16; logged {cache_type_k!r}, launch {launch_cache_type_k!r}",
        )
    if cache_type_v != _EXPECTED_CACHE_TYPE or launch_cache_type_v != _EXPECTED_CACHE_TYPE:
        failures.append(
            f"cache_type_v must be f16; logged {cache_type_v!r}, launch {launch_cache_type_v!r}",
        )
    if launch_fit != "off":
        failures.append(f"launch must contain canonical --fit off; observed {launch_fit!r}")
    if parsed.fit_evidence:
        failures.append(
            "fit adjustment evidence is forbidden: " + "; ".join(parsed.fit_evidence),
        )
    if flash_attn is None or flash_attn != expected_flash_attn:
        failures.append(
            f"flash_attn startup state must match the canonical launch; logged {flash_attn!r}, launch {launch_flash_attn!r}",
        )
    return StartupCapacityAssessment(
        context_tokens=context_tokens,
        slot_context_tokens=slot_context_tokens,
        parallel_slots=parallel_slots,
        cache_type_k=cache_type_k,
        cache_type_v=cache_type_v,
        fit="off" if launch_fit == "off" and not parsed.fit_evidence else None,
        flash_attn=flash_attn,
        failures=tuple(failures),
    )


def parse_llama_startup_capacity(text: str) -> LlamaStartupCapacityEvidence:
    return LlamaStartupCapacityEvidence(
        context_tokens=_integer_values(_CONTEXT_RE, text),
        slot_context_tokens=_integer_values(_SLOT_CONTEXT_RE, text),
        parallel_slots=_integer_values(_PARALLEL_SLOTS_RE, text),
        cache_type_k=_text_values(_CACHE_TYPE_K_RE, text),
        cache_type_v=_text_values(_CACHE_TYPE_V_RE, text),
        flash_attn=_text_values(_FLASH_ATTN_RE, text),
        fit_evidence=tuple(
            line.strip()
            for line in text.splitlines()
            if _FIT_LOG_RE.search(line) is not None
        ),
    )


def _integer_values(pattern: re.Pattern[str], text: str) -> tuple[int, ...]:
    return tuple(sorted({int(match.group(1)) for match in pattern.finditer(text)}))


def _text_values(pattern: re.Pattern[str], text: str) -> tuple[str, ...]:
    return tuple(
        sorted({match.group(1).strip().lower() for match in pattern.finditer(text)}),
    )


def _single_integer(
    label: str,
    values: tuple[int, ...],
    failures: list[str],
) -> int | None:
    if len(values) == 1:
        return values[0]
    failures.append(f"startup log must report one {label}; observed {list(values)!r}")
    return None


def _single_text(
    label: str,
    values: tuple[str, ...],
    failures: list[str],
) -> str | None:
    if len(values) == 1:
        return values[0]
    failures.append(f"startup log must report one {label}; observed {list(values)!r}")
    return None


def _launch_flag_value(argv: list[str], flag: str) -> str | None:
    positions = [index for index, token in enumerate(argv) if token == flag]
    if len(positions) != 1:
        return None
    index = positions[0]
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        return None
    return argv[index + 1].lower()


def _require_exact(
    label: str,
    observed: int | None,
    required: int,
    failures: list[str],
) -> None:
    if observed != required:
        failures.append(f"{label} must equal {required}; observed {observed!r}")
