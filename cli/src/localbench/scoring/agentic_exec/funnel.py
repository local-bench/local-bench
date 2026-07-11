"""Staged funnel campaign harness for the AppWorld-C candidate (GPU run orchestration).

This is the orchestration the GPU run drives on top of the already-built + verified Protocol C
loop (``benchmark.run_appworld_c_benchmark``). It is model-agnostic: it takes a ``ModelClient``
factory (the real :class:`ChatCompletionsClient` for the GPU run, or a scripted/mock client for
the GPU-free tests) and runs a single funnel *stage* over a frozen task-id subset, persisting the
full :class:`BenchmarkReport` (ASR + every diagnostic rate + per-task rows) to a results JSON.

What it owns (everything that is NOT the loop itself):

  1. **Frozen, pre-registered task subsets** (``select_subset`` / :class:`SubsetSpec`): a
     deterministic, seeded, stratified selection from a stated AppWorld split, documented so it is
     reproducible and demonstrably NOT tuned on results. See ``appworld-c-funnel-harness.md``.
  2. **Run + persist** (``run_stage``): run a stage once, write ``<results_dir>/<label>.<stage>.run<k>.json``.
  3. **Reruns + run-to-run delta** (``run_with_reruns``): the LOCKED rule — 2 full reruns for a
     displayed row; if the max abs delta on the headline metric (ASR) exceeds 5pp, do a 3rd and
     report the mean. Deltas are reported in absolute percentage points.
  4. **Early-stop check** (``evaluate_early_stop``): flags the LOCKED early-stop conditions
     (best ~0/96, near-perfect/saturated, all-within-noise, failures dominated by
     parser/syntax/runtime/cap) so a scored sweep can halt instead of burning GPU.
  5. **Aggregation across reruns** (``RerunAggregate``): mean ASR + the per-run series + the
     max abs delta + whether a 3rd run was triggered, all JSON-serialisable.

GPU-free / model-free: this module imports NO model SDK and NO sandbox. The sandbox + model are
supplied by the caller via factories (``run_appworld_c_benchmark``'s seam). The unit tests drive
the whole thing with a scripted/mock client and a :class:`FakeSandbox`, proving the orchestration
end-to-end without a model or a GPU. The agentic axis stays unregistered / weight-0.

The signed contract intentionally hashes this whole module, including comments and docstrings.
That conservative over-coverage may require a re-mint for behavior-neutral edits; it prevents
score-affecting edits from slipping through an incomplete semantic source extractor.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from localbench.scoring.agentic_exec.benchmark import (
    ModelFactory,
    SandboxFactory,
    run_appworld_c_benchmark,
)
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.loop_types import BenchmarkReport, TaskOutcome

# ==================================================================================================
# Frozen subset selection — deterministic, pre-registered, stratified, NOT tuned on results.
# ==================================================================================================

# The AppWorld dev split (57 tasks, verified end-to-end on this box) is the CALIBRATION pool:
# smoke + lite are drawn from it. The 96-task SCORED subset is drawn from test_normal (168 tasks),
# AppWorld's standard held-out evaluation split — so scoring is strictly separate from the dev pool
# the loop budgets were calibrated on. (dev=57 < 96, so the scored set cannot be dev anyway.)
SMOKE_SPLIT = "dev"
LITE_SPLIT = "dev"
SCORED_SPLIT = "test_normal"

# Sizes (LOCKED by the launch plan funnel: smoke few -> lite ~36 -> 96-task scored).
SMOKE_SIZE = 1          # the launch plan's smoke is "1 system, find bugs, no score" — 1 task here.
SMOKE_SIZE_EXT = 6      # an optional slightly wider smoke (still dev) for loop-bug hunting.
LITE_SIZE = 36
SCORED_SIZE = 96

# The pre-registration seed. Fixed FOREVER for the v1 manifest; documented in the harness doc.
# Selection = sort the split's task ids, stratify by (difficulty band, primary app) when metadata
# is available, then take a deterministic round-robin across strata seeded by this value. Changing
# it would change the subset, so it is part of the frozen manifest.
SELECTION_SEED = 20260624


class Stage(StrEnum):
    """A funnel stage. The split + default size each maps to is fixed by the launch plan."""

    SMOKE = "smoke"
    LITE = "lite"
    SCORED = "scored"


@dataclass(frozen=True, slots=True)
class TaskMeta:
    """The stratification metadata for one task (read from AppWorld ground_truth/metadata.json).

    Only ``difficulty`` and ``primary_app`` are used for stratification; both are optional so the
    selection still works (falling back to a single stratum = plain seeded sort) when metadata is
    unavailable on a host. ``num_api_calls`` is carried for documentation/inspection only.
    """

    task_id: str
    difficulty: int | None = None
    primary_app: str | None = None
    num_api_calls: int | None = None


@dataclass(frozen=True, slots=True)
class SubsetSpec:
    """A frozen task subset: the inputs that produced it + the resulting ordered ids + a hash.

    Task-set identity and selection-recipe identity are deliberately separate. The canonical
    task-set hash covers only the exact ordered IDs; the recipe hash covers only the inputs that
    selected them. ``legacy_manifest_hash`` preserves the pre-C0 mixed hash for historical rows.
    """

    name: str
    split: str
    size: int
    seed: int
    task_ids: tuple[str, ...]
    selection_version: str = "v1"

    @property
    def ordered_task_ids_sha256(self) -> str:
        from localbench.scoring.agentic_exec.task_pool import ordered_task_ids_sha256

        return ordered_task_ids_sha256(self.task_ids)

    @property
    def selection_recipe_sha256(self) -> str:
        from localbench.scoring.agentic_exec.task_pool import selection_recipe_sha256

        return selection_recipe_sha256(
            split=self.split,
            seed=self.seed,
            selection_version=self.selection_version,
        )

    @property
    def legacy_manifest_hash(self) -> str:
        """The historical mixed recipe+IDs hash; never use as task identity for new records."""
        payload = json.dumps(
            {
                "split": self.split,
                "size": self.size,
                "seed": self.seed,
                "selection_version": self.selection_version,
                # Order matters for the run; the hash pins the exact order.
                "task_ids": list(self.task_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def manifest_hash(self) -> str:
        """Legacy mixed recipe+IDs identity retained for artifact compatibility."""
        return self.legacy_manifest_hash

    def as_dict(self) -> dict[str, Any]:
        contract_identity = _contract_task_identity(self.task_ids)
        return {
            "name": self.name,
            "split": self.split,
            "size": self.size,
            "seed": self.seed,
            "selection_version": self.selection_version,
            "task_ids": list(self.task_ids),
            "manifest_hash": self.manifest_hash,
            "ordered_task_ids_sha256": contract_identity.get(
                "ordered_task_ids_sha256", self.ordered_task_ids_sha256
            ),
            "selection_recipe_sha256": contract_identity.get(
                "selection_recipe_sha256", self.selection_recipe_sha256
            ),
            "semantic_task_sha256": contract_identity.get("semantic_task_sha256"),
        }


def _stratum_key(meta: TaskMeta) -> tuple[Any, ...]:
    """Strata = (difficulty band, primary app). Missing fields collapse to a sentinel bucket."""
    return (
        meta.difficulty if meta.difficulty is not None else -1,
        meta.primary_app if meta.primary_app is not None else "",
    )


def _seeded_rank(task_id: str, seed: int) -> str:
    """A deterministic per-task sort key from a hash of (seed, task_id).

    Using a hash (not Python's salted ``hash()``) keeps the order reproducible across processes and
    interpreters — essential for a frozen manifest. Returns a hex digest so ties are vanishingly
    unlikely and the order is stable.
    """
    h = hashlib.sha256(f"{seed}:{task_id}".encode("utf-8")).hexdigest()
    return h


def select_subset(
    name: str,
    split: str,
    size: int,
    available_ids: Sequence[str],
    metadata: dict[str, TaskMeta] | None = None,
    seed: int = SELECTION_SEED,
    selection_version: str = "v1",
) -> SubsetSpec:
    """Deterministically select ``size`` task ids from ``available_ids`` (a stated split).

    Algorithm (pure, reproducible, NOT tuned on results):

      1. Drop duplicates; sort ``available_ids`` lexicographically (a canonical starting order
         independent of how the split happened to be enumerated).
      2. Group into strata by ``(difficulty, primary_app)`` using ``metadata`` (when present);
         with no metadata everything falls into one stratum.
      3. Within each stratum, order tasks by ``_seeded_rank(task_id, seed)`` (a fixed hash —
         reproducible, and decoupled from id lexical order so the sample is not biased toward
         low/high ids).
      4. Round-robin across strata (strata visited in sorted key order) taking one task at a time
         until ``size`` are collected — yielding a stratified, representative sample.
      5. If ``size`` exceeds the pool, take the whole pool (documented; the caller asserts size).

    The returned :class:`SubsetSpec` carries a ``manifest_hash`` over the inputs + ordered ids for
    the freeze check. Selection is on the SPLIT MEMBERSHIP only — never on task outcomes — so it is
    demonstrably independent of any model's results.
    """
    uniq = sorted(set(available_ids))
    meta = metadata or {}

    # Bucket into strata (sorted by stratum key for determinism).
    strata: dict[tuple[Any, ...], list[str]] = {}
    for tid in uniq:
        key = _stratum_key(meta.get(tid, TaskMeta(task_id=tid)))
        strata.setdefault(key, []).append(tid)
    for key in strata:
        strata[key].sort(key=lambda t: _seeded_rank(t, seed))

    ordered_keys = sorted(strata.keys(), key=lambda k: (str(k[0]), str(k[1])))

    # Round-robin draw across strata until we reach `size` (or exhaust the pool).
    picked: list[str] = []
    target = min(size, len(uniq))
    cursors = {k: 0 for k in ordered_keys}
    while len(picked) < target:
        progressed = False
        for key in ordered_keys:
            if len(picked) >= target:
                break
            bucket = strata[key]
            c = cursors[key]
            if c < len(bucket):
                picked.append(bucket[c])
                cursors[key] = c + 1
                progressed = True
        if not progressed:  # all strata exhausted (target > pool, already clamped — defensive)
            break

    return SubsetSpec(
        name=name,
        split=split,
        size=len(picked),
        seed=seed,
        task_ids=tuple(picked),
        selection_version=selection_version,
    )


def subset_for_stage(
    stage: Stage,
    available_by_split: dict[str, Sequence[str]],
    metadata: dict[str, TaskMeta] | None = None,
    seed: int = SELECTION_SEED,
    *,
    wide_smoke: bool = False,
) -> SubsetSpec:
    """Build the frozen subset for a funnel ``stage`` from per-split id pools.

    ``available_by_split`` maps each AppWorld split name to its full id list (e.g. the output of
    ``load_task_ids``). The stage fixes which split + size to use. ``wide_smoke`` selects the
    optional 6-task smoke instead of the 1-task smoke.
    """
    if stage is Stage.SMOKE:
        split, size, nm = SMOKE_SPLIT, (SMOKE_SIZE_EXT if wide_smoke else SMOKE_SIZE), "smoke"
    elif stage is Stage.LITE:
        split, size, nm = LITE_SPLIT, LITE_SIZE, "lite"
    elif stage is Stage.SCORED:
        split, size, nm = SCORED_SPLIT, SCORED_SIZE, "scored96"
    else:  # pragma: no cover - exhaustive
        raise ValueError(f"unknown stage: {stage}")

    pool = available_by_split.get(split)
    if pool is None:
        raise KeyError(
            f"no task-id pool for split '{split}' (needed by stage '{stage.value}'); "
            f"provide load_task_ids('{split}') in available_by_split"
        )
    return select_subset(nm, split, size, pool, metadata=metadata, seed=seed)


# ==================================================================================================
# Run + persist a single stage.
# ==================================================================================================


@dataclass(frozen=True, slots=True)
class StageRunResult:
    """One execution of a funnel stage (one BenchmarkReport) + where it was persisted."""

    label: str
    stage: str
    run_index: int
    subset_hash: str
    report: BenchmarkReport
    results_path: str | None  # None when not persisted (e.g. in-memory test)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "stage": self.stage,
            "run_index": self.run_index,
            "subset_hash": self.subset_hash,
            "results_path": self.results_path,
            "report": self.report.as_dict(),
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_stage(
    *,
    label: str,
    stage: Stage | str,
    subset: SubsetSpec,
    model_factory: ModelFactory,
    sandbox_factory: SandboxFactory,
    config: LoopConfig | None = None,
    run_index: int = 1,
    results_dir: Path | str | None = None,
    endpoint: str | None = None,
    model_id: str | None = None,
    chat_template_kwargs: dict[str, object] | None = None,
) -> StageRunResult:
    """Run one funnel stage over ``subset`` and (optionally) persist the BenchmarkReport.

    The persisted report embeds model, config, frozen subset, UTC timestamp, diagnostics, and every
    per-task row required by the launch plan and rerun/early-stop processing.
    """
    from localbench.scoring.agentic_exec.execution_contract import assert_execution_contract

    assert_execution_contract()
    stage_val = stage.value if isinstance(stage, Stage) else str(stage)
    cfg = config or LoopConfig()

    report = run_appworld_c_benchmark(
        task_ids=list(subset.task_ids),
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
        config=cfg,
    )

    results_path: str | None = None
    if results_dir is not None:
        results_path = _persist_report(
            results_dir=Path(results_dir),
            label=label,
            stage=stage_val,
            run_index=run_index,
            subset=subset,
            report=report,
            config=cfg,
            endpoint=endpoint,
            model_id=model_id,
            chat_template_kwargs=chat_template_kwargs,
        )

    return StageRunResult(
        label=label,
        stage=stage_val,
        run_index=run_index,
        subset_hash=subset.manifest_hash,
        report=report,
        results_path=results_path,
    )


def _persist_report(
    *,
    results_dir: Path,
    label: str,
    stage: str,
    run_index: int,
    subset: SubsetSpec,
    report: BenchmarkReport,
    config: LoopConfig,
    endpoint: str | None,
    model_id: str | None,
    chat_template_kwargs: dict[str, object] | None = None,
) -> str:
    results_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_slug(label)}.{stage}.run{run_index}.json"
    path = results_dir / fname
    doc = {
        "schema": "appworld-c-funnel-run/v1",
        "written_at": _utc_now_iso(),
        "label": label,
        "endpoint": endpoint,
        "model_id": model_id,
        # The per-request chat-template kwargs that engaged native thinking (e.g.
        # {"enable_thinking": true}) — recorded so a scored run's reasoning mode is provenanced.
        "chat_template_kwargs": chat_template_kwargs,
        "stage": stage,
        "run_index": run_index,
        "loop_config": {
            "max_turns": config.max_turns,
            "max_output_tokens_per_turn": config.max_output_tokens_per_turn,
            "max_observation_chars": config.max_observation_chars,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "seed": config.seed,
        },
        "subset": subset.as_dict(),
        "attestations": _report_attestations(report),
        "report": report.as_dict(),
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return str(path)


def _contract_task_identity(task_ids: tuple[str, ...]) -> dict[str, str]:
    """Expose signed full-set hashes without rereading task data during persistence."""
    from localbench.scoring.agentic_exec.execution_contract import load_execution_contract

    payload = load_execution_contract()["payload"]
    if not isinstance(payload, dict):
        return {}
    identity = payload.get("task_identity")
    if not isinstance(identity, dict) or list(task_ids) != identity.get("ordered_task_ids"):
        return {}
    return {
        key: value
        for key in (
            "ordered_task_ids_sha256",
            "selection_recipe_sha256",
            "semantic_task_sha256",
        )
        if isinstance((value := identity.get(key)), str)
    }
def _report_attestations(report: BenchmarkReport) -> list[dict[str, Any]]:
    return [result.attestation for result in report.results if result.attestation is not None]


# ==================================================================================================
# Reruns + run-to-run delta (the LOCKED 2-rerun rule with a 3rd on >5pp drift).
# ==================================================================================================

# LOCKED: 2 full reruns for a displayed row; if max abs delta on the headline metric (ASR) exceeds
# this threshold (in percentage points), add a 3rd run and report the mean.
RERUN_BASE_COUNT = 2
DELTA_TRIGGER_PP = 5.0


@dataclass(frozen=True, slots=True)
class RerunAggregate:
    """Aggregate over the reruns of one displayed row: the ASR series + drift + mean."""

    label: str
    stage: str
    subset_hash: str
    asr_series: tuple[float, ...]            # ASR of each run, in order
    max_abs_delta_pp: float                  # max pairwise abs delta on ASR, in percentage points
    triggered_third_run: bool                # did the >5pp rule fire?
    mean_asr: float
    runs: tuple[StageRunResult, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "stage": self.stage,
            "subset_hash": self.subset_hash,
            "asr_series": list(self.asr_series),
            "max_abs_delta_pp": self.max_abs_delta_pp,
            "triggered_third_run": self.triggered_third_run,
            "mean_asr": self.mean_asr,
            "runs": [r.as_dict() for r in self.runs],
        }


def _max_abs_delta_pp(values: Sequence[float]) -> float:
    """Max pairwise absolute delta across a series, expressed in percentage points (ASR*100)."""
    if len(values) < 2:
        return 0.0
    pts = [v * 100.0 for v in values]
    return max(pts) - min(pts)


def run_with_reruns(
    *,
    label: str,
    stage: Stage | str,
    subset: SubsetSpec,
    model_factory: ModelFactory,
    sandbox_factory: SandboxFactory,
    config: LoopConfig | None = None,
    results_dir: Path | str | None = None,
    base_count: int = RERUN_BASE_COUNT,
    delta_trigger_pp: float = DELTA_TRIGGER_PP,
    endpoint: str | None = None,
    model_id: str | None = None,
    chat_template_kwargs: dict[str, object] | None = None,
) -> RerunAggregate:
    """Run a displayed row ``base_count`` times; add a 3rd run iff ASR drift exceeds the threshold.

    Implements the LOCKED repeatability rule. Each run gets its own persisted JSON (run1/run2/…);
    the returned aggregate reports the ASR series, the max abs run-to-run delta in percentage
    points, whether the 3rd run fired, and the mean ASR. ``base_count`` is the number of runs that
    constitute a "displayed row" (LOCKED = 2; the launch plan also runs the FIRST full pass + 2
    reruns, but the freeze/early-stop logic only needs the repeatability series, which this owns).
    """
    from localbench.scoring.agentic_exec.execution_contract import assert_execution_contract

    assert_execution_contract()
    runs: list[StageRunResult] = []
    for k in range(1, base_count + 1):
        runs.append(
            run_stage(
                label=label,
                stage=stage,
                subset=subset,
                model_factory=model_factory,
                sandbox_factory=sandbox_factory,
                config=config,
                run_index=k,
                results_dir=results_dir,
                endpoint=endpoint,
                model_id=model_id,
                chat_template_kwargs=chat_template_kwargs,
            )
        )

    asr = [r.report.agentic_success_rate for r in runs]
    delta = _max_abs_delta_pp(asr)
    triggered = delta > delta_trigger_pp
    if triggered:
        runs.append(
            run_stage(
                label=label,
                stage=stage,
                subset=subset,
                model_factory=model_factory,
                sandbox_factory=sandbox_factory,
                config=config,
                run_index=base_count + 1,
                results_dir=results_dir,
                endpoint=endpoint,
                model_id=model_id,
                chat_template_kwargs=chat_template_kwargs,
            )
        )
        asr = [r.report.agentic_success_rate for r in runs]
        delta = _max_abs_delta_pp(asr)  # recompute over all runs incl. the 3rd

    stage_val = stage.value if isinstance(stage, Stage) else str(stage)
    mean_asr = sum(asr) / len(asr) if asr else 0.0
    return RerunAggregate(
        label=label,
        stage=stage_val,
        subset_hash=subset.manifest_hash,
        asr_series=tuple(asr),
        max_abs_delta_pp=delta,
        triggered_third_run=triggered,
        mean_asr=mean_asr,
        runs=tuple(runs),
    )


# ==================================================================================================
# Early-stop check (the LOCKED stop conditions for a scored sweep).
# ==================================================================================================

# 1 task on a 96-set ~= 1.04pp. "Near-zero" / "near-perfect" use a small task-count tolerance.
NEAR_ZERO_FRACTION = 0.02   # <= ~2 of 96 succeed
NEAR_PERFECT_FRACTION = 0.98  # >= ~94 of 96 succeed
# "Failures dominated by harness mechanics": parser(format) + syntax + runtime + cap account for
# this fraction (or more) of all NON-success tasks -> the column is measuring harness artifacts,
# not interactive API-coding skill (the construct-validity red flag the oracle called out).
HARNESS_FAILURE_DOMINANCE = 0.80
# "All within noise" across a set of displayed rows: the spread of ASR across models is under this
# many percentage points -> ranks are not meaningful, stop fine-grained comparison.
WITHIN_NOISE_SPREAD_PP = 3.0


@dataclass(frozen=True, slots=True)
class EarlyStopSignal:
    """Verdict of the early-stop check for one report (plus optional cross-model spread)."""

    should_stop: bool
    reasons: tuple[str, ...]
    asr: float
    harness_failure_share: float  # share of non-success tasks attributable to harness mechanics

    def as_dict(self) -> dict[str, Any]:
        return {
            "should_stop": self.should_stop,
            "reasons": list(self.reasons),
            "asr": self.asr,
            "harness_failure_share": self.harness_failure_share,
        }


def _harness_failure_share(report: BenchmarkReport) -> float:
    """Share of NON-success tasks whose TERMINAL OUTCOME is a harness mechanic.

    Counts ONLY tasks that never produced a gradeable answer — cap_exceeded + no_final_answer +
    harness_error. A FAILURE outcome means the model finalized and AppWorld's evaluate() returned
    False: a genuine on-merits failure, NOT harness friction, even if the trajectory carried
    recoverable format/syntax/runtime errors along the way (those surface separately as rates).
    Keying on terminal outcomes — not error-presence — is the fix for the over-flagging seen on the
    wide-smoke, where genuinely-attempted-but-failed tasks were mislabelled "harness friction"
    (e.g. Qwen: 5 genuine failures + 1 success reported share 1.00; the correct share is 0.00).
    """
    non_success = [r for r in report.results if not r.success]
    if not non_success:
        return 0.0
    harness_dominated = sum(
        1
        for r in non_success
        if r.outcome
        in (TaskOutcome.CAP_EXCEEDED, TaskOutcome.NO_FINAL_ANSWER, TaskOutcome.HARNESS_ERROR)
    )
    return harness_dominated / len(non_success)


def evaluate_early_stop(
    report: BenchmarkReport,
    *,
    cross_model_asr: Sequence[float] | None = None,
    near_zero_fraction: float = NEAR_ZERO_FRACTION,
    near_perfect_fraction: float = NEAR_PERFECT_FRACTION,
    harness_failure_dominance: float = HARNESS_FAILURE_DOMINANCE,
    within_noise_spread_pp: float = WITHIN_NOISE_SPREAD_PP,
) -> EarlyStopSignal:
    """Decide whether to early-stop a scored sweep, with human-readable reasons.

    Fires (any condition):
      * **near-zero** — best ASR ~0 (the model can't do the task; nothing to rank);
      * **near-perfect / saturated** — ASR ~1 (no discrimination; the column adds no signal);
      * **harness-dominated failures** — >= ``harness_failure_dominance`` of non-success tasks end
        in cap/no-final/harness-error or carry parser/syntax/runtime errors (construct-validity
        red flag: measuring harness friction, not API-coding skill);
      * **all within noise** — if ``cross_model_asr`` is given and its spread is under
        ``within_noise_spread_pp`` percentage points (ranks not meaningful).

    Does NOT itself decide on "order just mirrors IFBench+code-proxy / canary regression" — those
    need cross-axis correlation + the canary suite, computed by the caller; this function reports
    the loop-internal conditions it can see from one report (+ optional ASR spread).
    """
    reasons: list[str] = []
    asr = report.agentic_success_rate

    if asr <= near_zero_fraction:
        reasons.append(
            f"near_zero: ASR {asr:.3f} <= {near_zero_fraction:.3f} (no measurable skill to rank)"
        )
    if asr >= near_perfect_fraction:
        reasons.append(
            f"near_perfect: ASR {asr:.3f} >= {near_perfect_fraction:.3f} (saturated, no discrimination)"
        )

    hshare = _harness_failure_share(report)
    if hshare >= harness_failure_dominance and report.tasks_succeeded < report.tasks_total:
        reasons.append(
            f"harness_dominated: {hshare:.2f} of non-success tasks ended in "
            f"cap/no-final/harness-error (terminal harness outcomes) "
            f">= {harness_failure_dominance:.2f} (measuring harness friction, not skill)"
        )

    if cross_model_asr is not None and len(cross_model_asr) >= 2:
        spread = _max_abs_delta_pp(cross_model_asr)
        if spread < within_noise_spread_pp:
            reasons.append(
                f"within_noise: cross-model ASR spread {spread:.2f}pp < "
                f"{within_noise_spread_pp:.2f}pp (ranks not meaningful)"
            )

    return EarlyStopSignal(
        should_stop=bool(reasons),
        reasons=tuple(reasons),
        asr=asr,
        harness_failure_share=hshare,
    )


def _slug(text: str) -> str:
    """Filesystem-safe label slug (keep it readable, no surprises in filenames)."""
    keep = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        elif ch in (" ", "/", "\\", ":"):
            keep.append("-")
    slug = "".join(keep).strip("-")
    return slug or "model"


# A model-factory builder kept here (not in chat_client) so the funnel is the single import the
# GPU runner needs. Lazy import keeps this module import-safe where the client is unused.
def chat_client_factory(
    base_url: str,
    model: str,
    api_key: str = "",
    timeout_s: float = 600.0,
    chat_template_kwargs: dict[str, object] | None = None,
) -> ModelFactory:
    """``task_id -> ChatCompletionsClient(base_url, model)`` for the GPU run's ``model_factory``.

    Imported lazily so ``funnel`` stays import-safe even if the client module changes; the client
    itself is stdlib-only, so this is cheap. The returned factory ignores ``task_id`` (the client
    is stateless across tasks) but matches the ``ModelFactory`` signature the benchmark expects.
    ``chat_template_kwargs`` (e.g. ``{"enable_thinking": True}``) is forwarded per-request so the
    loop engages a thinking model's native reasoning reproducibly (not via a server launch flag).
    ``base_url`` may be the server root OR the OpenAI-style base including ``/v1`` — the client
    normalizes so both yield ``ROOT/v1/chat/completions`` (a double ``/v1`` 404s silently).
    """
    from localbench.scoring.agentic_exec.chat_client import (  # noqa: PLC0415 — lazy by design.
        ChatCompletionsClient,
    )

    def _factory(_task_id: str) -> ChatCompletionsClient:
        return ChatCompletionsClient(
            base_url, model, api_key=api_key, timeout_s=timeout_s,
            chat_template_kwargs=chat_template_kwargs,
        )

    return _factory


__all__ = [
    "Stage",
    "TaskMeta",
    "SubsetSpec",
    "select_subset",
    "subset_for_stage",
    "StageRunResult",
    "run_stage",
    "RerunAggregate",
    "run_with_reruns",
    "EarlyStopSignal",
    "evaluate_early_stop",
    "chat_client_factory",
    "SMOKE_SPLIT",
    "LITE_SPLIT",
    "SCORED_SPLIT",
    "SMOKE_SIZE",
    "SMOKE_SIZE_EXT",
    "LITE_SIZE",
    "SCORED_SIZE",
    "SELECTION_SEED",
    "RERUN_BASE_COUNT",
    "DELTA_TRIGGER_PP",
]

# Type alias re-export for runner convenience.
ModelFactoryT = Callable[[str], Any]
