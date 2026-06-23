"use client";

import { useState } from "react";

export function CopyButton({ value, label = "Copy" }: { readonly value: string; readonly label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="rounded border border-bench-line px-2 py-1 font-mono text-[11px] uppercase text-bench-muted transition-colors hover:border-bench-accent hover:text-bench-accent"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
