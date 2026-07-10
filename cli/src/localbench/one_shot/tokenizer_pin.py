from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from localbench._types import JsonObject
from localbench.one_shot.download import HfDownloadClient, HuggingFaceDownloadClient
from localbench.one_shot.plan_lock import OneShotPlanLockContext, read_resume_plan_lock, validate_or_write_plan_lock
from localbench.one_shot.preflight import PlanLockMismatch
from localbench.one_shot.types import OneShotSuiteIdentity, ResolvedOneShotModel


@dataclass(frozen=True, slots=True)
class TokenizerPlanRequest:
    resolved: ResolvedOneShotModel
    run_root: Path
    resume: Path | None
    cli_version: str
    hf_client: HfDownloadClient | None
    suite_identity: OneShotSuiteIdentity


@dataclass(frozen=True, slots=True)
class TokenizerPlan:
    resolved: ResolvedOneShotModel
    context: OneShotPlanLockContext
    repo_id: str
    revision: str


@dataclass(frozen=True, slots=True)
class _TokenizerPin:
    repo_id: str
    revision: str
    resolved_at_run_start: bool


def prepare_tokenizer_plan(request: TokenizerPlanRequest) -> TokenizerPlan:
    resume_plan = read_resume_plan_lock(request.run_root, resume=request.resume)
    pin = _tokenizer_pin(request.resolved, request.hf_client, resume_plan)
    resolved = replace(request.resolved, tokenizer_repo=pin.repo_id, tokenizer_revision=pin.revision)
    if pin.resolved_at_run_start:
        print(f"tokenizer  {pin.repo_id}@{pin.revision[:12]} (pinned at run start)")
    context = OneShotPlanLockContext(
        run_root=request.run_root,
        resolved=resolved,
        cli_version=request.cli_version,
        tokenizer_repo=pin.repo_id,
        tokenizer_revision=pin.revision,
        suite_identity=request.suite_identity,
    )
    validate_or_write_plan_lock(context, resume=request.resume)
    return TokenizerPlan(resolved=resolved, context=context, repo_id=pin.repo_id, revision=pin.revision)


def _tokenizer_pin(
    resolved: ResolvedOneShotModel,
    hf_client: HfDownloadClient | None,
    resume_plan: JsonObject | None,
) -> _TokenizerPin:
    locked = _locked_tokenizer_pin(resolved, resume_plan)
    if locked is not None:
        return locked
    repo_id = resolved.tokenizer_repo or resolved.artifact.repo_id
    if resolved.tokenizer_revision is not None:
        return _TokenizerPin(repo_id=repo_id, revision=resolved.tokenizer_revision, resolved_at_run_start=False)
    if repo_id == resolved.artifact.repo_id:
        return _TokenizerPin(repo_id=repo_id, revision=resolved.artifact.revision, resolved_at_run_start=False)
    client = hf_client or HuggingFaceDownloadClient()
    revision = client.resolve_model_revision(repo_id=repo_id)
    return _TokenizerPin(repo_id=repo_id, revision=revision, resolved_at_run_start=True)


def _locked_tokenizer_pin(
    resolved: ResolvedOneShotModel,
    resume_plan: JsonObject | None,
) -> _TokenizerPin | None:
    if resume_plan is None:
        return None
    revision = resume_plan.get("tokenizer_revision")
    if revision is None:
        return None
    if not isinstance(revision, str) or revision == "":
        raise PlanLockMismatch("plan.lock.json tokenizer_revision must be a non-empty string")
    repo = resume_plan.get("tokenizer_repo")
    repo_id = repo if isinstance(repo, str) and repo else resolved.tokenizer_repo or resolved.artifact.repo_id
    return _TokenizerPin(repo_id=repo_id, revision=revision, resolved_at_run_start=False)
