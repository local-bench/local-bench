import { KindBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import { getModelPageData, getModelStaticParams } from "@/lib/data";

export const dynamicParams = false;

type PageProps = {
  readonly params: Promise<{
    readonly slug: string;
  }>;
};

export async function generateStaticParams(): Promise<{ slug: string }[]> {
  return [...(await getModelStaticParams())];
}

export default async function ModelPage({ params }: PageProps) {
  const { slug } = await params;
  const { model, anchorRuns } = await getModelPageData(slug);
  const measuredRuns = model.runs.filter((run) => run.score_status === "measured");

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          <div className="flex flex-wrap gap-2">
            <KindBadge kind={model.kind} runCount={measuredRuns.length} />
          </div>
          <h1 className="mt-3 text-4xl font-semibold text-bench-text">{model.model_label}</h1>
          <p className="mt-2 max-w-3xl text-bench-muted">
            This model&apos;s quants and distills, ranked by the Local Intelligence Index. Pick the smallest variant that
            holds the quality you need — the VRAM and speed columns show what each rung costs.
          </p>
        </div>
      </header>
      <ModelVariantBoard model={model} />
      <ModelScatter model={model} anchorRuns={anchorRuns} />
    </main>
  );
}
