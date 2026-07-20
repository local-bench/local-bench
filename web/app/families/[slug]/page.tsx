import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { getIndexData } from "@/lib/data";
import { familySummaries, type FamilySummary } from "@/lib/families";
import { formatScore } from "@/lib/format";

export const dynamicParams = false;

type PageProps = {
  readonly params: Promise<{
    readonly slug: string;
  }>;
};

export async function generateStaticParams(): Promise<{ slug: string }[]> {
  const index = await getIndexData();
  return familySummaries(index.models).map((summary) => ({ slug: summary.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const summary = await getFamilySummary(slug);
  if (summary === undefined) notFound();
  const modelLabel = summary.models.length === 1 ? "model" : "models";
  return {
    title: `${summary.family} models | local-bench`,
    description: `Browse ${summary.models.length} ${summary.family} ${modelLabel}, measured results, and catalog entries on local-bench.`,
  };
}

export default async function FamilyPage({ params }: PageProps) {
  const { slug } = await params;
  const summary = await getFamilySummary(slug);
  if (summary === undefined) notFound();

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Model families", href: "/families" }, { label: summary.family }]} />
      <header className="rounded-lg border border-bench-line bg-bench-panel/82 p-5">
        <h1 className="flex items-center gap-3 text-4xl font-semibold text-bench-text">
          <FamilyLogoMark familyName={summary.family} modelLabel={summary.family} size={32} />
          {summary.family}
        </h1>
        <p className="mt-3 font-mono text-sm text-bench-muted">
          {summary.models.length} model{summary.models.length === 1 ? "" : "s"}
          {summary.bestScore === null
            ? " · awaiting a complete run"
            : ` · best ${formatScore(summary.bestScore)}`}
        </p>
      </header>
      <section className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82">
        <div className="border-b border-bench-line px-5 py-4">
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Family catalog</p>
          <h2 className="mt-1 text-2xl font-semibold text-bench-text">All {summary.family} models</h2>
          <p className="mt-1 text-sm leading-6 text-bench-muted">
            Complete headline runs are listed first by composite score, followed by models awaiting a complete run.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <thead className="bg-white/[0.03] text-left font-mono text-xs uppercase tracking-wide text-bench-muted">
              <tr>
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Headline composite</th>
              </tr>
            </thead>
            <tbody>
              {summary.models.map(({ model, score }) => (
                <tr key={model.slug} className="border-t border-bench-line/70">
                  <td className="px-5 py-3">
                    <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                      {model.model_label}
                    </Link>
                  </td>
                  <td className="px-5 py-3 font-mono text-bench-muted">
                    {score === null ? "awaiting a complete run" : formatScore(score)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

async function getFamilySummary(slug: string): Promise<FamilySummary | undefined> {
  const index = await getIndexData();
  return familySummaries(index.models).find((summary) => summary.slug === slug);
}
