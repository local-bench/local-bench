from __future__ import annotations

from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.verify import verify_bundle_offline

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_same_valid_bundle_verified_twice_writes_byte_identical_json(tmp_path: Path) -> None:
    # Given: a valid bundle and two output paths.
    fixtures = await build_submission_fixtures(tmp_path)
    bundle = tmp_path / "valid.lbsub.zip"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=bundle,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying twice.
    verify_bundle_offline(bundle, suite_dir=fixtures.suite_dir, out_path=first)
    verify_bundle_offline(bundle, suite_dir=fixtures.suite_dir, out_path=second)

    # Then: the verification JSON is byte-identical.
    assert first.read_bytes() == second.read_bytes()
