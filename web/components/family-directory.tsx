import Link from "next/link";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { familySummaries } from "@/lib/families";
import { formatScore } from "@/lib/format";
import type { IndexModel } from "@/lib/schemas";

export function FamilyDirectory({ models }: { readonly models: readonly IndexModel[] }) {
  const families = familySummaries(models);
  return (
    <section id="families" className="scroll-mt-24 overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82">
      <div className="border-b border-bench-line px-5 py-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Primary browse path</p>
        <h1 className="mt-1 text-2xl font-semibold text-bench-text">Browse by model family</h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Start with the base-model family, then compare its fine-tunes, distills, quants, reported runs, VRAM,
          and per-axis results in one place.
        </p>
      </div>
      <div className="grid gap-px bg-bench-line sm:grid-cols-2 xl:grid-cols-3">
        {families.map((summary) => (
          <article id={summary.slug} key={summary.family} className="scroll-mt-48 bg-bench-panel p-4 sm:scroll-mt-32 lg:scroll-mt-24">
            <div className="flex items-center gap-2">
              <FamilyLogoMark modelLabel={summary.family} size={20} />
              <h3 className="font-semibold text-bench-text">
                <Link href={`/families/${summary.slug}`} className="hover:text-bench-accent">
                  {summary.family}
                </Link>
              </h3>
            </div>
            <p className="mt-2 font-mono text-xs text-bench-muted">
              {summary.models.length} model{summary.models.length === 1 ? "" : "s"}
              {summary.bestScore === null ? " · awaiting a complete run" : ` · best ${formatScore(summary.bestScore)}`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {summary.models.slice(0, 5).map(({ model }) => (
                <Link
                  key={model.slug}
                  href={`/model/${model.slug}`}
                  className="rounded border border-bench-line px-2 py-1 text-xs text-bench-muted hover:border-bench-accent hover:text-bench-text"
                >
                  {model.model_label}
                </Link>
              ))}
            </div>
            <Link href={`/families/${summary.slug}`} className="mt-4 inline-flex text-sm font-semibold text-bench-accent hover:underline">
              View family →
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
