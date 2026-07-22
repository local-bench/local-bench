export const LOCALBENCH_TESTED_VERSION = "0.4.6";
export const LOCALBENCH_INSTALL_COMMAND = 'pip install "local-bench-ai[hf]"';
export const CURRENT_RANKED_SUITE = "suite-v1-full-exec-6axis-v1";
export const WINDOWS_WSL_DOCKER_GUIDE_URL =
  "https://local-bench.ai/docs/coding-sandbox-windows-wsl.md";
export const TOKENIZER_PRECACHE_NOTE =
  "With --hf-model-id, an online ranked run automatically pre-caches it before offline introspection. Run localbench cache-tokenizer <hf-model-id> first when using --offline.";
export const CODING_VERIFIER_NOTE =
  "bench runs the coding verifier automatically; on older CLIs run: localbench code --pending-run <run-dir> --suite-dir <suite-dir> --allow-untrusted-code";

export const CLI_PREREQUISITES = [
  "Python 3.11+",
  "llama.cpp server binary",
  "Docker for the coding sandbox",
  "Linux, or Windows with WSL2, for Agentic",
  "Tokenizer access for --hf-model-id (online auto-cache, or pre-cache before --offline)",
] as const;

export type CanonicalRankedBenchInput = {
  readonly modelFileArgument: string;
  readonly modelId: string;
  readonly hfModelId: string;
  readonly outArgument: string;
};

export function formatQuickLocalCheckCommand(modelArgument: string, quantArgument: string): string {
  return `localbench bench ${modelArgument} --quant ${quantArgument} --allow-untrusted-code`;
}

export function formatCanonicalBenchCommand(input: CanonicalRankedBenchInput): string {
  return (
    `localbench bench --runtime llama.cpp --server-bin <path-to-llama-server> ` +
    `--model-file ${input.modelFileArgument} --model-id ${input.modelId} ` +
    `--hf-model-id ${input.hfModelId} --lane bounded-final-v2 --profile auto --tier standard ` +
    `--ctx 32768 --seed 1234 --allow-untrusted-code --out ${input.outArgument}`
  );
}

export function formatCanonicalSubmitCommand(runArgument: string, baseModel: string): string {
  return `localbench submit run --run ${runArgument} --base-model ${baseModel}`;
}
