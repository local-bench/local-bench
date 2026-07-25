"""vLLM determinism policies.

The vLLM maintainer lane runs under one of two named determinism policies:

- ``vllm-batch-invariant-v1``: architectures vLLM supports under
  ``VLLM_BATCH_INVARIANT=1``. The full batch-invariant evidence web applies
  (launch export, env allowlist, live environ probe, affirmative kernel line).

- ``vllm-gdn-structural-single-slot-eager-v1``: GDN/linear-attention hybrid
  architectures (e.g. Qwen3.6), which vLLM refuses to initialise in
  batch-invariant mode. The policy makes a narrower public claim —
  empirically reproducible across clean process starts under structural
  single-slot execution on the recorded stack; NOT batch-invariant — and
  compensates with pinned backend resolution, eager execution, autotune
  selection capture, and a long-context token-level canary matrix.

Policy selection is architecture-based via the snapshot config. Multimodal
wrapper configs nest the LM fields under ``text_config``; every consumer of
snapshot config fields must go through :func:`resolve_model_text_config` so
policy selection, memory fit, and the SGLang mirror can never disagree.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from localbench._types import JsonObject

VLLM_BATCH_INVARIANT_POLICY_ID = "vllm-batch-invariant-v1"
VLLM_GDN_POLICY_ID = "vllm-gdn-structural-single-slot-eager-v1"

# Exact engine-version allowlist for the GDN policy. The affirmative log
# matchers and backend pins below are qualified against these versions only;
# widening this set requires re-qualifying the matchers as a named pair.
GDN_VLLM_VERSION_ALLOWLIST = frozenset({"0.25.1"})

# Marker substrings that identify a GDN/linear-attention layer entry in the
# snapshot config's layer_types list.
_GDN_LAYER_MARKERS = ("linear_attention", "gated_delta", "gdn")

BATCH_INVARIANT_CLAIM = (
    "best-effort same-stack reproducibility; not bitwise cross-stack determinism"
)
GDN_STRUCTURAL_CLAIM = (
    "empirically reproducible across clean process starts under structural "
    "single-slot execution on the recorded stack; not vLLM batch-invariant "
    "and not cross-stack bitwise deterministic"
)


def resolve_model_text_config(config: object) -> JsonObject:
    """Overlay ``text_config`` onto the top-level snapshot config.

    Multimodal wrapper configs (e.g. the unsloth Qwen3.6 NVFP4 snapshots) nest
    the language-model fields — layer_types, num_hidden_layers, head_dim,
    torch_dtype — under ``text_config``. Nested keys win over top-level keys.
    """
    if not isinstance(config, dict):
        raise RuntimeError("vLLM policy resolution requires an object config.json")
    nested = config.get("text_config")
    if isinstance(nested, dict):
        return {**config, **nested}
    return dict(config)


def load_model_text_config(snapshot_dir: Path) -> JsonObject:
    config_path = snapshot_dir / "config.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "vLLM policy resolution requires a valid snapshot config.json"
        ) from error
    return resolve_model_text_config(raw)


def config_layer_types(config: JsonObject) -> list[str]:
    layer_types = config.get("layer_types")
    if not isinstance(layer_types, list):
        return []
    return [value for value in layer_types if isinstance(value, str)]


def is_gdn_architecture(config: JsonObject) -> bool:
    """True when any layer is a GDN/linear-attention layer.

    Expects a config already passed through :func:`resolve_model_text_config` —
    a naive read of the raw wrapper config would miss ``layer_types`` entirely
    and misclassify the model as batch-invariant capable.
    """
    for value in config_layer_types(config):
        lowered = value.lower()
        if any(marker in lowered for marker in _GDN_LAYER_MARKERS):
            return True
    return False


def select_vllm_policy(config: JsonObject) -> str:
    return VLLM_GDN_POLICY_ID if is_gdn_architecture(config) else VLLM_BATCH_INVARIANT_POLICY_ID


def policy_claim(policy_id: str) -> str:
    if policy_id == VLLM_GDN_POLICY_ID:
        return GDN_STRUCTURAL_CLAIM
    return BATCH_INVARIANT_CLAIM


# --- serve pins -------------------------------------------------------------

# Flags appended to the base serve argv under the GDN policy. Every backend
# choice is pinned away from "auto"; eager mode removes the cudagraph
# dispatch/capture axis from the evidence burden (a later ...-graphs-v1 policy
# may restore it after qualification).
GDN_SERVE_FLAGS: tuple[str, ...] = (
    "--enforce-eager",
    "--gdn-prefill-backend",
    "triton",
    "--attention-backend",
    "TRITON_ATTN",
    "--linear-backend",
    "cutlass",
    "--no-enable-flashinfer-autotune",
    "--no-enable-mamba-cache-stochastic-rounding",
    "--jit-monitor-mode",
    "error",
    "--return-tokens-as-token-ids",
    # Text-only lane: a zero limit disables each multimodal modality and its
    # encoder-cache/2-max-image profiling, which otherwise reserves GiBs the
    # benchmark never uses (observed: only 1.5 GiB left for KV at ctx 32768).
    "--limit-mm-per-prompt",
    '{"image":0,"video":0}',
)

GDN_REQUIRED_FLAGS: frozenset[str] = frozenset(
    flag for flag in GDN_SERVE_FLAGS if flag.startswith("--")
)

# Environment pinned into the server process under the GDN policy, verified
# live via /proc/<pid>/environ. Per-start cache isolation dirs are derived
# from the run token at launch time and are deliberately NOT part of this
# fingerprintable allowlist.
GDN_ENV_PINS: dict[str, str] = {
    "CUDA_VISIBLE_DEVICES": "0",
    "PYTHONHASHSEED": "0",
    "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
    "FLA_TRIL_PRECISION": "ieee",
    "FLA_USE_CUDA_GRAPH": "0",
    "FLA_USE_TMA": "0",
    "TRITON_PRINT_AUTOTUNING": "1",
}

BATCH_INVARIANT_ENV_PINS: dict[str, str] = {
    "CUDA_VISIBLE_DEVICES": "0",
    "VLLM_BATCH_INVARIANT": "1",
}


def policy_env_pins(policy_id: str) -> dict[str, str]:
    if policy_id == VLLM_GDN_POLICY_ID:
        return dict(GDN_ENV_PINS)
    return dict(BATCH_INVARIANT_ENV_PINS)


def policy_serve_flags(policy_id: str) -> tuple[str, ...]:
    if policy_id == VLLM_GDN_POLICY_ID:
        return GDN_SERVE_FLAGS
    return ()


def policy_flash_attention_label(policy_id: str) -> str:
    if policy_id == VLLM_GDN_POLICY_ID:
        return "triton-attn-structural-single-slot-eager"
    return "batch-invariant"


# --- affirmative backend resolution ----------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedBackendEvidence:
    """Affirmative backend-resolution facts parsed from the serve log.

    Fail-closed: a fact is only satisfied when its affirmative line was found
    AND the resolved value matches the pin. ``None`` means the line was absent.
    """

    nvfp4_linear_kernel: str | None
    attention_backend: str | None
    gdn_prefill_backend: str | None
    eager_mode: bool | None
    matched_lines: tuple[str, ...]

    def satisfied(self) -> bool:
        return (
            self.nvfp4_linear_kernel == "CutlassNvFp4LinearKernel"
            and self.attention_backend == "TRITON_ATTN"
            and self.gdn_prefill_backend is not None
            and "triton" in self.gdn_prefill_backend.lower()
            and self.eager_mode is True
        )

    def as_json(self) -> JsonObject:
        return {
            "nvfp4_linear_kernel": self.nvfp4_linear_kernel,
            "attention_backend": self.attention_backend,
            "gdn_prefill_backend": self.gdn_prefill_backend,
            "eager_mode": self.eager_mode,
            "matched_lines": list(self.matched_lines),
            "satisfied": self.satisfied(),
        }


# Matcher table for vLLM 0.25.1 (the allowlisted version). These shapes are
# qualified during release gate 0 against a live serve log; any allowlist
# widening must re-qualify them.
_NVFP4_KERNEL_RE = re.compile(r"Using (\w+) for NVFP4 GEMM")
_ATTENTION_BACKEND_RE = re.compile(r"Using ([A-Z0-9_]+) attention backend")
_GDN_PREFILL_RE = re.compile(r"Using ([\w/.-]+) GDN prefill", re.IGNORECASE)
_EAGER_RES = (
    re.compile(r"enforce_eager=True"),
    re.compile(r"enforce_eager['\"]?\s*[:=]\s*True"),
    re.compile(r"cudagraph_mode[^\n]*NONE"),
)


def parse_resolved_backends(serve_log_text: str) -> ResolvedBackendEvidence:
    nvfp4: str | None = None
    attention: str | None = None
    gdn_prefill: str | None = None
    eager: bool | None = None
    matched: list[str] = []
    for line in serve_log_text.splitlines():
        nvfp4_match = _NVFP4_KERNEL_RE.search(line)
        if nvfp4_match is not None:
            nvfp4 = nvfp4_match.group(1)
            matched.append(line.strip())
            continue
        attention_match = _ATTENTION_BACKEND_RE.search(line)
        if attention_match is not None:
            attention = attention_match.group(1)
            matched.append(line.strip())
            continue
        gdn_match = _GDN_PREFILL_RE.search(line)
        if gdn_match is not None:
            gdn_prefill = gdn_match.group(1)
            matched.append(line.strip())
            continue
        if eager is not True and any(pattern.search(line) for pattern in _EAGER_RES):
            eager = True
            matched.append(line.strip())
    return ResolvedBackendEvidence(
        nvfp4_linear_kernel=nvfp4,
        attention_backend=attention,
        gdn_prefill_backend=gdn_prefill,
        eager_mode=eager,
        matched_lines=tuple(matched),
    )


# --- Triton autotune selection manifest -------------------------------------

# TRITON_PRINT_AUTOTUNING=1 emits, per autotuned kernel, a line containing the
# kernel name and the winning config. Timings are noise (they differ every
# start by construction); the manifest hashes only (kernel, config) pairs.
_AUTOTUNE_RE = re.compile(
    r"Triton autotuning for (?:function )?(\S+) finished after [^;]*;"
    r"\s*best config selected:\s*(.+?)\s*$"
)


def extract_autotune_selections(serve_log_text: str) -> tuple[tuple[str, str], ...]:
    selections: set[tuple[str, str]] = set()
    for line in serve_log_text.splitlines():
        match = _AUTOTUNE_RE.search(line)
        if match is not None:
            kernel = match.group(1)
            config = re.sub(r"\s+", " ", match.group(2)).rstrip(";,")
            selections.add((kernel, config))
    return tuple(sorted(selections))


def autotune_manifest_sha256(selections: tuple[tuple[str, str], ...]) -> str | None:
    if not selections:
        return None
    canonical = json.dumps(list(selections), ensure_ascii=False, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
