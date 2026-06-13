import Link from "next/link";
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
          The sortable number is a compact index. The three-axis profile remains the diagnostic view for
          understanding what changed and where a setup is strong or weak.
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
          MMLU-Pro is adjusted from a 10% chance baseline, while IFEval and genmath use a zero baseline. The
          composite is the equal-weighted arithmetic mean of those chance-corrected axis scores, shown on a 0..100
          scale for readability.
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
