#!/usr/bin/env python3
"""catalog_refresh.py — verify + refresh web/model_catalog.json against the public Hugging Face API.

What it does
------------
1. For every catalog entry (all have a ``gguf_repo``):
   - fetches the GGUF repo (``/api/models/{repo}?blobs=true``) for existence, gating,
     the file list with sizes, and the set of quant labels actually published;
   - fetches the canonical model (``/api/models/{id}?expand[]=...``) for fresh
     downloads / likes / trendingScore, license, and declared ``base_model`` lineage;
   - verifies per-quant ``file_gb`` against real file sizes, flags catalog quants the
     repo does not ship, and repo quants the catalog does not list.
2. Discovers NEW candidates: popular fine-tunes / merges of catalogued bases (via
   ``?filter=base_model:finetune:{id}``), alternate/quantized GGUF repos
   (``?filter=base_model:quantized:{id}``), and per-family GGUF search
   (``?search={family}&filter=gguf``), ranked by downloads.
3. Writes:
   - ``catalog-refresh-out/catalog-refresh-report.md``   (human-readable diff/report)
   - ``catalog-refresh-out/model_catalog.proposed.json`` (corrected catalog, additive
     ``base_model`` field only; NEVER overwrites web/model_catalog.json)

Politeness: >=200 ms request spacing (default 250 ms), retry/backoff on 429 and 5xx,
HF_TOKEN is used when present for metadata mode, and responses are cached under
``catalog-refresh-out/cache``.

Run from the repo root:
    uv run --project cli python scripts/catalog_refresh.py
    uv run --project cli python scripts/catalog_refresh.py --mode metadata
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://huggingface.co/api"
USER_AGENT = "local-bench-catalog-refresh/0.1 (public metadata only; https://local-bench.ai)"
MAX_CHANGED_ENTRIES = 250
MAX_NEW_FINETUNE_PROMOTIONS = 12
MAX_FINETUNES_PER_BASE = 2
MIN_FINETUNE_DOWNLOADS = 2_000
MIN_FINETUNE_LIKES = 50
RECIPE_GRADE_QUANTS = ("FP16", "Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K")

# Canonical-model detail fields (expand[] cannot be combined with blobs=true, so the
# GGUF-repo fetch uses ?blobs=true and the canonical fetch uses expand[]).
CANONICAL_EXPAND = [
    "downloads",
    "downloadsAllTime",
    "likes",
    "trendingScore",
    "cardData",
    "tags",
    "gated",
    "config",
    "safetensors",
]
METADATA_EXPAND = ["downloads", "downloadsAllTime", "likes", "trendingScore"]

# Quant-label extraction from GGUF filenames. Longest alternatives first.
QUANT_RE = re.compile(
    r"(?<![A-Za-z0-9])((?:UD[-_])?(?:I?Q\d+(?:_[A-Za-z0-9]{1,4}){1,3}|TQ\d+_\d+|MXFP4(?:_MOE)?|BF16|FP16|F16|FP32|F32))(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SPLIT_SUFFIX_RE = re.compile(r"[-.]\d{5}-of-\d{5}$")
PARAMS_X_RE = re.compile(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*[bB](?![A-Za-z0-9])")
PARAMS_RE = re.compile(r"(?<![aA])(?<![aA]\d)(\d+(?:\.\d+)?)\s*[bB](?![A-Za-z0-9])")

GB = 1e9  # decimal gigabytes, matching the catalog's params_b*bpw/8 convention


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- HTTP


class HfClient:
    """Throttled, disk-cached, retrying client for the public HF API. No credentials."""

    def __init__(self, cache_dir: Path, throttle_ms: int, cache_max_age_h: float, refresh: bool):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.throttle_s = max(throttle_ms, 200) / 1000.0  # never faster than 200 ms
        self.cache_max_age_s = cache_max_age_h * 3600
        self.refresh = refresh
        self._last_request = 0.0
        self.network_hits = 0
        self.cache_hits = 0
        self.errors: list[str] = []
        headers = {"User-Agent": USER_AGENT}
        token = os.environ.get("HF_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0),
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".json")

    def get_json(self, path: str, params: list[tuple[str, str]] | None = None) -> tuple[int, Any]:
        """GET an API path. Returns (status_code, parsed_json_or_None). Caches 200/401/404."""
        url = str(httpx.URL(API_BASE + path, params=params or []))
        cpath = self._cache_path(url)
        if not self.refresh and cpath.exists():
            try:
                entry = json.loads(cpath.read_text(encoding="utf-8"))
                if time.time() - entry["fetched_at"] <= self.cache_max_age_s:
                    self.cache_hits += 1
                    return entry["status"], entry["body"]
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # corrupt cache entry -> refetch

        for attempt in range(5):
            wait = self.throttle_s - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self._client.get(url)
                self._last_request = time.monotonic()
                self.network_hits += 1
            except httpx.HTTPError as exc:
                self._last_request = time.monotonic()
                if attempt == 4:
                    self.errors.append(f"{url}: {exc!r}")
                    return -1, None
                time.sleep(2.0 * (attempt + 1))
                continue

            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
                log(f"    429 rate-limited, sleeping {delay:.0f}s ...")
                time.sleep(delay)
                continue
            if resp.status_code >= 500:
                if attempt == 4:
                    self.errors.append(f"{url}: HTTP {resp.status_code}")
                    return resp.status_code, None
                time.sleep(2.0 * (attempt + 1))
                continue

            try:
                body = resp.json() if resp.content else None
            except json.JSONDecodeError:
                body = None
            if resp.status_code in (200, 401, 403, 404):
                cpath.write_text(
                    json.dumps({"url": url, "fetched_at": time.time(), "status": resp.status_code, "body": body}),
                    encoding="utf-8",
                )
            return resp.status_code, body

        return -1, None


class HubMetadataClient:
    def __init__(self, cache_dir: Path, throttle_ms: int, cache_max_age_h: float, refresh: bool):
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise SystemExit(
                "metadata mode requires huggingface_hub; run with the CLI environment that includes the hf extra"
            ) from exc
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.throttle_s = max(throttle_ms, 200) / 1000.0
        self.cache_max_age_s = cache_max_age_h * 3600
        self.refresh = refresh
        self.token = os.environ.get("HF_TOKEN") or None
        self.api = HfApi(token=self.token, user_agent=USER_AGENT)
        self._last_request = 0.0
        self.network_hits = 0
        self.cache_hits = 0
        self.errors: list[str] = []

    def _cache_path(self, repo_id: str) -> Path:
        key = f"model_info:{repo_id}:{','.join(METADATA_EXPAND)}"
        return self.cache_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def model_info(self, repo_id: str) -> dict[str, Any] | None:
        cpath = self._cache_path(repo_id)
        if not self.refresh and cpath.exists():
            try:
                entry = json.loads(cpath.read_text(encoding="utf-8"))
                if time.time() - entry["fetched_at"] <= self.cache_max_age_s:
                    self.cache_hits += 1
                    return entry["body"]
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        wait = self.throttle_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            info = self.api.model_info(repo_id, expand=METADATA_EXPAND, token=self.token, timeout=60)
            self._last_request = time.monotonic()
            self.network_hits += 1
        except Exception as exc:
            self._last_request = time.monotonic()
            self.errors.append(f"{repo_id}: {type(exc).__name__}: {exc}")
            return None
        body = model_info_body(info)
        cpath.write_text(
            json.dumps({"repo_id": repo_id, "fetched_at": time.time(), "body": body}),
            encoding="utf-8",
        )
        return body


def model_info_body(info: Any) -> dict[str, Any]:
    return {
        "downloads": value_from_info(info, "downloads"),
        "downloadsAllTime": value_from_info(info, "downloads_all_time", "downloadsAllTime"),
        "likes": value_from_info(info, "likes"),
        "trendingScore": value_from_info(info, "trending_score", "trendingScore"),
    }


def value_from_info(info: Any, *keys: str) -> Any:
    data = vars(info) if hasattr(info, "__dict__") else {}
    for key in keys:
        if key in data:
            return data[key]
        value = getattr(info, key, None)
        if value is not None:
            return value
    return None


# --------------------------------------------------------------------------- GGUF parsing


def _label_from_text(text: str) -> str | None:
    matches = QUANT_RE.findall(text)
    if not matches:
        return None
    label = matches[-1].upper().replace("UD_", "UD-")
    if label in ("FP16", "FP32"):
        label = label.replace("FP", "F")
    return label


def parse_gguf_quants(siblings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map quant label -> {size_bytes, n_files, example}. Split shards are summed per artifact;
    if several artifacts share a label (e.g. root file + per-quant subdir), the largest wins."""
    artifacts: dict[tuple[str, str], dict[str, Any]] = {}
    for sib in siblings:
        rfile = sib.get("rfilename") or ""
        if not rfile.lower().endswith(".gguf"):
            continue
        name = rfile.rsplit("/", 1)[-1]
        if "mmproj" in name.lower():
            continue
        stem = SPLIT_SUFFIX_RE.sub("", name[: -len(".gguf")])
        directory = rfile.rsplit("/", 1)[0] if "/" in rfile else ""
        label = _label_from_text(stem) or _label_from_text(directory or "")
        if not label:
            continue
        key = (directory, stem)
        art = artifacts.setdefault(key, {"label": label, "size_bytes": 0, "n_files": 0, "example": rfile})
        art["size_bytes"] += int(sib.get("size") or 0)
        art["n_files"] += 1

    by_label: dict[str, dict[str, Any]] = {}
    for art in artifacts.values():
        cur = by_label.get(art["label"])
        if cur is None or art["size_bytes"] > cur["size_bytes"]:
            by_label[art["label"]] = art
    return by_label


def params_from_name(name: str) -> float | None:
    tail = name.rsplit("/", 1)[-1]
    m = PARAMS_X_RE.search(tail)
    if m:
        return round(int(m.group(1)) * float(m.group(2)), 1)
    hits = [float(x) for x in PARAMS_RE.findall(tail)]
    return max(hits) if hits else None


# --------------------------------------------------------------------------- helpers


def base_model_relations(tags: list[str]) -> list[tuple[str, str]]:
    """[('finetune'|'quantized'|'merge'|'adapter'|'', base_id), ...] from base_model tags."""
    rels: list[tuple[str, str]] = []
    for tag in tags or []:
        if not tag.startswith("base_model:"):
            continue
        rest = tag[len("base_model:") :]
        for kind in ("finetune", "quantized", "merge", "adapter", "distill"):
            if rest.startswith(kind + ":"):
                rels.append((kind, rest[len(kind) + 1 :]))
                break
        else:
            rels.append(("", rest))
    return rels


def license_from_meta(meta: dict[str, Any]) -> str | None:
    for tag in meta.get("tags") or []:
        if tag.startswith("license:"):
            return tag[len("license:") :]
    card = meta.get("cardData") or {}
    lic = card.get("license")
    if isinstance(lic, list):
        lic = lic[0] if lic else None
    return lic


def declared_base_model(meta: dict[str, Any]) -> str | list[str] | None:
    card = meta.get("cardData") or {}
    base = card.get("base_model")
    if isinstance(base, list):
        base = [b for b in base if isinstance(b, str) and b.strip()]
        if not base:
            return None
        return base[0] if len(base) == 1 else base
    if isinstance(base, str) and base.strip():
        return base.strip()
    rels = base_model_relations(meta.get("tags") or [])
    bases = sorted({b for _, b in rels})
    if not bases:
        return None
    return bases[0] if len(bases) == 1 else bases


def _name_tokens(repo_or_id: str) -> list[str]:
    tail = repo_or_id.rsplit("/", 1)[-1].lower()
    return [t for t in re.split(r"[^a-z0-9]+", tail) if t]


def names_equivalent(entry_id: str, repo_id: str) -> bool:
    """True when the repo name is the entry's model name (optionally with a non-version
    suffix like -GGUF). 'GLM-5' vs 'GLM-5.1-GGUF' is NOT equivalent (version continues);
    'gemma-3n-E2B-it' vs 'gemma-3n-E2B-it-GGUF' is."""
    et = _name_tokens(entry_id)
    rt = _name_tokens(repo_id)
    if not et:
        return False
    for i in range(len(rt) - len(et) + 1):
        if rt[i : i + len(et)] == et:
            nxt = rt[i + len(et)] if i + len(et) < len(rt) else ""
            if not nxt or not nxt[0].isdigit():
                return True
    return False


def entry_total_params(entry: dict[str, Any]) -> float:
    p = entry.get("params_b")
    if isinstance(p, dict):
        return float(p.get("total_b") or 0)
    return float(p or 0)


def fmt_gb(x: float | None) -> str:
    return "?" if x is None else f"{x:g}"


def fmt_int(x: Any) -> str:
    return f"{int(x):,}" if isinstance(x, (int, float)) else "?"


# --------------------------------------------------------------------------- verification


@dataclass
class EntryResult:
    entry_id: str
    gguf_repo: str
    repo_status: str = "ok"  # ok | gated | dead | error
    repo_note: str = ""
    corrections: list[dict[str, Any]] = field(default_factory=list)  # file_gb fixes
    missing_in_repo: list[str] = field(default_factory=list)  # catalog quants repo lacks
    extra_in_repo: list[str] = field(default_factory=list)  # repo quants catalog lacks
    license_change: tuple[str | None, str | None] | None = None
    base_model: str | list[str] | None = None
    base_mismatch: str | None = None  # gguf repo declares a different base than entry id
    wrong_scale: bool = False  # repo params differ >2x from entry -> sizes NOT applied
    repo_params_b: float | None = None
    params_note: bool = False  # repo IS the right model but catalog params_b looks off
    entry_params_b: float | None = None
    popularity_old: dict[str, Any] = field(default_factory=dict)
    popularity_new: dict[str, Any] = field(default_factory=dict)
    canonical_missing: bool = False

    @property
    def clean(self) -> bool:
        return (
            self.repo_status == "ok"
            and not self.corrections
            and not self.missing_in_repo
            and self.license_change is None
            and self.base_mismatch is None
            and not self.wrong_scale
        )


def verify_entry(client: HfClient, entry: dict[str, Any], proposed: dict[str, Any]) -> EntryResult:
    res = EntryResult(entry_id=entry["id"], gguf_repo=entry.get("gguf_repo") or "")

    # --- canonical model: popularity, license, lineage -------------------------------
    params = [("expand[]", e) for e in CANONICAL_EXPAND]
    status, meta = client.get_json(f"/models/{entry['id']}", params)
    if status == 200 and isinstance(meta, dict):
        pop_old = dict(entry.get("popularity") or {})
        pop_new = dict(pop_old)
        if isinstance(meta.get("downloads"), (int, float)):
            pop_new["downloads"] = int(meta["downloads"])
        if isinstance(meta.get("likes"), (int, float)):
            pop_new["likes"] = int(meta["likes"])
        if isinstance(meta.get("trendingScore"), (int, float)):
            pop_new["trending"] = int(meta["trendingScore"])
        res.popularity_old, res.popularity_new = pop_old, pop_new
        proposed["popularity"] = {**(proposed.get("popularity") or {}), **pop_new}

        hf_license = license_from_meta(meta)
        if hf_license and entry.get("license") and hf_license != entry["license"]:
            res.license_change = (entry["license"], hf_license)
            proposed["license"] = hf_license

        base = declared_base_model(meta)
        if base:
            res.base_model = base
            rebuilt = {}
            for k, v in proposed.items():
                rebuilt[k] = v
                if k == "license":
                    rebuilt["base_model"] = base
            if "base_model" not in rebuilt:
                rebuilt["base_model"] = base
            proposed.clear()
            proposed.update(rebuilt)
    else:
        res.canonical_missing = True

    # --- GGUF repo: existence, files, quants ------------------------------------------
    if not res.gguf_repo:
        res.repo_status = "error"
        res.repo_note = "no gguf_repo in catalog"
        return res
    status, repo = client.get_json(f"/models/{res.gguf_repo}", [("blobs", "true")])
    if status in (401, 404) or (status == 200 and not isinstance(repo, dict)):
        res.repo_status = "dead"
        res.repo_note = f"HTTP {status} (missing or private; unauthenticated HF returns 401 for both)"
        return res
    if status == 403:
        res.repo_status = "gated"
        res.repo_note = "HTTP 403 (gated; files not listable anonymously)"
        return res
    if status != 200:
        res.repo_status = "error"
        res.repo_note = f"HTTP {status}"
        return res

    if repo.get("disabled"):
        res.repo_status = "dead"
        res.repo_note = "repo disabled"
        return res
    gated = repo.get("gated")
    if gated:
        res.repo_status = "gated"
        res.repo_note = f"gated={gated!r}"

    # lineage declared by the GGUF repo itself; catches repo pointing at a different base
    gguf_base = declared_base_model(repo)
    gguf_bases = gguf_base if isinstance(gguf_base, list) else [gguf_base] if gguf_base else []
    if gguf_bases and entry["id"] not in gguf_bases:
        res.base_mismatch = ", ".join(gguf_bases)

    # Scale guard: if the repo's GGUF parameter count is >2x off the entry's params_b,
    # something is wrong. Two distinct cases:
    #   (a) the repo quantizes a DIFFERENT model (declared base != entry, or the repo
    #       name is a different model, e.g. an 8B distill linked from a 671B entry):
    #       applying its file sizes would poison the proposal -> skip comparison;
    #   (b) the repo IS this model (name-equivalent, e.g. gemma-3n E2B whose raw param
    #       count exceeds its "effective" catalog params_b): the files are real, so
    #       sizes apply, and the *catalog's params_b* is flagged for review instead.
    repo_total = (repo.get("gguf") or {}).get("total")
    entry_total = entry_total_params(entry)
    res.entry_params_b = entry_total or None
    if isinstance(repo_total, (int, float)) and repo_total > 0:
        res.repo_params_b = round(repo_total / 1e9, 1)
        if entry_total > 0:
            ratio = (repo_total / 1e9) / entry_total
            if not (0.5 <= ratio <= 2.0):
                if res.base_mismatch or not names_equivalent(entry["id"], res.gguf_repo):
                    res.wrong_scale = True
                    res.repo_note = (
                        f"repo GGUF is ~{res.repo_params_b}B vs entry {entry_total}B; "
                        "file sizes NOT applied"
                    )
                    return res
                res.params_note = True

    quants = parse_gguf_quants(repo.get("siblings") or [])
    if not quants:
        if res.repo_status == "ok":
            res.repo_status = "error"
            res.repo_note = "no parsable .gguf files in repo listing"
        return res

    catalog_labels = set()
    for q_orig, q_prop in zip(entry.get("quants") or [], proposed.get("quants") or []):
        label = (q_orig.get("label") or "").upper()
        catalog_labels.add(label)
        hit = quants.get(label)
        if hit is None:
            res.missing_in_repo.append(label)
            continue
        actual_gb = round(hit["size_bytes"] / GB, 1)
        old_gb = q_orig.get("file_gb")
        if isinstance(old_gb, (int, float)) and abs(actual_gb - float(old_gb)) >= 0.05:
            q_prop["file_gb"] = actual_gb
            old_vram = q_orig.get("vram_gb_8k")
            new_vram = round(actual_gb + 1.0 + 0.05 * entry_total_params(entry), 1)
            q_prop["vram_gb_8k"] = new_vram
            res.corrections.append(
                {"quant": label, "old_gb": float(old_gb), "new_gb": actual_gb,
                 "old_vram": old_vram, "new_vram": new_vram, "n_files": hit["n_files"]}
            )
    res.extra_in_repo = sorted(set(quants) - catalog_labels)
    return res


# --------------------------------------------------------------------------- discovery


@dataclass
class Candidate:
    repo_id: str
    downloads: int = 0
    likes: int = 0
    tags: list[str] = field(default_factory=list)
    pipeline_tag: str | None = None
    sources: set[str] = field(default_factory=set)
    relation: str = ""  # e.g. "finetune of Qwen/Qwen3-8B"
    relation_kind: str = ""
    base_id: str = ""
    base_in_catalog: bool = False
    has_gguf: bool = False
    params_b: float | None = None
    params_src: str = "name"
    quant_labels: list[str] = field(default_factory=list)
    gguf_of_candidate: str = ""  # for safetensors fine-tunes: a GGUF repo that quantizes them


def discover(
    client: HfClient,
    catalog: list[dict[str, Any]],
    detail_top: int,
    per_query_limit: int = 10,
) -> list[Candidate]:
    known: set[str] = set()
    for e in catalog:
        known.add(e["id"].lower())
        if e.get("gguf_repo"):
            known.add(e["gguf_repo"].lower())
        for d in e.get("distills") or []:
            if d.get("id"):
                known.add(d["id"].lower())
    catalog_ids = {e["id"].lower() for e in catalog}

    cands: dict[str, Candidate] = {}

    def ingest(items: Any, source: str) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            rid = item.get("id") or item.get("modelId")
            if not rid or rid.lower() in known:
                continue
            c = cands.get(rid.lower())
            if c is None:
                c = Candidate(repo_id=rid)
                cands[rid.lower()] = c
            c.downloads = max(c.downloads, int(item.get("downloads") or 0))
            c.likes = max(c.likes, int(item.get("likes") or 0))
            if item.get("tags"):
                c.tags = item["tags"]
            c.pipeline_tag = item.get("pipeline_tag") or c.pipeline_tag
            c.sources.add(source)

    n = len(catalog)
    for i, entry in enumerate(catalog):
        eid = entry["id"]
        log(f"  discover [{i + 1}/{n}] {eid}")
        for kind in ("finetune", "quantized"):
            status, items = client.get_json(
                "/models",
                [("filter", f"base_model:{kind}:{eid}"), ("sort", "downloads"),
                 ("direction", "-1"), ("limit", str(per_query_limit))],
            )
            if status == 200:
                ingest(items, f"{kind}:{eid}")

    families = sorted({e.get("family") for e in catalog if e.get("family")})
    for fam in families:
        log(f"  discover family search: {fam}")
        status, items = client.get_json(
            "/models",
            [("search", fam), ("filter", "gguf"), ("sort", "downloads"),
             ("direction", "-1"), ("limit", "20")],
        )
        if status == 200:
            ingest(items, f"search:{fam}")

    # classify from tags
    for c in cands.values():
        c.has_gguf = "gguf" in (t.lower() for t in c.tags)
        rels = base_model_relations(c.tags)
        pick = next((r for r in rels if r[0] == "finetune"), None) or \
               next((r for r in rels if r[0] in ("merge", "adapter", "distill")), None) or \
               next((r for r in rels if r[0] == "quantized"), None) or \
               (rels[0] if rels else None)
        if pick:
            c.relation_kind, c.base_id = pick
            c.relation = f"{pick[0] or 'derived'} of {pick[1]}"
            c.base_in_catalog = pick[1].lower() in catalog_ids
        c.params_b = params_from_name(c.repo_id)

    ranked = sorted(cands.values(), key=lambda c: -c.downloads)

    # detail-fetch top GGUF candidates for real quant labels + exact params
    fetched = 0
    for c in ranked:
        if fetched >= detail_top or c.downloads <= 0:
            break
        if not c.has_gguf:
            continue
        status, meta = client.get_json(f"/models/{c.repo_id}", [("blobs", "true")])
        fetched += 1
        if status == 200 and isinstance(meta, dict):
            c.quant_labels = sorted(parse_gguf_quants(meta.get("siblings") or []))
            total = (meta.get("gguf") or {}).get("total")
            if isinstance(total, (int, float)) and total > 0:
                c.params_b = round(total / 1e9, 1)
                c.params_src = "gguf"
            base = declared_base_model(meta)
            if base and not c.base_id:
                first = base[0] if isinstance(base, list) else base
                c.base_id = first
                c.relation = f"derived of {first}"
                c.base_in_catalog = first.lower() in catalog_ids

    # for the top safetensors fine-tunes, probe whether someone published a GGUF of them
    probed = 0
    for c in ranked:
        if probed >= 25:
            break
        if c.has_gguf or c.relation_kind not in ("finetune", "merge", "distill") or not c.base_in_catalog:
            continue
        status, items = client.get_json(
            "/models",
            [("filter", f"base_model:quantized:{c.repo_id}"), ("sort", "downloads"),
             ("direction", "-1"), ("limit", "3")],
        )
        probed += 1
        if status == 200 and isinstance(items, list):
            for item in items:
                tags = item.get("tags") or []
                if any(t.lower() == "gguf" for t in tags):
                    c.gguf_of_candidate = item.get("id") or ""
                    break
    return ranked


# --------------------------------------------------------------------------- fine-tune promotion


@dataclass
class FineTuneCandidate:
    repo_id: str
    base_id: str
    base_slug: str
    base_display_name: str
    base_entry: dict[str, Any]
    display_name: str
    org: str
    downloads: int
    likes: int
    trending: int
    source: str
    relation_kind: str = "finetune"


@dataclass
class FineTunePromotion:
    candidate: FineTuneCandidate
    entry: dict[str, Any]
    why: str


@dataclass
class FineTuneRejection:
    candidate: FineTuneCandidate
    reason: str


def is_derivative_entry(entry: dict[str, Any], catalog_ids: set[str]) -> bool:
    kind = entry.get("model_kind")
    if kind in ("finetune", "distill", "merge"):
        return True
    base = entry.get("base_model")
    return isinstance(base, str) and base.lower() in catalog_ids


def gather_finetune_candidates(catalog: list[dict[str, Any]]) -> list[FineTuneCandidate]:
    catalog_ids = {str(entry.get("id", "")).lower() for entry in catalog}
    candidates: list[FineTuneCandidate] = []
    for entry in catalog:
        if is_derivative_entry(entry, catalog_ids):
            continue
        base_id = str(entry.get("id") or "")
        if not base_id:
            continue
        for raw in entry.get("distills") or []:
            if not isinstance(raw, dict):
                continue
            repo_id = raw.get("id")
            if not isinstance(repo_id, str) or not repo_id:
                continue
            popularity = raw.get("popularity") if isinstance(raw.get("popularity"), dict) else {}
            display_name = raw.get("display_name") if isinstance(raw.get("display_name"), str) else display_name_from_repo(repo_id)
            org = raw.get("org") if isinstance(raw.get("org"), str) else repo_id.split("/", 1)[0]
            candidates.append(
                FineTuneCandidate(
                    repo_id=repo_id,
                    base_id=base_id,
                    base_slug=str(entry.get("slug") or ""),
                    base_display_name=str(entry.get("display_name") or base_id),
                    base_entry=entry,
                    display_name=display_name,
                    org=org,
                    downloads=int(popularity.get("downloads") or 0),
                    likes=int(popularity.get("likes") or 0),
                    trending=int(popularity.get("trending") or 0),
                    source="catalog distills[]",
                )
            )
    return dedupe_finetune_candidates(candidates)


def dedupe_finetune_candidates(candidates: list[FineTuneCandidate]) -> list[FineTuneCandidate]:
    by_repo: dict[str, FineTuneCandidate] = {}
    for candidate in candidates:
        key = candidate.repo_id.lower()
        current = by_repo.get(key)
        if current is None or (candidate.downloads, candidate.likes) > (current.downloads, current.likes):
            by_repo[key] = candidate
    return sorted(by_repo.values(), key=lambda candidate: (candidate.base_id.lower(), -candidate.downloads, -candidate.likes, candidate.repo_id.lower()))


def known_catalog_repos(catalog: list[dict[str, Any]]) -> set[str]:
    known: set[str] = set()
    for entry in catalog:
        for value in (entry.get("id"), entry.get("gguf_repo")):
            if isinstance(value, str) and value:
                known.add(value.lower())
    return known


def canonical_model_id_from_gguf(repo_id: str) -> str:
    if "/" not in repo_id:
        return strip_gguf_suffix(repo_id)
    owner, tail = repo_id.split("/", 1)
    return f"{owner}/{strip_gguf_suffix(tail)}"


def strip_gguf_suffix(value: str) -> str:
    upper = value.upper()
    for suffix in ("-GGUF", "_GGUF", ".GGUF"):
        if upper.endswith(suffix):
            return value[: -len(suffix)]
    return value


def display_name_from_repo(repo_id: str) -> str:
    tail = strip_gguf_suffix(repo_id.rsplit("/", 1)[-1])
    return re.sub(r"[-_]+", " ", tail).strip() or repo_id


def slugify_model(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "model"


def base_lineage_matches(meta: dict[str, Any], candidate: FineTuneCandidate) -> bool:
    base = declared_base_model(meta)
    if base is None:
        return True
    bases = base if isinstance(base, list) else [base]
    return candidate.base_id in bases


def quant_sort_key(label: str) -> tuple[int, str]:
    try:
        return (RECIPE_GRADE_QUANTS.index(label), label)
    except ValueError:
        return (len(RECIPE_GRADE_QUANTS), label)


def recipe_grade_quants(quants: dict[str, dict[str, Any]], params_b: float, revision: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label in sorted((label for label in quants if label in RECIPE_GRADE_QUANTS), key=quant_sort_key):
        size_bytes = quants[label].get("size_bytes")
        if not isinstance(size_bytes, (int, float)) or size_bytes <= 0:
            continue
        file_gb = round(float(size_bytes) / GB, 1)
        row = {
            "label": label,
            "bpw": round(file_gb * 8.0 / params_b, 2),
            "file_gb": file_gb,
            "vram_gb_8k": round(file_gb + 1.0 + 0.05 * params_b, 1),
        }
        if revision:
            row["revision"] = revision
        rows.append(row)
    return rows


def verify_finetune_candidate(
    client: HfClient,
    candidate: FineTuneCandidate,
    known: set[str],
) -> FineTunePromotion | FineTuneRejection:
    canonical_id = canonical_model_id_from_gguf(candidate.repo_id)
    if candidate.repo_id.lower() in known or canonical_id.lower() in known:
        return FineTuneRejection(candidate, "already in catalog")
    if candidate.downloads < MIN_FINETUNE_DOWNLOADS and candidate.likes < MIN_FINETUNE_LIKES:
        return FineTuneRejection(candidate, "below popularity floor")

    status, meta = client.get_json(f"/models/{candidate.repo_id}", [("blobs", "true")])
    if status != 200 or not isinstance(meta, dict):
        return FineTuneRejection(candidate, f"GGUF repo did not resolve (HTTP {status})")
    if meta.get("disabled"):
        return FineTuneRejection(candidate, "GGUF repo disabled")
    if meta.get("gated"):
        return FineTuneRejection(candidate, f"GGUF repo gated ({meta.get('gated')!r})")
    if not base_lineage_matches(meta, candidate):
        return FineTuneRejection(candidate, f"base_model lineage mismatch: {declared_base_model(meta)!r}")

    license_id = license_from_meta(meta)
    if not license_id:
        return FineTuneRejection(candidate, "license did not resolve")

    total = (meta.get("gguf") or {}).get("total")
    params_b = round(float(total) / 1e9, 1) if isinstance(total, (int, float)) and total > 0 else entry_total_params(candidate.base_entry)
    if params_b <= 0:
        parsed_params = params_from_name(candidate.repo_id)
        params_b = parsed_params or 0
    if params_b <= 0:
        return FineTuneRejection(candidate, "params_b did not resolve")

    quants = parse_gguf_quants(meta.get("siblings") or [])
    revision = meta.get("sha") if isinstance(meta.get("sha"), str) else None
    recipe_quants = recipe_grade_quants(quants, params_b, revision)
    if not recipe_quants:
        return FineTuneRejection(candidate, "no recipe-grade GGUF quant with real file size")

    entry = {
        "id": canonical_id,
        "slug": slugify_model(canonical_id.rsplit("/", 1)[-1]),
        "display_name": candidate.display_name,
        "family": candidate.base_entry.get("family") or "",
        "org": candidate.org,
        "params_b": params_b,
        "is_moe": bool(candidate.base_entry.get("is_moe")),
        "reasoning_capable": bool(candidate.base_entry.get("reasoning_capable")),
        "license": license_id,
        "base_model": candidate.base_id,
        "model_kind": candidate.relation_kind if candidate.relation_kind in ("distill", "merge") else "finetune",
        "popularity": {"downloads": candidate.downloads, "likes": candidate.likes, "trending": candidate.trending},
        "gguf_repo": candidate.repo_id,
        "quants": recipe_quants,
        "distills": [],
    }
    why = (
        f"{candidate.source}; popularity {candidate.downloads:,} downloads / {candidate.likes:,} likes; "
        f"{len(recipe_quants)} recipe-grade quant(s) verified from files"
    )
    return FineTunePromotion(candidate, entry, why)


def curate_finetune_promotions(
    client: HfClient,
    catalog: list[dict[str, Any]],
) -> tuple[list[FineTunePromotion], list[FineTuneRejection], int]:
    candidates = gather_finetune_candidates(catalog)
    known = known_catalog_repos(catalog)
    accepted_by_base: dict[str, list[FineTunePromotion]] = {}
    rejected: list[FineTuneRejection] = []

    grouped: dict[str, list[FineTuneCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.base_id, []).append(candidate)

    for base_id in sorted(grouped):
        base_promotions = accepted_by_base.setdefault(base_id, [])
        for candidate in sorted(grouped[base_id], key=lambda item: (-item.downloads, -item.likes, item.repo_id.lower())):
            result = verify_finetune_candidate(client, candidate, known)
            if isinstance(result, FineTuneRejection):
                rejected.append(result)
                continue
            if len(base_promotions) >= MAX_FINETUNES_PER_BASE:
                rejected.append(FineTuneRejection(candidate, "per-base promotion cap reached"))
                continue
            base_promotions.append(result)
            known.add(result.entry["id"].lower())
            known.add(result.entry["gguf_repo"].lower())

    selected: list[FineTunePromotion] = []
    overflow: list[FineTunePromotion] = []
    for base_id in sorted(accepted_by_base):
        for promotion in accepted_by_base[base_id]:
            if len(selected) < MAX_NEW_FINETUNE_PROMOTIONS:
                selected.append(promotion)
            else:
                overflow.append(promotion)
    rejected.extend(FineTuneRejection(promotion.candidate, "wave cap reached") for promotion in overflow)
    return selected, rejected, len(candidates)


def finetune_report(
    promotions: list[FineTunePromotion],
    rejections: list[FineTuneRejection],
    candidate_count: int,
    client: HfClient,
    args: argparse.Namespace,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Catalog fine-tune discovery",
        "",
        "- mode: discover-finetunes",
        f"- generated: {now}",
        f"- catalog: `{args.catalog}`",
        "- candidate source: nested catalog `distills[]` arrays (HF lineage list query intentionally deferred for v1)",
        f"- candidates gathered: {candidate_count}",
        f"- promotions: {len(promotions)}",
        f"- rejections: {len(rejections)}",
        f"- caps: top {MAX_FINETUNES_PER_BASE} per base, {MAX_NEW_FINETUNE_PROMOTIONS} total new entries",
        f"- popularity floor: downloads_last_month >= {MIN_FINETUNE_DOWNLOADS:,} OR likes >= {MIN_FINETUNE_LIKES:,}",
        f"- HTTP: {client.network_hits} network requests, {client.cache_hits} cache hits, {len(client.errors)} transport errors",
        "",
        "The proposal appends verified fine-tunes only. Existing entries are left byte-for-byte unchanged and the live catalog is not updated.",
        "",
    ]
    if promotions:
        lines.extend(
            [
                "## Promoted fine-tunes",
                "",
                "| Base | Repo | Downloads | Likes | Quants | Why |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for promotion in promotions:
            quants = ", ".join(quant["label"] for quant in promotion.entry["quants"])
            lines.append(
                f"| {promotion.candidate.base_id} | {promotion.candidate.repo_id} | {promotion.candidate.downloads:,} | {promotion.candidate.likes:,} | {quants} | {promotion.why} |"
            )
        lines.append("")
    if rejections:
        lines.extend(["## Rejected candidates", "", "| Base | Repo | Downloads | Likes | Reason |", "| --- | --- | ---: | ---: | --- |"])
        for rejection in rejections:
            lines.append(
                f"| {rejection.candidate.base_id} | {rejection.candidate.repo_id} | {rejection.candidate.downloads:,} | {rejection.candidate.likes:,} | {rejection.reason} |"
            )
        lines.append("")
    if client.errors:
        lines.extend(["## Fetch errors", ""])
        for error in client.errors[:50]:
            lines.append(f"- {error}")
        lines.append("")
    return "\n".join(lines)


def refresh_finetunes_mode(
    args: argparse.Namespace,
    catalog_path: Path,
    out_dir: Path,
    raw_catalog: Any,
    catalog: list[dict[str, Any]],
    client: HfClient | None = None,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    hf = client or HfClient(out_dir / "cache", args.throttle_ms, args.cache_max_age_hours, args.refresh)
    try:
        promotions, rejections, candidate_count = curate_finetune_promotions(hf, catalog)
    finally:
        if own_client:
            hf.close()

    proposed_models = copy.deepcopy(catalog)
    proposed_models.extend(copy.deepcopy(promotion.entry) for promotion in promotions)
    proposed_catalog = catalog_with_models(raw_catalog, proposed_models)
    proposed_path = out_dir / "model_catalog.proposed.json"
    proposed_path.write_text(json.dumps(proposed_catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    report = finetune_report(promotions, rejections, candidate_count, hf, args)
    report_path = out_dir / "catalog-refresh-report.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")

    print(
        f"mode=discover-finetunes candidates={candidate_count} promoted={len(promotions)} rejected={len(rejections)} report_only"
    )
    print(f"report: {report_path}")
    print(f"proposal: {proposed_path}")
    return 0


# --------------------------------------------------------------------------- report


def build_report(
    results: list[EntryResult],
    candidates: list[Candidate],
    catalog_len: int,
    client: HfClient,
    args: argparse.Namespace,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    clean = [r for r in results if r.clean]
    corrected = [r for r in results if r.corrections]
    dead = [r for r in results if r.repo_status == "dead"]
    gated = [r for r in results if r.repo_status == "gated"]
    errored = [r for r in results if r.repo_status == "error"]
    with_missing = [r for r in results if r.missing_in_repo]
    with_extra = [r for r in results if r.extra_in_repo]
    lic_changes = [r for r in results if r.license_change]
    mismatches = [r for r in results if r.base_mismatch or r.wrong_scale]
    wrong_scale = [r for r in results if r.wrong_scale]
    params_notes = [r for r in results if r.params_note]
    with_base = [r for r in results if r.base_model]
    n_missing_quants = sum(len(r.missing_in_repo) for r in results)
    n_corrections = sum(len(r.corrections) for r in results)

    L: list[str] = []
    L.append("# Catalog refresh report")
    L.append("")
    L.append(f"Generated {now} by `scripts/catalog_refresh.py` against the public Hugging Face API.")
    L.append(f"Catalog: `{args.catalog}` ({catalog_len} entries). Proposed catalog: `model_catalog.proposed.json` (same shape, additive `base_model` only).")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append("| Metric | Count |")
    L.append("| --- | ---: |")
    L.append(f"| Entries checked | {len(results)} |")
    L.append(f"| Verified clean (repo ok, sizes match, all catalog quants exist) | {len(clean)} |")
    L.append(f"| Entries with file_gb corrections | {len(corrected)} ({n_corrections} quant rows) |")
    L.append(f"| Entries with catalog quants MISSING from the repo | {len(with_missing)} ({n_missing_quants} quant rows) |")
    L.append(f"| Entries whose repo ships quants NOT in the catalog | {len(with_extra)} |")
    L.append(f"| Dead / inaccessible gguf repos | {len(dead)} |")
    L.append(f"| Gated gguf repos | {len(gated)} |")
    L.append(f"| Fetch/parse errors | {len(errored)} |")
    L.append(f"| License differences | {len(lic_changes)} |")
    L.append(f"| GGUF repo points at a different model (see mismatch table) | {len(mismatches)} |")
    L.append(f"| ... of which WRONG SCALE (>2x params off; sizes not applied) | {len(wrong_scale)} |")
    L.append(f"| Catalog `params_b` disagrees with the repo's GGUF param count | {len(params_notes)} |")
    L.append(f"| Entries gaining a `base_model` lineage field | {len(with_base)} |")
    L.append(f"| New candidates discovered (not in catalog) | {len(candidates)} |")
    L.append("")
    L.append(f"HTTP: {client.network_hits} network requests, {client.cache_hits} cache hits, {len(client.errors)} transport errors.")
    L.append("")

    if dead or errored:
        L.append("## Dead or unreadable GGUF repos")
        L.append("")
        L.append("| Entry | gguf_repo | Status | Note |")
        L.append("| --- | --- | --- | --- |")
        for r in dead + errored:
            L.append(f"| {r.entry_id} | {r.gguf_repo} | {r.repo_status} | {r.repo_note} |")
        L.append("")

    if gated:
        L.append("## Gated GGUF repos")
        L.append("")
        L.append("| Entry | gguf_repo | Note |")
        L.append("| --- | --- | --- |")
        for r in gated:
            L.append(f"| {r.entry_id} | {r.gguf_repo} | {r.repo_note} |")
        L.append("")

    if mismatches:
        L.append("## GGUF repo base-model mismatches")
        L.append("")
        L.append("The GGUF repo's own metadata points at a different model than the catalog entry id. Rows marked **WRONG SCALE** quantize a model >2x params away from the entry (e.g. an 8B distill linked from a 671B entry) — their file sizes were **not** applied to the proposal; re-point `gguf_repo` instead. Same-scale rows are usually renames/variants (Meta- prefix, org renames, -BF16): sizes applied, link worth a look.")
        L.append("")
        L.append("| Entry | gguf_repo | Repo declares base | Repo ~params B | Sizes applied |")
        L.append("| --- | --- | --- | ---: | --- |")
        for r in mismatches:
            applied = "NO - WRONG SCALE" if r.wrong_scale else "yes"
            L.append(f"| {r.entry_id} | {r.gguf_repo} | {r.base_mismatch or '(none declared)'} | {fmt_gb(r.repo_params_b)} | {applied} |")
        L.append("")

    if params_notes:
        L.append("## Catalog params_b vs repo GGUF param count")
        L.append("")
        L.append("The linked repo IS this model (name-equivalent), but its GGUF metadata reports a parameter count >2x away from the catalog's `params_b` — usually an effective-vs-raw discrepancy (Gemma E-series) or a stale/underscoped MoE total. File sizes from the repo were applied (they are real files); review `params_b` (it drives the bpw-estimate formula and the VRAM overhead term).")
        L.append("")
        L.append("| Entry | Catalog params_b (total) | Repo GGUF params B |")
        L.append("| --- | ---: | ---: |")
        for r in params_notes:
            L.append(f"| {r.entry_id} | {fmt_gb(r.entry_params_b)} | {fmt_gb(r.repo_params_b)} |")
        L.append("")

    if corrected:
        L.append("## file_gb corrections (from actual repo file sizes)")
        L.append("")
        L.append("Sizes are decimal GB (bytes / 1e9), rounded to 1 dp to match the catalog convention; `vram_gb_8k` is recomputed with the catalog formula `file_gb + 1.0 + 0.05 * params_b(total)`. Multi-part GGUFs are summed.")
        L.append("")
        L.append("| Entry | Quant | file_gb old | file_gb new | vram_8k old | vram_8k new |")
        L.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for r in corrected:
            for c in r.corrections:
                L.append(
                    f"| {r.entry_id} | {c['quant']} | {fmt_gb(c['old_gb'])} | **{fmt_gb(c['new_gb'])}** | {fmt_gb(c['old_vram'])} | {fmt_gb(c['new_vram'])} |"
                )
        L.append("")

    if with_missing:
        L.append("## Catalog quants that do NOT exist in the GGUF repo")
        L.append("")
        L.append("These stay in the proposed catalog (owner's call to prune or re-point `gguf_repo`), but the site is currently advertising files nobody can download.")
        L.append("")
        L.append("| Entry | gguf_repo | Missing quants |")
        L.append("| --- | --- | --- |")
        for r in with_missing:
            L.append(f"| {r.entry_id} | {r.gguf_repo} | {', '.join(r.missing_in_repo)} |")
        L.append("")

    if with_extra:
        L.append("## Repo quants not in the catalog (available but unlisted)")
        L.append("")
        L.append("Informational: the catalog intentionally carries a fixed 6-step ladder, but these labels are published in the linked repo.")
        L.append("")
        L.append("| Entry | Additional repo quants |")
        L.append("| --- | --- |")
        for r in with_extra:
            L.append(f"| {r.entry_id} | {', '.join(r.extra_in_repo)} |")
        L.append("")

    if lic_changes:
        L.append("## License differences (catalog vs HF)")
        L.append("")
        L.append("| Entry | Catalog | Hugging Face | Applied to proposal |")
        L.append("| --- | --- | --- | --- |")
        for r in lic_changes:
            old, new = r.license_change
            L.append(f"| {r.entry_id} | {old} | {new} | yes |")
        L.append("")

    # popularity movement (top movers only; full refresh applied to proposal)
    movers = []
    for r in results:
        od, nd = r.popularity_old.get("downloads"), r.popularity_new.get("downloads")
        if isinstance(od, (int, float)) and isinstance(nd, (int, float)) and od != nd:
            movers.append((r.entry_id, int(od), int(nd)))
    if movers:
        movers.sort(key=lambda m: -abs(m[2] - m[1]))
        L.append("## Popularity refresh")
        L.append("")
        L.append(f"downloads/likes/trending refreshed from HF for all reachable entries ({len(movers)} download counts changed). `downloads` is HF's standard rolling ~30-day figure (the number the hub UI and `sort=downloads` use). Top movers:")
        L.append("")
        L.append("| Entry | Downloads (catalog) | Downloads (now) |")
        L.append("| --- | ---: | ---: |")
        for eid, od, nd in movers[:15]:
            L.append(f"| {eid} | {od:,} | {nd:,} |")
        L.append("")

    canon_missing = [r for r in results if r.canonical_missing]
    if canon_missing:
        L.append("## Canonical model ids that did not resolve")
        L.append("")
        L.append("Popularity/license/lineage kept as-is for these (the GGUF repo may still verify fine):")
        L.append("")
        for r in canon_missing:
            L.append(f"- {r.entry_id}")
        L.append("")

    # ---- new candidates ---------------------------------------------------------
    finetunes = [c for c in candidates if c.relation_kind in ("finetune", "merge", "adapter", "distill") and c.base_in_catalog and c.downloads > 0]
    gguf_new = [c for c in candidates if c.has_gguf and c not in finetunes and c.downloads > 0]

    L.append("## New candidates: fine-tunes / merges of catalogued bases")
    L.append("")
    L.append("Discovered via `?filter=base_model:finetune:{id}` (HF lineage tags), ranked by downloads. `GGUF repo` is a best-effort probe for a community quantization of the fine-tune itself.")
    L.append("")
    L.append("| # | Repo | Downloads | Likes | Relation (base_model) | ~Params B | GGUF of it |")
    L.append("| ---: | --- | ---: | ---: | --- | ---: | --- |")
    for i, c in enumerate(finetunes[:30], 1):
        gg = c.gguf_of_candidate or ("itself (gguf)" if c.has_gguf else "")
        L.append(f"| {i} | {c.repo_id} | {c.downloads:,} | {c.likes:,} | {c.relation} | {fmt_gb(c.params_b)} | {gg} |")
    L.append("")

    L.append("## New candidates: popular GGUF repos not in the catalog")
    L.append("")
    L.append("From per-family GGUF search plus `base_model:quantized:{id}` lineage. Quants listed where the repo detail was fetched (top candidates only). Params from GGUF metadata where available, else parsed from the name.")
    L.append("")
    L.append("| # | Repo | Downloads | base_model | ~Params B | Quants |")
    L.append("| ---: | --- | ---: | --- | ---: | --- |")
    for i, c in enumerate(gguf_new[:30], 1):
        quants = ", ".join(c.quant_labels) if c.quant_labels else "(not fetched)"
        base = c.base_id or "?"
        L.append(f"| {i} | {c.repo_id} | {c.downloads:,} | {base} | {fmt_gb(c.params_b)} | {quants} |")
    L.append("")

    L.append("## API notes / adaptations")
    L.append("")
    L.append("- The catalog file is snake_case (`gguf_repo`, `file_gb`), not camelCase; the additive lineage field follows suit as `base_model` (string, or array when HF declares multiple bases, e.g. merges).")
    L.append("- Unauthenticated HF returns **HTTP 401 (\"Invalid username or password\")** for nonexistent *and* private repos alike, so \"dead\" above means \"missing or private\".")
    L.append("- `?expand[]=` cannot be combined with `?blobs=true`; the script does two flavours of fetch (canonical id with expand for downloads/likes/trendingScore/cardData, GGUF repo with blobs for file sizes).")
    L.append("- `downloads` from HF is the rolling ~30-day count; `downloadsAllTime` exists via expand but the catalog's numbers track the standard 30-day metric.")
    L.append("- `cardData.base_model` can be a string **or a list**; single-element lists are collapsed to a string in the proposal.")
    L.append("- Quant labels are parsed from GGUF filenames (incl. `IQ*`, `UD-*` unsloth dynamic, `MXFP4`, split `-00001-of-000NN` shards summed; `mmproj-*` projector files ignored).")
    L.append("- Scale guard: when the repo's `gguf.total` parameter count is >2x off the entry's `params_b`, sizes are only applied if the repo is name-equivalent to the entry (then the *catalog params_b* is flagged instead, e.g. Gemma E-series effective-vs-raw). Non-equivalent repos (e.g. an 8B distill linked from a 671B entry) get NO size updates and land in the mismatch table.")
    if client.errors:
        L.append(f"- {len(client.errors)} transport errors after retries (first few): " + "; ".join(client.errors[:5]))
    L.append("")
    L.append("## Review workflow")
    L.append("")
    L.append("1. Read this report; spot-check a few corrections against the repo file listings on huggingface.co.")
    L.append("2. Diff the proposal: `git diff --no-index web/model_catalog.json catalog-refresh-out/model_catalog.proposed.json`")
    L.append("3. If happy: `cp catalog-refresh-out/model_catalog.proposed.json web/model_catalog.json` and rebuild site data.")
    L.append("4. New candidates are NOT auto-added; curate manually (the fine-tune table carries `base_model` lineage for the new `base_model` field).")
    L.append("")
    return "\n".join(L)


def load_catalog(path: Path) -> tuple[Any, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw, raw
    if isinstance(raw, dict) and isinstance(raw.get("models"), list):
        return raw, raw["models"]
    raise SystemExit("model catalog must be either a list or an object with a models list")


def catalog_with_models(raw: Any, models: list[dict[str, Any]], popularity_as_of: str | None = None) -> Any:
    if isinstance(raw, dict):
        out = copy.deepcopy(raw)
        if popularity_as_of is not None:
            out["popularity_as_of"] = popularity_as_of
        out["models"] = models
        return out
    if popularity_as_of is None:
        return models
    return {"popularity_as_of": popularity_as_of, "models": models}


def refresh_metadata_mode(args: argparse.Namespace, catalog_path: Path, out_dir: Path, raw_catalog: Any, catalog: list[dict[str, Any]]) -> int:
    proposed = copy.deepcopy(catalog)
    work_count = min(args.limit, len(catalog)) if args.limit else len(catalog)
    client = HubMetadataClient(out_dir / "cache", args.throttle_ms, args.cache_max_age_hours, args.refresh)
    changed: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    as_of = datetime.now(timezone.utc).date().isoformat()
    log(f"Refreshing metadata for {work_count} catalog entries ...")
    for index, entry in enumerate(catalog[:work_count]):
        repo_id = entry.get("gguf_repo") or entry.get("id")
        if not isinstance(repo_id, str) or not repo_id:
            client.errors.append(f"{entry.get('id', '<unknown>')}: missing repo id")
            continue
        log(f"  [{index + 1}/{work_count}] {entry.get('id')}  (popularity repo: {repo_id})")
        info = client.model_info(repo_id)
        if info is None:
            continue
        old = dict(entry.get("popularity") or {})
        new = popularity_from_info(info, old)
        proposed[index]["popularity"] = new
        if old != new:
            changed.append((str(entry.get("id") or repo_id), repo_id, old, new))
    proposed_catalog = catalog_with_models(raw_catalog, proposed, as_of)
    proposed_path = out_dir / "model_catalog.proposed.json"
    proposed_path.write_text(json.dumps(proposed_catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    guard = metadata_guard(raw_catalog, proposed_catalog, changed)
    report = metadata_report(changed, client, as_of, guard, args)
    report_path = out_dir / "catalog-refresh-report.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")
    if args.apply and guard["safe"]:
        catalog_path.write_text(json.dumps(proposed_catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        applied = "applied"
    elif args.apply:
        applied = "guard_blocked"
    else:
        applied = "report_only"
    print(f"mode=metadata entries={work_count} changed_entries={len(changed)} guard={guard['status']} {applied}")
    print(f"report: {report_path}")
    print(f"proposal: {proposed_path}")
    return 0


def popularity_from_info(info: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    new = dict(old)
    if isinstance(info.get("downloads"), (int, float)):
        new["downloads"] = int(info["downloads"])
    if isinstance(info.get("likes"), (int, float)):
        new["likes"] = int(info["likes"])
    if isinstance(info.get("trendingScore"), (int, float)):
        new["trending"] = int(info["trendingScore"])
    if isinstance(info.get("downloadsAllTime"), (int, float)):
        new["downloads_all_time"] = int(info["downloadsAllTime"])
    return new


def metadata_guard(raw_catalog: Any, proposed_catalog: Any, changed: list[tuple[str, str, dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    original_models = raw_catalog["models"] if isinstance(raw_catalog, dict) else raw_catalog
    proposed_models = proposed_catalog["models"] if isinstance(proposed_catalog, dict) else proposed_catalog
    reasons: list[str] = []
    if len(changed) > MAX_CHANGED_ENTRIES:
        reasons.append(f"changed entries {len(changed)} exceeds MAX_CHANGED_ENTRIES={MAX_CHANGED_ENTRIES}")
    if len(original_models) != len(proposed_models):
        reasons.append("model count changed")
    for old, new in zip(original_models, proposed_models, strict=False):
        old_without_meta = {k: v for k, v in old.items() if k != "popularity"}
        new_without_meta = {k: v for k, v in new.items() if k != "popularity"}
        if old_without_meta != new_without_meta:
            reasons.append(f"non-metadata diff for {old.get('id') or old.get('slug')}")
            break
        if [q.get("label") for q in old.get("quants", [])] != [q.get("label") for q in new.get("quants", [])]:
            reasons.append(f"quant labels changed for {old.get('id') or old.get('slug')}")
            break
        if old.get("id") != new.get("id") or old.get("gguf_repo") != new.get("gguf_repo"):
            reasons.append(f"recipe target changed for {old.get('id') or old.get('slug')}")
            break
    safe = not reasons
    return {"safe": safe, "status": "ok" if safe else "blocked", "reasons": reasons}


def metadata_report(
    changed: list[tuple[str, str, dict[str, Any], dict[str, Any]]],
    client: HubMetadataClient,
    as_of: str,
    guard: dict[str, Any],
    args: argparse.Namespace,
) -> str:
    lines = [
        "# Catalog metadata refresh",
        "",
        "- mode: metadata",
        f"- popularity_as_of: {as_of}",
        f"- changed entries: {len(changed)}",
        f"- cache hits: {client.cache_hits}",
        f"- network hits: {client.network_hits}",
        f"- apply requested: {bool(args.apply)}",
        f"- guard: {guard['status']}",
        "",
        "Popularity is fetched from the entry GGUF repo when present, so downloads are Hugging Face's monthly repo-level count across all files in that repo, not per quant.",
        "",
    ]
    reasons = guard.get("reasons") or []
    if reasons:
        lines.append("## Guard failures")
        lines.append("")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")
    if changed:
        lines.append("## Changed popularity blocks")
        lines.append("")
        lines.append("| Entry | Repo | Downloads old | Downloads new | Likes old | Likes new | Trending old | Trending new |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for entry_id, repo_id, old, new in changed:
            lines.append(
                f"| {entry_id} | {repo_id} | {fmt_int(old.get('downloads'))} | {fmt_int(new.get('downloads'))} | {fmt_int(old.get('likes'))} | {fmt_int(new.get('likes'))} | {fmt_int(old.get('trending'))} | {fmt_int(new.get('trending'))} |"
            )
        lines.append("")
    if client.errors:
        lines.append("## Metadata fetch errors")
        lines.append("")
        for error in client.errors[:50]:
            lines.append(f"- {error}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Verify/refresh web/model_catalog.json against the public HF API.")
    ap.add_argument("--catalog", default=str(repo_root / "web" / "model_catalog.json"))
    ap.add_argument("--out-dir", default=str(repo_root / "catalog-refresh-out"))
    ap.add_argument("--mode", choices=("full", "metadata", "discover-finetunes"), default="full")
    ap.add_argument("--apply", action="store_true", help="apply metadata mode only when guards pass")
    ap.add_argument("--throttle-ms", type=int, default=250, help="min spacing between network requests (floor 200)")
    ap.add_argument("--cache-max-age-hours", type=float, default=24.0)
    ap.add_argument("--refresh", action="store_true", help="ignore the response cache")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N entries (testing)")
    ap.add_argument("--no-discover", action="store_true", help="skip new-candidate discovery")
    ap.add_argument("--discover-detail-top", type=int, default=40, help="fetch full detail for top-N GGUF candidates")
    args = ap.parse_args()

    catalog_path = Path(args.catalog)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_catalog, catalog = load_catalog(catalog_path)
    if args.mode == "metadata":
        return refresh_metadata_mode(args, catalog_path, out_dir, raw_catalog, catalog)
    if args.mode == "discover-finetunes":
        return refresh_finetunes_mode(args, catalog_path, out_dir, raw_catalog, catalog)

    if args.limit:
        work = catalog[: args.limit]
    else:
        work = catalog
    proposal = copy.deepcopy(catalog)

    client = HfClient(out_dir / "cache", args.throttle_ms, args.cache_max_age_hours, args.refresh)
    results: list[EntryResult] = []
    try:
        log(f"Verifying {len(work)} catalog entries ...")
        for i, entry in enumerate(work):
            log(f"  [{i + 1}/{len(work)}] {entry['id']}  (gguf: {entry.get('gguf_repo')})")
            results.append(verify_entry(client, entry, proposal[i]))

        candidates: list[Candidate] = []
        if not args.no_discover:
            log("Discovering new candidates ...")
            candidates = discover(client, work, args.discover_detail_top)
    finally:
        client.close()

    report = build_report(results, candidates, len(work), client, args)
    report_path = out_dir / "catalog-refresh-report.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")

    proposed_path = out_dir / "model_catalog.proposed.json"
    proposed_catalog = catalog_with_models(raw_catalog, proposal)
    proposed_path.write_text(
        json.dumps(proposed_catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )

    clean = sum(1 for r in results if r.clean)
    corrected = sum(1 for r in results if r.corrections)
    dead = sum(1 for r in results if r.repo_status == "dead")
    missing = sum(len(r.missing_in_repo) for r in results)
    print(f"entries={len(results)} clean={clean} corrected={corrected} dead_repos={dead} missing_quant_rows={missing} candidates={len(candidates)}")
    print(f"report: {report_path}")
    print(f"proposal: {proposed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
