"use client";

import { useState } from "react";

export function CopyButton({ value, label = "Copy" }: { readonly value: string; readonly label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="rounded border border-bench-line px-3 py-1.5 font-mono text-xs uppercase text-bench-muted transition-colors hover:border-bench-accent hover:text-bench-accent"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? <span role="status">Copied</span> : label}
    </button>
  );
}
