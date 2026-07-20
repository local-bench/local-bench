import Link from "next/link";
import type { IndexModel } from "@/lib/schemas";

// The ~100 score-less catalog shells live BELOW the ranked board, collapsed by default, so they
// never sort into or dwarf the measured rank (board-display contract). Expand = the roadmap of
// models still waiting for their first run.
export function CatalogShells({ models }: { readonly models: readonly IndexModel[] }) {
  if (models.length === 0) {
    return null;
  }
  const sorted = [...models].sort(
    (left, right) => left.family.localeCompare(right.family) || left.model_label.localeCompare(right.model_label),
  );
  return (
    <details className="rounded-lg border border-bench-line bg-bench-panel/50">
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-bench-text">
        Not yet benchmarked — {models.length} catalog models on the roadmap
      </summary>
      <div className="border-t border-bench-line px-4 pt-4">
        <Link className="text-sm font-semibold text-bench-accent hover:underline" href="/submit">
          be the first to submit a run →
        </Link>
      </div>
      <ul className="grid gap-x-6 gap-y-1 px-4 py-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((model) => (
          <li key={model.slug}>
            <Link
              href={`/model/${model.slug}`}
              className="flex items-baseline justify-between gap-2 text-bench-muted hover:text-bench-accent"
            >
              <span className="truncate">{model.model_label}</span>
              <span className="shrink-0 text-xs text-bench-muted/60">{model.family}</span>
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}
