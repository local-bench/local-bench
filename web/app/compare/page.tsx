import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { CompareLivePicker } from "@/components/compare-live-picker";
import { getCompareConfigs } from "@/lib/compare";
import { communityArtifactDetails } from "@/lib/community-artifact-details";
import { getCommunityBoardRows } from "@/lib/community-data";
import { getFineTuneComparePresets, getIndexData, getModelData } from "@/lib/data";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata(
  "Compare local LLM runs",
  "Compare two local LLM model and quant configurations across benchmark quality, VRAM, speed, and per-axis results.",
);

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
      <Breadcrumbs items={[{ label: "Model families", href: "/families/" }, { label: "Compare" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Head-to-head</p>
        <h1 className="mt-3 text-4xl font-semibold text-bench-text">Compare model configs</h1>
        <p className="mt-2 max-w-3xl leading-7 text-bench-muted">
          Pick two model × quant rows and inspect quality, effective VRAM, speed, and per-axis
          winners side by side. Ranks only compare within the same{" "}
          <Link
            className="underline decoration-bench-line underline-offset-2 hover:text-bench-accent"
            href="/methodology/#serving-engine-lanes"
            title="A lane fixes the serving engine and benchmark protocol used for a comparable run"
          >
            lane
          </Link>.
        </p>
      </header>
      <CompareLivePicker
        communityArtifactDetails={communityArtifactDetails(models)}
        communityRows={communityRows ?? []}
        fineTunePresets={fineTunePresets}
        projectConfigs={projectConfigs}
      />
    </main>
  );
}
