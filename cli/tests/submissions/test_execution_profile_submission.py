from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_pack_carries_structured_execution_profile_in_signed_payload(
    tmp_path: Path,
) -> None:
    # Given: a completed run with a probe-verified public execution profile.
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    execution_profile = {
        "id": "generic_think_tags_8192_v1",
        "selection_policy_id": "gguf-effective-template-v1",
        "selection_reason": "gguf_generic_think_confirmed",
        "template_source": "gguf-default",
        "template_sha256": "a" * 64,
        "chat_template_kwargs": {"enable_thinking": True},
        "answer_stops": ["<|im_end|>"],
        "runtime_probe_passed": True,
        "prompt_renderer_engine": "llama.cpp.apply-template",
    }
    run["manifest"]["execution_profile"] = execution_profile
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")

    # When: the submission bundle is packed and signed.
    manifest = pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=tmp_path / "profile.lbsub.zip",
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # Then: the signed payload carries the structured disclosure verbatim.
    assert manifest["payload"]["execution_profile"] == execution_profile
