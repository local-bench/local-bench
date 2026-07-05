"""Build adversarial sandbox probes for the BigCodeBench verifier.

Each probe is a deliberately WRONG solution (it never computes the real answer) carrying one
harness-gaming exploit from the suite-v2 design review. A probe that PASSES the sandbox proves
that exploit defeats the harness — the expected verdict for every probe is FAIL. Probe 7 also
checks that runaway children do not hang the verifier (wall-clock sanity), and probe 4 plants a
file intended to poison LATER tasks — pair it with a ground-truth item ordered after it to test
cross-task isolation.

Usage:
  <python> scripts/build_adversarial_probes.py --out runs/groundtruth/bcb-probes.pending.json
  localbench code --pending-run runs/groundtruth/bcb-probes.pending.json --suite-dir suite/v1 \
      --image bigcodebench/bigcodebench-evaluate@sha256:<pinned>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli" / "src"))

from localbench.coding_exec.artifacts import code_artifact_for_generation  # noqa: E402

SUITE_FIL