import { runtimeDisplay, type RuntimeDisplayInput } from "@/lib/runtime-display";

export function RuntimeBadge({ runtime }: { readonly runtime: RuntimeDisplayInput | null | undefined }) {
  const display = runtimeDisplay(runtime);
  if (display === null) return null;
  return (
    <span
      className="inline-flex rounded border border-bench-accent/35 bg-bench-accent/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-accent"
      title={display.version === null ? `Serving engine: ${display.label}` : `Serving engine: ${display.label} ${display.version}`}
    >
      {display.label}
    </span>
  );
}
