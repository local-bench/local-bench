from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
ResponseMap = dict[tuple[str, tuple[tuple[str, str], ...]], tuple[int, JsonValue]]


def load_catalog_refresh() -> ModuleType:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "catalog_refresh.py"
    spec = importlib.util.spec_from_file_location("catalog_refresh_under_test", module_path)
    if spec is None or spec.loader is None:
        msg = f"could not load {module_path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses: ResponseMap):
        self.responses = responses
        self.network_hits = 0
        self.cache_hits = 0
        self.errors: list[str] = []
        self.closed = False

    def get_json(self, path: str, params: list[tuple[str, str]] | None = None) -> tuple[int, JsonValue]:
        self.network_hits += 1
        return self.responses.get((path, tuple(params or [])), (404, None))

    def close(self) -> None:
        self.closed = True


def base_entry(model_id: str, slug: str, distills: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    return {
        "id": model_id,
        "slug": slug,
        "display_name": "Qwen3.6 27B",
        "family": "Qwen3.6",
        "org": "Qwen",
        "params_b": 27,
        "is_moe": False,
        "reasoning_capable": True,
        "license": "apache-2.0",
        "popularity": {"downloads": 4_000_000, "likes": 1800, "trending": 20},
        "gguf_repo": "unsloth/Qwen3.6-27B-MTP-GGUF",
        "quants": [],
        "distills": distills,
    }


def distill(repo_id: str, downloads: int, likes: int) -> dict[str, JsonValue]:
    return {
        "id": repo_id,
        "display_name": repo_id.rsplit("/", 1)[-1].replace("-GGUF", "").replace("-", " "),
        "org": repo_id.split("/", 1)[0],
        "popularity": {"downloads": downloads, "likes": likes, "trending": 7},
    }


def gguf_detail(repo_id: str, base_id: str, quant_label: str = "Q4_K_M", size: int = 15_700_000_000) -> dict[str, JsonValue]:
    return {
        "id": repo_id,
        "sha": f"sha-{repo_id.rsplit('/', 1)[-1]}",
        "tags": ["gguf", "license:apache-2.0", f"base_model:finetune:{base_id}"],
        "cardData": {"base_model": base_id, "license": "apache-2.0"},
        "siblings": [{"rfilename": f"model-{quant_label}.gguf", "size": size}],
        "gguf": {"total": 27_000_000_000},
    }


def args(catalog_path: Path) -> argparse.Namespace:
    return argparse.Namespace(catalog=str(catalog_path))


def test_discover_finetunes_writes_verified_promotions_and_rejections(tmp_path: Path) -> None:
    catalog_refresh = load_catalog_refresh()
    catalog_path = tmp_path / "model_catalog.json"
    out_dir = tmp_path / "out"
    base = base_entry(
        "Qwen/Qwen3.6-27B",
        "qwen3-6-27b",
        [
            distill("Jackrong/Qwopus3.6-27B-bad-GGUF", 6_000, 70),
            distill("Jackrong/Qwopus3.6-27B-v2-MTP-GGUF", 5_000, 80),
            distill("Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF", 4_000, 60),
            distill("Jackrong/Qwopus3.6-27B-v1-preview-GGUF", 3_000, 50),
            distill("Jackrong/Qwopus3.6-27B-extra-GGUF", 2_500, 55),
            distill("Jackrong/Qwopus3.6-27B-low-pop-GGUF", 100, 2),
        ],
    )
    existing = {
        "id": "Jackrong/Qwopus3.6-27B-v2-MTP",
        "slug": "qwopus3-6-27b-v2-mtp",
        "display_name": "Qwopus 3.6 27B v2 MTP",
        "family": "Qwen3.6",
        "org": "Jackrong",
        "params_b": 27,
        "is_moe": False,
        "reasoning_capable": True,
        "license": "apache-2.0",
        "base_model": "Qwen/Qwen3.6-27B",
        "popularity": {"downloads": 5_000, "likes": 80, "trending": 7},
        "gguf_repo": "Jackrong/Qwopus3.6-27B-v2-MTP-GGUF",
        "quants": [],
        "distills": [],
    }
    raw_catalog = {"popularity_as_of": "2026-07-05", "models": [base, existing]}
    catalog_path.write_text("{}\n", encoding="utf-8")
    client = FakeClient(
        {
            ("/models/Jackrong/Qwopus3.6-27B-bad-GGUF", (("blobs", "true"),)): (
                200,
                {
                    "id": "Jackrong/Qwopus3.6-27B-bad-GGUF",
                    "tags": ["gguf", "license:apache-2.0"],
                    "siblings": [],
                    "gguf": {"total": 27_000_000_000},
                },
            ),
            ("/models/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF", (("blobs", "true"),)): (
                200,
                gguf_detail("Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF", "Qwen/Qwen3.6-27B", "Q6_K", 22_900_000_000),
            ),
            ("/models/Jackrong/Qwopus3.6-27B-v1-preview-GGUF", (("blobs", "true"),)): (
                200,
                gguf_detail("Jackrong/Qwopus3.6-27B-v1-preview-GGUF", "Qwen/Qwen3.6-27B", "Q4_K_M", 17_100_000_000),
            ),
            ("/models/Jackrong/Qwopus3.6-27B-extra-GGUF", (("blobs", "true"),)): (
                200,
                gguf_detail("Jackrong/Qwopus3.6-27B-extra-GGUF", "Qwen/Qwen3.6-27B", "Q4_K_M", 16_500_000_000),
            ),
        }
    )

    exit_code = catalog_refresh.refresh_finetunes_mode(args(catalog_path), catalog_path, out_dir, raw_catalog, [base, existing], client)

    assert exit_code == 0
    proposal = catalog_refresh.load_catalog(out_dir / "model_catalog.proposed.json")[0]
    proposed_models = proposal["models"]
    assert proposed_models[:2] == [base, existing]
    promoted = proposed_models[2:]
    assert [entry["id"] for entry in promoted] == [
        "Jackrong/Qwopus3.6-27B-Coder-MTP",
        "Jackrong/Qwopus3.6-27B-v1-preview",
    ]
    assert all(entry["model_kind"] == "finetune" for entry in promoted)
    assert all(entry["base_model"] == "Qwen/Qwen3.6-27B" for entry in promoted)
    assert promoted[0]["quants"][0] == {
        "label": "Q6_K",
        "bpw": 6.79,
        "file_gb": 22.9,
        "vram_gb_8k": 25.2,
        "revision": "sha-Qwopus3.6-27B-Coder-MTP-GGUF",
    }
    report = (out_dir / "catalog-refresh-report.md").read_text(encoding="utf-8")
    assert "mode: discover-finetunes" in report
    assert "Promoted fine-tunes" in report
    assert "Jackrong/Qwopus3.6-27B-bad-GGUF" in report
    assert "no recipe-grade GGUF quant with real file size" in report
    assert "already in catalog" in report
    assert "below popularity floor" in report
    assert "per-base promotion cap reached" in report


def test_discover_finetunes_enforces_per_base_and_wave_caps(tmp_path: Path) -> None:
    catalog_refresh = load_catalog_refresh()
    catalog_path = tmp_path / "model_catalog.json"
    out_dir = tmp_path / "out"
    models: list[dict[str, JsonValue]] = []
    responses: ResponseMap = {}
    for base_index in range(7):
        base_id = f"Org/Base-{base_index}"
        distills = []
        for candidate_index in range(3):
            repo_id = f"Tuner/Base-{base_index}-Tune-{candidate_index}-GGUF"
            distills.append(distill(repo_id, 10_000 - candidate_index, 100 - candidate_index))
            responses[(f"/models/{repo_id}", (("blobs", "true"),))] = (200, gguf_detail(repo_id, base_id))
        models.append(base_entry(base_id, f"base-{base_index}", distills))
    raw_catalog = {"models": models}
    catalog_path.write_text("{}\n", encoding="utf-8")

    exit_code = catalog_refresh.refresh_finetunes_mode(args(catalog_path), catalog_path, out_dir, raw_catalog, models, FakeClient(responses))

    assert exit_code == 0
    proposal = catalog_refresh.load_catalog(out_dir / "model_catalog.proposed.json")[0]
    promoted = proposal["models"][len(models) :]
    assert len(promoted) == 12
    for base_index in range(7):
        assert sum(1 for entry in promoted if entry["base_model"] == f"Org/Base-{base_index}") <= 2
    report = (out_dir / "catalog-refresh-report.md").read_text(encoding="utf-8")
    assert "wave cap reached" in report
