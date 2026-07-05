export const LAUNCH_FREEZE = {
  asOfDate: "2026-07-05",
  scorecardVersion: "scorecard-v2.1",
  boardSha256: "c199e25c9ce22287732f84f9aeaedd6514492d874b9fb6bb55152814e9963081",
  itemSetHashes: [
    { label: "MMLU-Pro (Knowledge, 400 items)", file: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4" },
    { label: "IFBench (Instruction, 294 items)", file: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257" },
    { label: "TC-JSON v1 (Tool calling, 330 items)", file: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74" },
    { label: "LiveCodeBench proxy (Coding, 129 items)", file: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf" },
  ],
  headlineDefinition:
    "Index = 0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.10 Coding.",
  candidateDefinition:
    "Math, Long-Context, and BigCodeBench-Hard coding-exec are diagnostic or opt-in modules until their lanes are hardened.",
  determinismWording:
    "Scoring is deterministic from frozen artifacts and submitted outputs. Model reruns are reported with fixed settings and bootstrap confidence intervals, not claimed bit-identical across hardware or software stacks.",
} as const;

export function shortHash(sha256: string): string {
  return sha256.slice(0, 12);
}
