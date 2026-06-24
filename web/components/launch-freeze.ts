// Frozen public-contract metadata for the v1 launch.
//
// These values mirror the canonical freeze record `cli/runs/board/launch_freeze_v1.json`
// (schema `launch-freeze-v1`). They are surfaced verbatim on the site so a visitor can see
// exactly which item sets and scorer produced the board, and as-of when. They are content
// constants (not derived from the served data) on purpose: the freeze is LOCKED for the
// release, and threading new fields through the data pipeline (`build_data.py` / `lib/`) is
// owned by separate work. If the freeze record changes, update both in lockstep.
//
// Source of truth: cli/runs/board/launch_freeze_v1.json — keep these in sync with it.

export const LAUNCH_FREEZE = {
  /** Date the board was frozen (the "as of" date shown to visitors). */
  asOfDate: "2026-06-23",
  /** Scorecard version that produced every displayed score. */
  scorecardVersion: "scorecard-v1.3",
  /** sha256 of the published board artifact. */
  boardSha256: "0cdac94e29c74dc48c2fea4dbb06e6e114f3d3d815828073b2a2ebc93f328c41",
  /** Per-item-set sha256 of the frozen suite (the only sets in the headline Index). */
  itemSetHashes: [
    { label: "MMLU-Pro (Knowledge, 400 items)", file: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4" },
    { label: "IFBench (Instruction, 294 items)", file: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257" },
  ],
  /** What the headline number is, in one line. */
  headlineDefinition:
    "Index = Knowledge (MMLU-Pro 400) + Instruction (IFBench 294), equal-weight, chance-corrected.",
  /** How candidate axes are treated. */
  candidateDefinition:
    "Candidate axes (Math, Coding-exec, Agentic) are measured and shown at 0% Index weight, under validation; they never move the headline.",
  /** Exactly what "deterministic" does and does not claim. */
  determinismWording:
    "Scoring is deterministic from frozen artifacts + submitted outputs. Model reruns are reported with fixed settings and bootstrap confidence intervals — not claimed bit-identical across hardware or software stacks.",
} as const;

/** First 12 hex chars, for compact inline display. Full value stays available in a title attr. */
export function shortHash(sha256: string): string {
  return sha256.slice(0, 12);
}
