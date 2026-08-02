from __future__ import annotations

from pathlib import Path

from localbench.check.kld import (
    KldRequest,
    build_kld_command,
    first_reference_tokens,
    run_kld_subpass,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kld"


def test_first_reference_tokens_is_exact_and_deterministic() -> None:
    tokens = list(range(20))

    assert first_reference_tokens(tokens, count=8) == tuple(range(8))
    assert first_reference_tokens(tokens, count=8) == first_reference_tokens(tokens, count=8)


def test_kld_commands_encode_pinned_two_phase_segment_contract(tmp_path: Path) -> None:
    binary = tmp_path / "llama-perplexity.exe"
    model = tmp_path / "model.gguf"
    corpus = tmp_path / "corpus.txt"
    logits = tmp_path / "reference.kld"

    reference = build_kld_command(binary, model=model, corpus=corpus, logits=logits, reference=True)
    candidate = build_kld_command(binary, model=model, corpus=corpus, logits=logits, reference=False)

    assert reference[-2:] == ["--kl-divergence-base", str(logits)]
    assert candidate[-3:] == ["--kl-divergence-base", str(logits), "--kl-divergence"]
    for command in (reference, candidate):
        assert command[command.index("--ctx-size") + 1] == "4096"
        assert command[command.index("--chunks") + 1] == "64"
        assert command[command.index("--ppl-stride") + 1] == "4096"


def test_kld_missing_reference_is_unavailable_and_never_changes_verdict(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.gguf"
    _ = candidate.write_bytes(b"candidate")

    result = run_kld_subpass(
        KldRequest(
            binary=tmp_path / "llama-perplexity.exe",
            reference=None,
            candidate=candidate,
            corpus=tmp_path / "corpus.txt",
            work_dir=tmp_path / "kld",
            bands=None,
        )
    )

    assert result["status"] == "unavailable"
    assert result["verdict_effect"] == "none"


def test_kld_fixture_run_formats_four_significant_figures_and_records_provenance(tmp_path: Path) -> None:
    binary = tmp_path / "llama-perplexity.exe"
    reference = tmp_path / "reference.gguf"
    candidate = tmp_path / "candidate.gguf"
    corpus = tmp_path / "corpus.txt"
    _ = binary.write_bytes(b"binary")
    _ = reference.write_bytes(b"reference")
    _ = candidate.write_bytes(b"candidate")
    _ = corpus.write_bytes(b"pinned corpus")
    calls: list[list[str]] = []

    def runner(command: list[str]) -> str:
        calls.append(command)
        if "--help" in command:
            return "--kl-divergence --kl-divergence-base --ctx-size --chunks --ppl-stride"
        if "--kl-divergence" in command:
            return (_FIXTURES / "kld-Q4_K_M-vs-bf16.log").read_text(encoding="utf-8")
        return "reference logits saved"

    result = run_kld_subpass(
        KldRequest(
            binary=binary,
            reference=reference,
            candidate=candidate,
            corpus=corpus,
            work_dir=tmp_path / "kld",
            bands={"mean_kld_max": 0.915, "p95_kld_max": 4.0, "p99_kld_max": 9.0, "top_token_agreement_min": 66.0},
        ),
        runner=runner,
    )

    assert result["status"] == "in-band"
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics == {
        "mean_kld": 0.9149,
        "p95_kld": 3.907,
        "p99_kld": 8.561,
        "top_token_agreement_rate": 67.06,
    }
    provenance = result["provenance"]
    assert isinstance(provenance, dict)
    artifact_hashes = provenance["artifact_sha256s"]
    binary_hash = provenance["binary_sha256"]
    corpus_hash = provenance["corpus_sha256"]
    assert isinstance(artifact_hashes, dict)
    assert isinstance(binary_hash, str)
    assert isinstance(corpus_hash, str)
    assert set(artifact_hashes) == {"candidate", "reference"}
    assert len(binary_hash) == 64
    assert len(corpus_hash) == 64
    assert provenance["parameters"] == {
        "accumulation": "fp32",
        "context_tokens": 4096,
        "direction": "KL(reference||candidate)",
        "fresh_context_per_segment": True,
        "overlap": 0,
        "segments": 64,
        "tokens": 262144,
    }
    assert len(calls) == 3
