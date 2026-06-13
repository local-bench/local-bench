"use client";

import { useState } from "react";

const BOUNTIES = [
  {
    label: "Qwen3 32B Q6_K",
    command: "localbench run --model qwen3-32b --quant Q6_K --lane answer-only --tier quick",
  },
  {
    label: "Gemma-3 27B FP16",
    command: "localbench run --model gemma-3-27b --quant FP16 --lane answer-only --tier quick",
  },
  {
    label: "Mistral-Small-24B Q8_0",
    command: "localbench run --model mistral-small-24b --quant Q8_0 --lane answer-only --tier quick",
  },
] as const;

export function RigMatchBounty() {
  const [copied, setCopied] = useState<string | null>(null);
  return (
    <aside className="min-w-0 rounded border border-bench-line bg-black/12 p-4">
      <h2 className="text-sm font-semibold uppercase text-bench-text">Bounty</h2>
      <p className="mt-2 text-sm leading-6 text-bench-muted">Most-wanted runs to replace preview rows with real measurements.</p>
      <div className="mt-4 flex flex-col gap-3">
        {BOUNTIES.map((bounty) => (
          <div key={bounty.label} className="rounded border border-bench-line bg-bench-panel-2 p-3">
            <div className="text-sm font-semibold text-bench-text">{bounty.label}</div>
            <code className="mt-2 block break-all font-mono text-xs text-bench-muted">{bounty.command}</code>
            <button
              type="button"
              className="mt-3 rounded border border-bench-accent/45 px-3 py-1.5 text-xs font-semibold uppercase text-bench-accent hover:bg-bench-accent/10"
              onClick={() => copyCommand(bounty.label, bounty.command, setCopied)}
            >
              {copied === bounty.label ? "Copied" : "Copy CLI"}
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}

function copyCommand(label: string, command: string, setCopied: (label: string | null) => void): void {
  void navigator.clipboard
    .writeText(command)
    .then(() => {
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1200);
    })
    .catch((error: unknown) => {
      if (error instanceof Error) {
        console.warn(`Could not copy command: ${error.message}`);
        return;
      }
      console.warn("Could not copy command.");
    });
}
