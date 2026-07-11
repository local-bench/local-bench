# local-bench

Community quality leaderboard for local AI setups. The sortable headline score is the **Local Intelligence Index** (`index-v3.0 | 40/15/15/10/15/5`): 40% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, 15% Coding, and 5% Math.

The ranked six-axis profile is Agentic / Knowledge / Instruction / Tool calling / Coding / Math. BigCodeBench-Hard execution is the ranked Coding axis; the LiveCodeBench proxy (`lcb`) is a legacy diagnostic only and is never pooled into the ranked score.

## Layout

- `cli/` - Python benchmark runner, scoring registry, board builder, and submission client
- `suite/` - versioned suite definitions, item sets, prompts, and scorers
- `web/` - leaderboard site and static data projection
- `docs/` - reproduction notes, methodology history, licensing, and threat model

## Quickstart

```bash
pip install "local-bench-ai[hf]"   # installs the `localbench` command (Python 3.11+)

localbench fetch-suite \
  --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 \
  --accept-suite-terms

localbench cache-tokenizer <hf-model-id>

localbench run \
  --endpoint http://localhost:8080/v1 \
  --model <served-model-name> \
  --hf-model-id <hf-model-id> \
  --ctx-len-configured 32768 \
  --lane bounded-final-v2 \
  --profile auto \
  --tier standard \
  --publishable \
  --sampler-seed 1234 \
  --out runs/my-run.json

localbench submit run --run runs/my-run.json
```

Use `--hf-model-id` and `cache-tokenizer` when you know the exact tokenizer repo. If no exact HF tokenizer repo exists, omit `cache-tokenizer` and replace `--hf-model-id <hf-model-id>` with `--gguf-repo-only`. The site recipe pins an exact CLI version for suite-sha reproducibility; the README install stays unpinned.

Submissions are identified by an Ed25519 key generated on first submit — no
account, no email. Nothing publishes without maintainer review; see
https://local-bench.ai/submit for the full loop and what the trust labels mean.
Working from source instead: `pip install -e cli`.

## Status

Live and actively maintained. The public board is at https://local-bench.ai and is maintainer-verified. Current index identity: index-v3.0 on the bounded-final-v2 ranked lane; current CLI release: 0.3.2 (admission-compatible submit client, streaming file hashing). The site's recipe generator pins the exact CLI version to run.
