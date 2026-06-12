import Link from "next/link";

export default function TrustPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Link href="/" className="text-sm text-bench-accent hover:underline">
        Back to leaderboard
      </Link>
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs uppercase text-bench-accent">trust and threat model</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Honesty is the credibility signal</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          local-bench never treats a transcript as proof of model identity. The trust unit is replication, not a
          one-off “verified” claim.
        </p>
      </header>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Labels mean exactly what they say</h2>
        <p>
          Community-reported runs are ordinary submitted results. Replicated is reserved for future results
          reproduced by at least three independent accounts. Anchor runs are project-maintained references against
          the same frozen suite.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">A proxy can fake transcripts</h2>
        <p>
          The cheat-proxy attack proves that an OpenAI-compatible endpoint can look up public answers and fabricate
          plausible transcripts. Server-side scoring, timing physics, and hardware plausibility are useful signals,
          but they are not proof.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What improves trust</h2>
        <p>
          Independent replication should converge on the real model distribution. Generated-math private sentinel
          items act as a contamination canary because static answer lookup no longer works when answers are withheld.
          Composite scores and CIs are useful ranking signals, but they do not prove model or hardware identity.
        </p>
      </section>
    </main>
  );
}
