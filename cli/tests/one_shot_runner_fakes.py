from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.one_shot.download import DownloadError
from localbench.one_shot.runner import OneShotRunnerDeps
from localbench.one_shot.serve_plan import STATIC_EXEC_BENCHES
from localbench.one_shot.types import STATIC_EXEC_SUITE_IDENTITY
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.submissions.submit_run import SubmitRunOptions, SubmitRunResult
from one_shot_fixtures import (
    MODEL_BYTES,
    MODEL_SHA,
    REV_A,
    TOKENIZER_REV_A,
    catalog_with_artifacts,
    one_shot_artifact,
)


class _CatalogLoader:
    def __init__(self, tokenizer_repo: str = "owner/base-model") -> None:
        self._tokenizer_repo = tokenizer_repo

    def load(self, *, requested_model: str, site: str) -> dict[str, object]:
        assert requested_model == "qwen3-6-27b"
        assert site == "https://local-bench.ai"
        return catalog_with_artifacts(
            tokenizer_repo=self._tokenizer_repo,
            artifacts=[
                {
                    "quant_label": "Q4_K_M",
                    "repo_id": "owner/model-gguf",
                    "filename": "model-q4.gguf",
                    "revision": REV_A,
                    "sha256": MODEL_SHA,
                    "size_bytes": len(MODEL_BYTES),
                    "vram_required_gb_32k": 22.0,
                },
            ],
        )


class _PreflightHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((url, payload))
        return {"publishable": True, "reasons": []}


class _HfClient:
    def __init__(self) -> None:
        self.tokenizer_revision = TOKENIZER_REV_A
        self.tokenizer_revision_error: DownloadError | None = None
        self.revision_calls: list[str] = []
        self.snapshot_calls: list[dict[str, object]] = []

    def download_file(self, *, repo_id: str, filename: str, revision: str, destination: Path) -> None:
        assert repo_id in {"owner/model-gguf", "owner/raw-gguf"}
        assert filename == "model-q4.gguf"
        assert revision == REV_A
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(MODEL_BYTES)

    def resolve_model_revision(self, *, repo_id: str) -> str:
        self.revision_calls.append(repo_id)
        if self.tokenizer_revision_error is not None:
            raise self.tokenizer_revision_error
        return self.tokenizer_revision

    def snapshot_download(self, *, repo_id: str, revision: str, destination: Path) -> Path:
        assert repo_id in {"owner/base-model", "owner/model-gguf", "owner/raw-gguf"}
        self.snapshot_calls.append({"repo_id": repo_id, "revision": revision, "destination": destination})
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "tokenizer.json").write_text("{}", encoding="utf-8")
        (destination / "tokenizer_config.json").write_text(
            json.dumps({"chat_template": "{{ messages }}"}),
            encoding="utf-8",
        )
        return destination


class _BenchRunner:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.options = None
        self.raise_keyboard_interrupt = False

    def __call__(self, options) -> dict[str, object]:
        if self.raise_keyboard_interrupt:
            raise KeyboardInterrupt
        self.options = options
        run_path = self._run_dir / "localbench-run.json"
        record: dict[str, object] = {"scores": {"headline_score": 0.73}, "warnings": []}
        if options.suite == STATIC_EXEC_SUITE_IDENTITY.release_id:
            record.update({
                "manifest": {
                    "suite": {
                        "coverage_profile_id": "static-exec-5axis-v1",
                        "suite_release_id": STATIC_EXEC_SUITE_IDENTITY.release_id,
                        "suite_manifest_sha256": STATIC_EXEC_SUITE_IDENTITY.manifest_sha256,
                    },
                },
                "benches": {bench: {} for bench in STATIC_EXEC_BENCHES},
            })
        run_path.write_text(json.dumps(record), encoding="utf-8")
        return record


class _Submitter:
    def __init__(self) -> None:
        self.calls: list[SubmitRunOptions] = []

    def __call__(self, options: SubmitRunOptions) -> SubmitRunResult:
        self.calls.append(options)
        return SubmitRunResult(exit_code=0, lines=("submission sub_fake",))


class _RawArtifactResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def resolve_raw_artifact(self, *, repo_id: str, quant: str | None):
        self.calls.append((repo_id, quant))
        return one_shot_artifact(
            repo_id=repo_id,
            quant_label=quant or "Q4_K_M",
            sha256=MODEL_SHA,
            size_bytes=len(MODEL_BYTES),
            vram_required_gb_8k=None,
            vram_required_gb_32k=None,
        )


def _agentic_preflight(_options, _root: Path) -> WslPreflightResult:
    return WslPreflightResult(identity={"fixture": True}, task_ids=("fixture_task",))


def _deps(tmp_path: Path) -> OneShotRunnerDeps:
    return OneShotRunnerDeps(
        catalog_loader=_CatalogLoader(),
        preflight_http=_PreflightHttp(),
        hf_client=_HfClient(),
        bench_runner=_BenchRunner(tmp_path),
        submitter=_Submitter(),
        raw_artifact_resolver=_RawArtifactResolver(),
        agentic_preflight=_agentic_preflight,
    )


def _args(
    tmp_path: Path,
    *,
    one_shot_submit: bool | None = False,
    offline: bool = False,
    resume: Path | None = None,
    static_only: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        one_shot_model="qwen3-6-27b",
        yes=True,
        one_shot_submit=one_shot_submit,
        accept_suite_terms=True,
        quant="Q4_K_M",
        vram_gb=24.0,
        offline=offline,
        static_only=static_only,
        allow_sleep_risk=False,
        purge_model=False,
        llama_server_path=Path("llama-server.exe"),
        server_bin=None,
        out=None if resume is not None else tmp_path,
        resume=resume,
        cache_dir=None,
        suite_dir=(
            Path(__file__).resolve().parents[2]
            / "web"
            / "public"
            / "suites"
            / (
                "suite-v1-static-exec-5axis-v1"
                if static_only
                else "suite-v1-full-exec-6axis-v1"
            )
        ),
        suite_source=None,
        max_items=None,
        threads=8,
        threads_batch=8,
        wsl_venv_python="/opt/localbench/bin/python3",
        appworld_root="/srv/appworld",
        site="https://local-bench.ai",
        signing_key=None,
        display_name=None,
        bypass_token=None,
        bypass_token_file=None,
    )
