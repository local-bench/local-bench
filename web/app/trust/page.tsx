import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";

type Attribution = {
  readonly name: string;
  readonly owner: string;
  readonly license: string;
  readonly role: string;
};

const HEADLINE_SOURCES: readonly Attribution[] = [
  {
    name: "MMLU-Pro",
    owner: "TIGER-Lab",
    license: "MIT",
    role: "Knowledge axis item set (400 items).",
  },
  {
    name: "IFBench",
    owner: "Allen Institute for AI (Ai2)",
    license: "ODC-BY-1.0 (dataset)",
    role: "Instruction-Following axis item set (294 items).",
  },
  {
    name: "IFEval checker",
    owner: "Google Research",
    license: "Apache-2.0",
    role: "Instruction-following verifier logic adapted into the local-bench scorer.",
  },
  {
    name: "TC-JSON v1",
    owner: "local-bench + Gorilla LLM / UC Berkeley",
    license: "Apache-2.0",
    role: "Tool-calling axis item set and structural JSON scorer (330 items).",
  },
  {
    name: "LiveCodeBench",
    owner: "LiveCodeBench authors",
    license: "CC-BY-4.0 item data / MIT harness",
    role: "Coding proxy axis item set for output prediction (129 items).",
  },
];

const CANDIDATE_SOURCES: readonly Attribution[] = [
  {
    name: "BFCL / BigCodeBench / RULER / math expansions",
    owner: "Gorilla LLM / UC Berkeley",
    license: "various open licenses",
    role: "Candidate and opt-in expansion modules credited in their suite manifests.",
  },
];

function AttributionRow({ source }: { readonly source: Attribution }) {
  return (
    <div className="flex flex-col gap-1 border-b border-bench-line/60 py-3 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <div className="min-w-0 sm:max-w-md">
        <p className="text-sm font-semibold text-bench-text">{source.name}</p>
        <p className="text-xs text-bench-muted">{source.role}</p>
      </div>
      <div className="shrink-0 text-xs text-bench-muted sm:text-right">
        <p>{source.owner}</p>
        <p className="font-mono text-bench-accent">{source.license}</p>
      </div>
    </div>
  );
}

export default function TrustPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Trust & licenses" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">trust, threat model and licenses</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Honesty is the credibility signal</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          local-bench never treats a transcript as proof of model identity. The trust unit is replication, not a
          one-off &ldquo;verified&rdquo; claim.
        </p>
      </header>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Labels mean exactly what they say</h2>
        <p>
          Community re-scored means the submitted bundle was re-scored from its transcript and accepted for
          maintainer review. It does not verify the model, hardware, or runtime identity. Replicated is reserved
          for future results reproduced by at least three independent accounts. Anchor runs are project-maintained
          references against the same frozen suite.
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
          The {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) and CIs are useful ranking
          signals, but they do not prove model or hardware identity.
        </p>
      </section>
      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Benchmark sources and attribution</h2>
        <p>
          local-bench publishes public suite artifacts, scores, and metadata. No model weights, GGUF files, API
          keys, or private runtime credentials are hosted here. The frozen item sets behind the headline Index
          are derived from the following sources, each used under its own license:
        </p>
        <div className="rounded-lg border border-bench-line bg-bench-panel/50 px-4 py-2">
          {HEADLINE_SOURCES.map((source) => (
            <AttributionRow key={source.name} source={source} />
          ))}
        </div>
        <p className="pt-1">
          Candidate and opt-in modules draw on additional sources, credited the same way:
        </p>
        <div className="rounded-lg border border-bench-line bg-bench-panel/50 px-4 py-2">
          {CANDIDATE_SOURCES.map((source) => (
            <AttributionRow key={source.name} source={source} />
          ))}
        </div>
        <p className="text-sm">
          Full license texts and the complete redistribution notice ship in the repository&rsquo;s{" "}
          <span className="font-mono text-bench-text">NOTICE</span> file and{" "}
          <span className="font-mono text-bench-text">LICENSES/</span> directory. Model names are the property of
          their respective owners; listing a model is benchmark evaluation, not an endorsement by — or of — its
          maker. The suite and scorecard hashes that pin this board appear on the{" "}
          <Link href="/methodology" className="text-bench-accent hover:underline">
            scoring methodology page
          </Link>{" "}
          and in the footer.
        </p>
      </section>
    </main>
  );
}
