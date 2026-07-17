export const LAUNCH_FREEZE = {
  asOfDate: "2026-07-17",
  scorecardVersion: "scorecard-v6",
  boardSha256: "5803ce4344624312fc501b78e8b1ab1a43093e69919841c2d8788bdf796098c8",
  itemSetHashes: [
    { label: "MMLU-Pro (Knowledge, 400 items)", file: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4" },
    { label: "IFBench (Instruction, 294 items)", file: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257" },
    { label: "TC-JSON v1 (Tool calling, 330 items)", file: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74" },
    { label: "BigCodeBench-Hard (Coding, executed, 148 items)", file: "bigcodebench_hard.jsonl", sha256: "33635febb89ab6cb8f06e139bc33932ada89d90e32ce03820ad7f15712e19b8e" },
    { label: "OlymMATH-Hard (Math, 100 items)", file: "olymmath_hard.jsonl", sha256: "8126598901f0e2be27b2a4fed97fded7b2c43aa37ca3ecb580527ad11a15e53b" },
    { label: "AMO (Math, 39 items)", file: "amo.jsonl", sha256: "98e79f1da84680345224f48fc7d1ed8b220e76cfd0525da1c494633d1abd1904" },
    { label: "LiveCodeBench proxy (legacy diagnostic, 129 items)", file: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf" },
  ],
  headlineDefinition:
    "Index (index-v4.1) = 0.25 Agentic + 0.225 Knowledge + 0.225 Instruction + 0.225 Coding + 0.075 Math, under the bounded-final-v2 lane. Agentic folds AppWorld (agentic execution) and multi-turn tool control; Coding is BigCodeBench-Hard with verifier-side execution.",
  candidateDefinition:
    "Long-Context remains a candidate axis; LiveCodeBench is a legacy diagnostic. Rows measured under earlier lanes (capped-thinking) stay on model pages as diagnostics and never rank.",
  determinismWording:
    "Scoring is deterministic from frozen artifacts and submitted outputs. Model reruns are reported with fixed settings and bootstrap confidence intervals, not claimed bit-identical across hardware or software stacks.",
} as const;

export function shortHash(sha256: string): string {
  return sha256.slice(0, 12);
}
