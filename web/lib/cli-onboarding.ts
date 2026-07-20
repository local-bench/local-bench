export const LOCALBENCH_TESTED_VERSION = "0.4.2";
export const LOCALBENCH_INSTALL_COMMAND = 'pip install "local-bench-ai[hf]"';
export const CURRENT_RANKED_SUITE = "suite-v1-full-exec-6axis-v1";

export const CLI_PREREQUISITES = [
  "Python 3.11+",
  "llama.cpp server binary",
  "Docker for the coding sandbox",
  "Windows with WSL2 for Agentic today",
] as const;

export function formatCanonicalBenchCommand(modelArgument: string, quantArgument: string): string {
  return `localbench bench ${modelArgument} --quant ${quantArgument} --allow-untrusted-code`;
}
