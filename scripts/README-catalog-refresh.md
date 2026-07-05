# catalog_refresh.py — verify & refresh the onramp model catalog

`web/model_catalog.json` (the onramp picker source) is hand-curated and drifts: quant
file sizes were estimated from a bpw formula, repos get renamed/deleted, popularity
goes stale, and popular fine-tunes of catalogued bases never get picked up.
`scripts/catalog_refresh.py` checks the whole catalog against the **public Hugging Face
API** (no token, nothing sent anywhere else) and proposes a corrected catalog for
review. It never touches `web/model_catalog.json` itself.

## Run

From the repo root:

```
uv run --project cli python scripts/catalog_refresh.py
```

A full run makes ~500 throttled API calls (>= 200 ms spacing) and takes a few minutes
the first time; responses are cached under `catalog-refresh-out/cache/` so re-runs are
nearly instant within the cache window (24 h by default).

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--catalog PATH` | `web/model_catalog.json` | catalog to verify |
| `--out-dir PATH` | `catalog-refresh-out/` | where report/proposal/cache go |
| `--throttle-ms N` | 250 | spacing between network requests (floor 200) |
| `--cache-max-age-hours H` | 24 | reuse cached API responses younger than this |
| `--refresh` | off | ignore the cache entirely |
| `--limit N` | all | only the first N entries (smoke testing) |
| `--no-discover` | off | skip new-candidate discovery (verification only) |
| `--discover-detail-top N` | 40 | fetch full file listings for the top-N GGUF candidates |

## What it checks

Per catalog entry (each has a `gguf_repo`):

- **Repo liveness** — `GET /api/models/{gguf_repo}?blobs=true`. Note: unauthenticated
  HF answers **401** for missing *and* private repos alike, so "dead" means
  "missing or private". Gated repos are reported separately.
- **Per-quant `file_gb`** — quant labels are parsed from actual GGUF filenames
  (`Q4_K_M`, `IQ4_XS`, `UD-Q4_K_XL`, `MXFP4`, ...; `-00001-of-000NN` shards summed,
  `mmproj-*` ignored). Sizes are decimal GB (bytes/1e9) rounded to 1 dp to match the
  catalog convention; `vram_gb_8k` is recomputed with the catalog formula
  `file_gb + 1.0 + 0.05 * params_b(total)`.
- **Quant coverage** — catalog quants the repo does **not** ship (dead download
  buttons) and repo quants the catalog doesn't list (informational).
- **Popularity** — downloads / likes / trendingScore refreshed from the canonical
  model id (`downloads` is HF's rolling ~30-day figure, the same metric the hub UI
  and `sort=downloads` use).
- **License** — compared against HF's `license:` tag; differences applied to the
  proposal and listed in the report.
- **Lineage** — if HF declares a `base_model` for the canonical id (fine-tunes,
  distills, instruct-tunes of a base), the proposal gains an additive `base_model`
  field (string, or array when multiple bases are declared, e.g. merges). This is the
  **only** schema addition; everything else keeps the existing snake_case shape, and
  the web loaders are tolerant of unknown keys by design (`web/lib/schemas.ts`).
- **Base mismatch** — if the GGUF repo's own metadata says it quantizes a different
  model than the entry id, that's flagged for a manual look.
- **Wrong-scale guard** — when the repo's `gguf.total` parameter count is >2x off the
  entry's `params_b`, two cases are distinguished:
  - repo is **not** name-equivalent to the entry (e.g. `deepseek-ai/DeepSeek-R1`
    linked an 8B distill GGUF): its sizes would poison the entry, so **no** size
    updates are applied; the entry lands in the mismatch table as "WRONG SCALE -
    sizes not applied" and the fix is re-pointing `gguf_repo`;
  - repo **is** this model by name (e.g. Gemma 3n/4 E-series, whose raw param count
    exceeds the "effective" `params_b`; GLM-5.1 at ~754B): the files are real, sizes
    are applied, and the catalog's `params_b` is flagged for review instead.

## Discovery (new candidates)

Three probes, all ranked by downloads and deduped against the catalog
(entry ids + `gguf_repo`s + distill ids):

1. `?filter=base_model:finetune:{id}` for every catalogued base — popular fine-tunes,
   merges and distills **with lineage**, which is exactly what the owner wants added
   (the report table carries `base_model` so a curated add can fill the new field).
   For top fine-tunes, a best-effort probe finds a community GGUF of the fine-tune.
2. `?filter=base_model:quantized:{id}` — alternate GGUF sources for catalogued bases.
3. `?search={family}&filter=gguf&sort=downloads` per catalog family — popular GGUF
   repos the lineage tags miss.

Candidates are **never** auto-added to the proposal; they appear only in the report.

## Outputs

- `catalog-refresh-out/catalog-refresh-report.md` — human-readable diff: corrections,
  missing quants, dead/gated repos, license diffs, popularity movers, new-candidate
  tables, API notes.
- `catalog-refresh-out/model_catalog.proposed.json` — the corrected catalog
  (same array shape, additive `base_model` only).
- `catalog-refresh-out/cache/` — raw API responses (safe to delete; only a cache).

## Review workflow

1. Read the report. Spot-check a few `file_gb` corrections against the repo's
   "Files" tab on huggingface.co.
2. Diff the proposal against the live catalog:
   `git diff --no-index web/model_catalog.json catalog-refresh-out/model_catalog.proposed.json`
3. Apply if happy: `cp catalog-refresh-out/model_catalog.proposed.json web/model_catalog.json`,
   then rebuild the site data and run the web tests.
4. Curate new candidates from the report by hand (add entry + `base_model` lineage;
   quants/sizes for the add can be read straight from the candidate's repo via the
   cached responses).

## API findings baked into the script

- `expand[]` and `blobs=true` cannot be combined; the script fetches the canonical id
  with `expand[]` (popularity/cardData) and the GGUF repo with `blobs=true` (file sizes).
- `cardData.base_model` may be a string or a list.
- Nonexistent repos return 401, not 404 (unauthenticated).
- 429s are retried honouring `Retry-After`; 5xx/timeouts retry with backoff; persistent
  failures degrade to per-entry "error" rows rather than aborting the run.
