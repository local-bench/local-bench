import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { FamilyModelTableLive } from "@/components/family-community-models";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { getCommunityBoardRows } from "@/lib/community-data";
import { communityRowsWithFamilyPaths } from "@/lib/community-family";
import { getIndexData, getIndexModelsWithArtifacts } from "@/lib/data";
import { familyResolutionContext } from "@/lib/family-resolution-data";
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
  return familySummaries(index.models, familyResolutionContext()).map((summary) => ({ slug: summary.slug }));
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
  const index = await getIndexData();
  const [communityRows, modelsWithArtifacts] = await Promise.all([
    getCommunityBoardRows(),
    getIndexModelsWithArtifacts(index.models),
  ]);
  const resolutionContext = familyResolutionContext(modelsWithArtifacts);
  const summary = familySummaries(index.models, resolutionContext).find((candidate) => candidate.slug === slug);
  if (summary === undefined) notFound();
  const resolvedCommunityRows = communityRows === null
    ? []
    : communityRowsWithFamilyPaths(communityRows, resolutionContext);

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
            Rows with the complete headline profile are listed first by composite score, followed by models awaiting one.
          </p>
        </div>
        <FamilyModelTableLive
          family={summary.family}
          models={summary.models}
          resolutionContext={resolutionContext}
          rows={resolvedCommunityRows}
        />
      </section>
    </main>
  );
}

async function getFamilySummary(slug: string): Promise<FamilySummary | undefined> {
  const index = await getIndexData();
  return familySummaries(index.models, familyResolutionContext()).find((summary) => summary.slug === slug);
}
