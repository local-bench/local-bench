#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx2[http2,brotli,zstd]",
#   "jinja2>=3.1",
#   "pydantic>=2.11",
#   "transformers==5.12.1",
#   "typer>=0.16",
# ]
# ///
# Run from the repository root with the exact tokenizer revision used by the
# comparison run:
# PYTHONPATH=cli/src uv run --script cli/tools/renderer_equivalence.py \
#   SUITE_CACHE AGENTIC_TRACE HF_TOKENIZER LLAMA_URL OUT --revision HF_REVISION

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import httpx2
import typer
from pydantic import ValidationError
from renderer_equivalence_cases import load_cases
from renderer_equivalence_support import (
    TEMPLATE_KWARGS,
    CaseResult,
    Config,
    HarnessError,
    compare,
    create_client,
    hf_render,
    llama_render,
)
from transformers import AutoTokenizer, PreTrainedTokenizerBase


def _run(config: Config) -> int:
    tokenizer: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(
        config.hf_tokenizer,
        revision=config.revision,
    )
    results: list[CaseResult] = []
    with create_client(config) as client:
        for case in load_cases(config):
            hf = hf_render(tokenizer, case, config.template_kwargs)
            llama = llama_render(client, case, config.template_kwargs)
            result = compare(hf, llama, case.name)
            results.append(result)
            typer.echo(f"{'PASS' if result.passed else 'FAIL'} {case.name}")
    passed = all(result.passed for result in results)
    evidence = {
        "schema": "localbench.renderer_equivalence.v1",
        "passed": passed,
        "claim_gate": "native-vs-gguf-delta-renderer-equivalence",
        "inputs": {
            "suite_cache": str(config.suite_cache.resolve()),
            "agentic_trace": str(config.agentic_trace.resolve()),
            "hf_tokenizer": config.hf_tokenizer,
            "revision": config.revision,
            "llama_url": config.llama_url,
            "tier": config.tier,
            "samples": config.samples,
            "chat_template_kwargs": config.template_kwargs,
        },
        "results": [asdict(result) for result in results],
    }
    config.out.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


def main(
    suite_cache: Path,
    agentic_trace: Path,
    hf_tokenizer: str,
    llama_url: str,
    out: Path,
    revision: str = typer.Option(...),
    tier: str = typer.Option("standard"),
    samples: int = typer.Option(8, min=1),
    template_kwargs: str = typer.Option('{"enable_thinking":true}'),
) -> None:
    """Run the renderer-equivalence claim gate and write JSON evidence."""
    try:
        kwargs = TEMPLATE_KWARGS.validate_json(template_kwargs)
        code = _run(
            Config(
                suite_cache=suite_cache,
                agentic_trace=agentic_trace,
                hf_tokenizer=hf_tokenizer,
                revision=revision,
                llama_url=llama_url.rstrip("/"),
                out=out,
                tier=tier,
                samples=samples,
                template_kwargs=kwargs,
            )
        )
    except (HarnessError, ValidationError, OSError, httpx2.HTTPError) as error:
        typer.echo(f"ERROR {error}", err=True)
        raise typer.Exit(2) from error
    raise typer.Exit(code)


if __name__ == "__main__":
    typer.run(main)
