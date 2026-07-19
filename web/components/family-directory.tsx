import Link from "next/link";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { formatScore } from "@/lib/format";
import { isFullIndexRow } from "@/lib/leaderboard-score";
import type { IndexModel } from "@/lib/schemas";

type FamilySummary = {
  readonly bestScore: number | null;
  readonly family: string;
  readonly models: readonly IndexModel[];
};

export function FamilyDirectory({ models }: { readonly models: readonly IndexModel[] }) {
  const families = familySummaries(models);
  return (
    <section id="families" className="scroll-mt-24 overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82">
      <div className="border-b border-bench-line px-5 py-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Primary view</p>
        <h2 className="mt-1 text-2xl font-semibold text-bench-text">Browse by model family</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Start with the base-model family, then compare its fine-tunes, distills, quants, reported runs, VRAM,
          and per-axis results in one place.
        </p>
      </div>
      <div className="grid gap-px bg-bench-line sm:grid-cols-2 xl:grid-cols-3">
        {families.map((summary) => (
          <article key={summary.family} className="bg-bench-panel p-4">
            <div className="flex items-center gap-2">
              <FamilyLogoMark modelLabel={summary.family} size={20} />
              <h3 className="font-semibold text-bench-text">{summary.family}</h3>
            </div>
            <p className="mt-2 font-mono text-xs text-bench-muted">
              {summary.models.length} model{summary.models.length === 1 ? "" : "s"}
              {summary.bestScore === null ? " · awaiting a complete run" : ` · best ${formatScore(summary.bestScore)}`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {summary.models.slice(0, 5).map((model) => (
                <Link
                  key={model.slug}
                  href={`/model/${model.slug}`}
                  className="rounded border border-bench-line px-2 py-1 text-xs text-bench-muted hover:border-bench-accent hover:text-bench-text"
                >
                  {model.model_label}
                </Link>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function familySummaries(models: readonly IndexModel[]): readonly FamilySummary[] {
  const byFamily = new Map<string, IndexModel[]>();
  for (const model of models) byFamily.set(model.family, [...(byFamily.get(model.family) ?? []), model]);
  return [...byFamily.entries()].map(([family, familyModels]) => {
    const scores = familyModels.filter(isFullIndexRow).flatMap((model) => {
      const score = model.composite_full ?? model.composite;
      return score === null || score === undefined ? [] : [score.point];
    });
    return {
      bestScore: scores.length === 0 ? null : Math.max(...scores),
      family,
      models: familyModels.sort((left, right) => left.model_label.localeCompare(right.model_label)),
    };
  }).sort((left, right) => (right.bestScore ?? -1) - (left.bestScore ?? -1) || left.family.localeCompare(right.family));
}
