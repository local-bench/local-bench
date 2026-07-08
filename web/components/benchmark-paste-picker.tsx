"use client";

import { QUANT_OPTIONS } from "@/lib/quant";

export function PasteModelPicker(props: {
  readonly pasteRepo: string;
  readonly onPasteRepo: (value: string) => void;
  readonly pasteHfModelId: string;
  readonly onPasteHfModelId: (value: string) => void;
  readonly pasteQuant: string;
  readonly onPasteQuant: (value: string) => void;
}) {
  const selectClass =
    "rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent";

  return (
    <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_140px]">
      <label className="flex flex-col gap-1 font-mono text-[11px] uppercase text-bench-muted">
        HF GGUF repo (owner/repo)
        <input
          type="text"
          className={selectClass}
          placeholder="owner/repo-GGUF"
          aria-label="HF GGUF repo"
          value={props.pasteRepo}
          onChange={(event) => props.onPasteRepo(event.currentTarget.value)}
        />
      </label>
      <label className="flex flex-col gap-1 font-mono text-[11px] uppercase text-bench-muted">
        Exact HF model repo
        <input
          type="text"
          className={selectClass}
          placeholder="owner/repo"
          aria-label="Exact HF model repo"
          value={props.pasteHfModelId}
          onChange={(event) => props.onPasteHfModelId(event.currentTarget.value)}
        />
      </label>
      <label className="flex flex-col gap-1 font-mono text-[11px] uppercase text-bench-muted">
        Quant
        <select className={selectClass} aria-label="Quant" value={props.pasteQuant} onChange={(event) => props.onPasteQuant(event.currentTarget.value)}>
          {QUANT_OPTIONS.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <p className="font-mono text-[11px] text-bench-muted md:col-span-3">
        Use the fine-tune&apos;s own non-GGUF repo. Do not enter the base model unless this GGUF is the base model.
      </p>
      <p className="font-mono text-[11px] text-bench-muted md:col-span-3">
        Pick the quant label that exists in the GGUF repo — if llama-server reports no matching file, use the exact quant
        shown on Hugging Face.
      </p>
    </div>
  );
}
