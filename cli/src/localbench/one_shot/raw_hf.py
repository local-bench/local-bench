from __future__ import annotations

from localbench.one_shot.catalog import CatalogResolutionError
from localbench.one_shot.download import DownloadError
from localbench.one_shot.types import OneShotArtifact


class HuggingFaceRawArtifactResolver:
    def resolve_raw_artifact(self, *, repo_id: str, quant: str | None) -> OneShotArtifact:
        try:
            from huggingface_hub import HfApi
        except ImportError as error:
            raise DownloadError("install localbench[hf] to resolve raw Hugging Face GGUF repos") from error
        info = HfApi().model_info(repo_id, files_metadata=True)
        revision = getattr(info, "sha", None)
        if not isinstance(revision, str) or len(revision) != 40:
            raise CatalogResolutionError("raw HF repo must resolve to a full pinned commit SHA")
        selected = _select_raw_gguf(getattr(info, "siblings", ()), quant)
        filename = _sibling_filename(selected)
        return OneShotArtifact(
            repo_id=repo_id,
            filename=filename,
            revision=revision.lower(),
            quant_label=quant or _quant_from_filename(filename),
            sha256=_sibling_sha256(selected),
            size_bytes=_sibling_size(selected),
            vram_required_gb_8k=None,
            vram_required_gb_32k=None,
        )


def _select_raw_gguf(siblings: object, quant: str | None) -> object:
    if not isinstance(siblings, list | tuple):
        raise CatalogResolutionError("raw HF repo file listing is unavailable")
    candidates: list[object] = []
    for sibling in siblings:
        filename = _sibling_filename_or_none(sibling)
        if filename is None or not filename.lower().endswith(".gguf"):
            continue
        if quant is not None and quant.lower() not in filename.lower():
            continue
        candidates.append(sibling)
    if not candidates:
        suffix = f" matching {quant}" if quant is not None else ""
        raise CatalogResolutionError(f"raw HF repo has no GGUF artifact{suffix}")
    return sorted(candidates, key=_sibling_filename)[0]


def _sibling_filename(sibling: object) -> str:
    filename = _sibling_filename_or_none(sibling)
    if filename is None:
        raise CatalogResolutionError("raw HF repo file listing contains an unnamed file")
    return filename


def _sibling_filename_or_none(sibling: object) -> str | None:
    value = getattr(sibling, "rfilename", None) or getattr(sibling, "path", None)
    return value if isinstance(value, str) and value else None


def _sibling_size(sibling: object) -> int | None:
    value = getattr(sibling, "size", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sibling_sha256(sibling: object) -> str | None:
    lfs = getattr(sibling, "lfs", None)
    value = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
    if isinstance(value, str) and len(value) == 64:
        return value.lower()
    return None


def _quant_from_filename(filename: str) -> str:
    upper = filename.upper()
    for label in ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K", "IQ2_XS", "F16"):
        if label in upper:
            return label
    return "unknown"
