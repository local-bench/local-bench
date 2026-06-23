import Link from "next/link";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { getIndexData } from "@/lib/data";

export default async function MethodologyPage() {
  const index = await getIndexData();

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Link href="/" className="text-sm text-bench-accent hover:underline">
        Back to leaderboard
      </Link>
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs uppercase text-bench-accent">
          {index.suite_version} · {index.index_version} methodology
        </p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">How local-bench scores runs</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}).
          {` ${LOCAL_INTELLIGENCE_INDEX_PROFILE}`} stays visible beside it, while candidate axes wait for
          validation before any Overall tier exists.
        </p>
      </header>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Three estimands stay separate</h2>
        <p>
          Repeatability asks whether the same setup reproduces on the same items. Paired quant-delta asks whether
          one quant differs from another on these frozen items. Generalization asks whether the result transfers to
          the universe of similar questions. Each has a different uncertainty story, so the UI avoids universal
          claims from quick-tier fixed-item runs.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Absolute chance-corrected normalization</h2>
        <p>
          Knowledge uses MMLU-Pro and instruction uses IFBench. The {LOCAL_INTELLIGENCE_INDEX_NAME} (
          {LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) is the equal-weighted arithmetic mean of those chance-corrected
          Knowledge and Instruction axis scores, shown on a 0..100 scale for readability.
        </p>
        <p>
          Math, Coding-exec, and Agentic are candidate axes. They remain outside the Intelligence Index until measured
          discrimination earns promotion; a full intelligence claim is reserved for an evidence-backed Overall tier.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Lanes, tiers, and uncertainty</h2>
        <p>
          Reasoning lanes are not mixed: native, capped, and answer-only runs compare within their own lane.
          Quick tier is an unranked personal estimate; Standard tier is the ranked board. Fixed item sets make runs
          reproducible, and bootstrap CIs make uncertainty visible beside every score.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Editorial versioning</h2>
        <p>
          Domain weights are explicit editorial choices tied to an index version. Suite versions tag the item sets
          independently, so scoring changes and item changes are visible instead of silent.
        </p>
      </section>
    </main>
  );
}
