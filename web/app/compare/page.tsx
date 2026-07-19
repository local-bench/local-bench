import { Breadcrumbs } from "@/components/breadcrumbs";
import { CompareLivePicker } from "@/components/compare-live-picker";
import { getCompareConfigs } from "@/lib/compare";
import { getCommunityBoardRows } from "@/lib/community-data";
import { getFineTuneComparePresets, getIndexData, getModelData } from "@/lib/data";

export default async function ComparePage() {
  const [index, fineTunePresets, communityRows] = await Promise.all([
    getIndexData(),
    getFineTuneComparePresets(),
    getCommunityBoardRows(),
  ]);
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  const projectConfigs = getCompareConfigs(models);

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Model families", href: "/" }, { label: "Compare" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Head-to-head</p>
        <h1 className="mt-3 text-4xl font-semibold text-bench-text">Compare model configs</h1>
        <p className="mt-2 max-w-3xl leading-7 text-bench-muted">
          Pick two model × quant rows and inspect quality, effective VRAM, speed, and per-axis
          winners side by side. Ranks only compare within the same lane.
        </p>
      </header>
      <CompareLivePicker
        communityRows={communityRows ?? []}
        fineTunePresets={fineTunePresets}
        projectConfigs={projectConfigs}
      />
    </main>
  );
}
