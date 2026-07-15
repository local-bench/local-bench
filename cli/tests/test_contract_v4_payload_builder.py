from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    load_execution_contract,
    validate_execution_contract_payload,
)
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity
from localbench.scoring.agentic_exec.wsl_worker import _PIN_ENV
from localbench.submissions.canon import canonical_json_hash
from scripts.build_contract_v4_payload import (
    V4_CONTRACT_ID,
    build_v4_payload,
)


_CITATION_PATTERN = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")
_REPO_ROOT = Path(__file__).parents[2]
_EXCERPT_PATH = (
    _REPO_ROOT
    / "cli/src/localbench/data/contracts/agentic-task-identity-run-excerpts-v1.json"
)


def _load_run_excerpts() -> JsonObject:
    payload = json.loads(_EXCERPT_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_v4_payload_builder_is_deterministic_and_preserves_contract_store(
    tmp_path: Path,
) -> None:
    # Given: the immutable signed v3 base and a byte snapshot of the production contract store.
    contracts = Path(__file__).parents[1] / "src/localbench/data/contracts"
    before = {path.name: path.read_bytes() for path in contracts.iterdir() if path.is_file()}
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    script = Path(__file__).parents[2] / "scripts/build_contract_v4_payload.py"

    # When: the unsigned draft is regenerated twice from current sources.
    first_run = subprocess.run(
        [sys.executable, str(script), "--output", str(first)],
        check=True,
        capture_output=True,
        text=True,
    )
    second_run = subprocess.run(
        [sys.executable, str(script), "--output", str(second)],
        check=True,
        capture_output=True,
        text=True,
    )

    # Then: bytes and printed hashes match, the loader accepts the unsigned payload shape,
    # and no production contract byte was touched.
    assert first.read_bytes() == second.read_bytes()
    assert first_run.stdout == second_run.stdout
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    validate_execution_contract_payload(payload, expected_contract_id=V4_CONTRACT_ID)
    assert first_run.stdout.strip() == f"payload_sha256={canonical_json_hash(payload)}"
    assert "signature" not in payload
    assert {path.name: path.read_bytes() for path in contracts.iterdir() if path.is_file()} == before


def test_v4_payload_builder_carries_gate_status_and_v3_lineage_verbatim() -> None:
    # Given / When: both authorized gate-status payload variants are built.
    default = build_v4_payload(gate_status="not-yet-passed")
    passed = build_v4_payload(
        gate_status="passed-current-repo-harness-vs-appliance"
    )

    # Then: only the requested status changes and v3 is the direct predecessor.
    assert default["packaging_correctness_gate"]["status"] == "not-yet-passed"
    assert passed["packaging_correctness_gate"]["status"] == (
        "passed-current-repo-harness-vs-appliance"
    )
    assert default["identity_lineage"]["predecessor_contract_id"] == CONTRACT_ID
    assert default["identity_lineage"]["predecessor_payload_sha256"] == (
        load_execution_contract()["payload_sha256"]
    )
    assert default["covered_behavior"]["run_aggregation"] == (
        load_execution_contract()["payload"]["covered_behavior"]["run_aggregation"]
    )


def test_v4_payload_builder_refreshes_worker_content_identity_at_head() -> None:
    current_identity = worker_implementation_identity()
    predecessor_sandbox = dict(load_execution_contract()["payload"]["sandbox_identity"])
    payload = build_v4_payload(gate_status="not-yet-passed")

    assert payload["sandbox_identity"]["worker_content_sha256"] == (
        current_identity["worker_content_sha256"]
    )
    predecessor_sandbox["worker_content_sha256"] = current_identity["worker_content_sha256"]
    assert payload["sandbox_identity"] == predecessor_sandbox
    assert str(payload["provenance"]["sandbox_identity.worker_content_sha256"]).startswith(
        "scripts/build_contract_v4_payload.py:"
    )


def test_v4_payload_builder_env_pins_match_worker_startup_assertion() -> None:
    payload = build_v4_payload(gate_status="not-yet-passed")

    assert payload["appworld_identity"]["env_pins"] == _PIN_ENV


def test_v4_payload_builder_refuses_unknown_gate_status(tmp_path: Path) -> None:
    # Given: an unsupported packaging-gate status.
    script = Path(__file__).parents[2] / "scripts/build_contract_v4_payload.py"

    # When: the CLI parser receives it.
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--gate-status",
            "builder-invented-status",
            "--output",
            str(tmp_path / "refused.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: generation fails before writing an artifact.
    assert completed.returncode != 0
    assert not (tmp_path / "refused.json").exists()


def test_v4_payload_provenance_cites_only_tracked_in_range_sources() -> None:
    # Given: the default unsigned v4 payload inherited from signed v3 provenance.
    payload = build_v4_payload(gate_status="not-yet-passed")
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)

    # When: every leaf citation is parsed into a unique source span.
    references: set[tuple[str, int, int]] = set()
    for citation in provenance.values():
        assert isinstance(citation, str)
        for ref in citation.split(";"):
            match = _CITATION_PATTERN.fullmatch(ref)
            assert match is not None, ref
            start = int(match.group(2))
            references.add((match.group(1), start, int(match.group(3) or start)))

    # Then: every cited source is in Git and every declared span exists.
    for source_name, start, end in references:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", source_name],
            cwd=_REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert tracked.returncode == 0, source_name
        lines = (_REPO_ROOT / source_name).read_text(encoding="utf-8").splitlines()
        assert 1 <= start <= end <= len(lines), f"{source_name}:{start}-{end}"


def test_task_identity_run_excerpt_schema_and_span_widths() -> None:
    # Given / When: the tracked raw-run excerpt is parsed.
    payload = _load_run_excerpts()

    # Then: required schema fields exist and every verbatim span has its declared width.
    assert payload["schema"] == "localbench.contract_run_excerpts.v1"
    assert isinstance(payload["purpose"], str)
    sources = payload["sources"]
    assert isinstance(sources, list) and sources
    for source in sources:
        assert isinstance(source, dict)
        assert isinstance(source["path"], str)
        assert isinstance(source["raw_file_sha256"], str)
        spans = source["spans"]
        assert isinstance(spans, list) and spans
        for span in spans:
            assert isinstance(span, dict)
            start, end = (int(part) for part in str(span["lines"]).split("-"))
            verbatim = span["verbatim"]
            assert isinstance(verbatim, list)
            assert len(verbatim) == end - start + 1


def test_task_identity_run_excerpts_match_raw_sources_when_available() -> None:
    # Given: the tracked excerpts and any locally retained, gitignored raw runs.
    payload = _load_run_excerpts()
    sources = payload["sources"]
    assert isinstance(sources, list)
    missing = [
        str(source["path"])
        for source in sources
        if isinstance(source, dict) and not (_REPO_ROOT / str(source["path"])).is_file()
    ]
    if missing:
        pytest.skip(f"raw-run provenance sources absent from fresh checkout: {', '.join(missing)}")

    # When / Then: every retained source digest and cited line is compared byte-for-byte.
    for source in sources:
        assert isinstance(source, dict)
        raw_path = _REPO_ROOT / str(source["path"])
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == source["raw_file_sha256"]
        raw_lines = raw_path.read_text(encoding="utf-8").splitlines()
        spans = source["spans"]
        assert isinstance(spans, list)
        for span in spans:
            assert isinstance(span, dict)
            start, end = (int(part) for part in str(span["lines"]).split("-"))
            assert span["verbatim"] == raw_lines[start - 1 : end]
