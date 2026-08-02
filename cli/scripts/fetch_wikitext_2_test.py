# /// script
# requires-python = ">=3.11"
# dependencies = ["datasets==5.0.0", "huggingface-hub==1.21.0", "typer==0.25.1"]
# ///

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypeVar

import typer
from datasets import Dataset, load_dataset
from huggingface_hub import hf_hub_download

RequiredValue = TypeVar("RequiredValue", str, int)


def _required(
    config: dict[str, Any], key: str, expected_type: type[RequiredValue]
) -> RequiredValue:
    value = config.get(key)
    if not isinstance(value, expected_type):
        raise TypeError(f"KLD corpus config field {key!r} has the wrong type")
    return value


def fetch(output: Path) -> None:
    config_path = Path(__file__).resolve().parents[2] / "checkset" / "kld-corpus.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("KLD corpus config must be a JSON object")
    repository = str(_required(config, "repository", str))
    revision = str(_required(config, "revision", str))
    source_file = str(_required(config, "source_file", str))
    cached_source = Path(
        hf_hub_download(
            repo_id=repository,
            filename=source_file,
            revision=revision,
            repo_type="dataset",
        )
    )
    source_sha256 = hashlib.sha256(cached_source.read_bytes()).hexdigest()
    if source_sha256 != _required(config, "source_sha256", str):
        raise ValueError("Downloaded Wikitext source digest does not match the pin")
    dataset = load_dataset(
        repository,
        str(_required(config, "config", str)),
        split=str(_required(config, "split", str)),
        revision=revision,
    )
    if not isinstance(dataset, Dataset):
        raise TypeError("Wikitext loader did not return a Dataset")
    text_rows = dataset["text"]
    if len(text_rows) != _required(config, "row_count", int):
        raise ValueError("Wikitext row count does not match the pin")
    corpus = "".join(str(text) for text in text_rows).encode("utf-8")
    if len(corpus) != _required(config, "corpus_bytes", int):
        raise ValueError("Materialized Wikitext byte count does not match the pin")
    if hashlib.sha256(corpus).hexdigest() != _required(config, "corpus_sha256", str):
        raise ValueError("Materialized Wikitext digest does not match the pin")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(corpus)
    typer.echo(f"wrote {len(corpus)} pinned bytes to {output}")


if __name__ == "__main__":
    typer.run(fetch)
