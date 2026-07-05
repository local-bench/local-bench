import { Breadcrumbs } from "@/components/breadcrumbs";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";
import { getIndexData } from "@/lib/data";

type Attribution = {
  readonly name: string;
  readonly owner: string;
  readonly license: string;
  readonly role: string;
};

const HEADLINE_SOURCES: readonly Attribution[] = [
  { name: "MMLU-Pro", owner: "TIGER-Lab", license: "MIT", role: "Knowledge axis item set (400 items)." },
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

export default async function MethodologyPage() {
  const index = await getIndexData();

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Methodology" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
          {index.suite_version} | {index.index_version} methodology
        </p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">How local-bench scores runs</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}):
          50% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, and 10% Coding.
          Rows that skip the agentic axis rank on a separate renormalized static composite instead.
          {` ${LOCAL_INTELLIGENCE_INDEX_PROFILE}`} stays visible beside every score.
        </p>
      </header>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What the headline Index is</h2>
        <p>
          The Index is a weighted arithmetic mean of measured, judge-free axes. Agentic is AppWorld-C task
          success rate. Knowledge is MMLU-Pro. Instruction is IFBench. Tool calling is tc_json_v1 structural
          tool selection and argument construction. Coding is the lightweight LiveCodeBench output-prediction
          proxy used by standard runs so the suite remains practical on local hardware.
        </p>
        <p>
          Math, Long-Context, and BigCodeBench-Hard coding-exec remain diagnostic or opt-in expansion modules;
          they never enter the headline number.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">One suite, one headline rank — and a no-agentic lane</h2>
        <p>
          local-bench is one benchmark: one frozen suite, one methodology, one headline rank. But the agentic
          axis executes model-written code in a Linux sandbox, and not every platform can run that. Rather than
          rejecting those runs or fudging them a number, runs without agentic get a clearly-subordinate fallback
          lane:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <span className="text-bench-text">index-v2.1</span> — the headline rank: Agentic 50 / Knowledge 15 /
            Instruction-Following 15 / Tool calling 10 / Coding 10. Requires all five headline axes.
          </li>
          <li>
            <span className="text-bench-text">static-suite-v1</span> — the no-agentic lane: Knowledge 30 /
            Instruction-Following 30 / Tool calling 20 / Coding 20, renormalized over the four static axes.
            It appears as its own table, only when such rows exist, and ranks only against itself.
          </li>
        </ul>
        <p>
          The two are never score-comparable, and that is deliberate. Renormalizing without agentic produces
          systematically higher numbers — the same model can score 40 on the main index and 60 renormalized —
          so letting four-axis runs into the headline rank would reward skipping the hardest, longest axis.
          The quarantined lane removes that incentive: you cannot dodge agentic and place higher for it. Rows
          with fewer than the four static axes display per-axis scores and confidence intervals only and are
          not ranked. Both weight sets are explicit editorial choices, versioned and hashed like everything
          else (see Editorial versioning below).
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Why the coding split exists</h2>
        <p>
          The standard Coding axis is intentionally fast and repeatable: it asks the model to predict LiveCodeBench
          testcase outputs without running generated code. The stronger coding-exec module runs BigCodeBench-Hard
          in a sandbox and is the right long-term generation benchmark, but it stays opt-in until the execution lane
          is cheap, hardened, and repeatable enough for regular leaderboard submissions.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">One lane: capped-thinking</h2>
        <p>
          Reasoning lanes are never mixed. The ranked board is the <span className="text-bench-text">capped-thinking</span>{" "}
          lane: reasoning is on, with a graceful 8192-token reasoning budget and a 16384-token answer ceiling.
          Answer-only and uncapped-API runs compare only within their own lane and never merge into the headline.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Who submits, and what the labels mean</h2>
        <p>
          Anyone can submit a run. Submitters are identified by a locally generated Ed25519 key — no account,
          no email — and accepted rows can carry an optional display name as credit. Every row also carries
          labels that say exactly how much checking stands behind each number:
        </p>
        <ul className="list-disc space-y-3 pl-5">
          <li>
            <span className="text-bench-text">Run by: local-bench vs community.</span> Rows the project
            measured on its own hardware are credited to local-bench; community rows carry the
            submitter&apos;s credit line. The server derives this; submitters cannot set it.
          </li>
          <li>
            <span className="text-bench-text">Static axes: always re-scored.</span> For every accepted bundle —
            project-run or community — the four static axes are independently recomputed from the submitted
            transcripts against the frozen, sha256-pinned item sets. A submitted static score never enters the
            board as claimed, so fabricated static scores do not survive.
          </li>
          <li>
            <span className="text-bench-text">Agentic axis: provenance-labeled, not re-scored.</span> Agentic
            verdicts are produced by live task execution and cannot be recomputed from a transcript after the
            fact, so carried verdicts wear a provenance label instead.{" "}
            <span className="text-bench-text">Attested</span> means every carried verdict has a valid Ed25519
            attestation, signed at the moment the sandbox verdict was accepted and checked against the
            project&apos;s pinned attester key — project-run rows carry this. (One historical local-bench row, the
            first ranked run, predates per-verdict signing and is grandfathered as attested by bundle hash;
            it was produced by the same host-derived verdict path.){" "}
            <span className="text-bench-text">Self-reported</span> means the verdicts were carried exactly as
            submitted and counted in the composite without independent verification — community rows carry
            this today. The label never changes the score; it tells you how much to trust it.
          </li>
          <li>
            <span className="text-bench-text">Moderation: nothing auto-publishes.</span> Every submission lands
            as pending. The maintainer reviews it — including plausibility of self-reported agentic results
            against the independently re-scored static axes — and must explicitly accept it before the board is
            regenerated and deployed.
          </li>
        </ul>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Threat posture, honestly</h2>
        <p>
          An OpenAI-compatible endpoint can be a cheat proxy: it can look up public answers and fabricate
          plausible transcripts, and no server-side check proves which model — or whose hardware — actually
          produced a bundle. Re-scoring closes the cheapest fraud (claimed static scores that don&apos;t match the
          transcripts), signed attestations make the project&apos;s own agentic verdicts tamper-evident, and
          manual review is the backstop for everything else; but a determined submitter could still fabricate a
          self-reported agentic result, which is exactly why the board labels it self-reported rather than
          verified. Spot replication of community agentic runs is on the roadmap. Until then, treat labels as
          what they are: re-scored means recomputed from your transcripts, attested means cryptographically
          signed by the project at verdict time, self-reported means taken at your word — and none of them
          proves model identity.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Determinism and reproducibility</h2>
        <p>{LAUNCH_FREEZE.determinismWording}</p>
        <p>
          Every displayed score carries a bootstrap confidence interval. Repeatability, paired quant-delta, and
          generalization are kept separate. Quick-tier fixed-item runs are personal estimates and stay unranked;
          only Standard-tier runs can be ranked.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Contamination and public items</h2>
        <p>
          Several inputs are public benchmarks, so local-bench does not pretend contamination is impossible. The
          item subsets are frozen and sha256-pinned, contamination status is shown per run, and small leaderboard
          gaps should be treated as uncertainty unless they clear the reported confidence intervals.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Quant degradation is drift, not just accuracy</h2>
        <p>
          Model pages report quantization as a trade-off across accuracy, VRAM, speed, tokens-to-answer, and output
          drift against a full-precision or explicitly labeled proxy reference. Drift is labeled as drift, never as
          a hidden task score.
        </p>
      </section>

      <section id="frozen" className="space-y-3 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Frozen as of {LAUNCH_FREEZE.asOfDate}</h2>
        <p>
          The board is a point-in-time snapshot. These identifiers pin exactly what produced it; the same values
          appear in the site footer on every page.
        </p>
        <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-bench-line bg-bench-line sm:grid-cols-2">
          <div className="bg-bench-bg px-4 py-3">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">As-of date</dt>
            <dd className="mt-1 text-sm text-bench-text">{LAUNCH_FREEZE.asOfDate}</dd>
          </div>
          <div className="bg-bench-bg px-4 py-3">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">Scorecard version</dt>
            <dd className="mt-1 text-sm text-bench-text">{LAUNCH_FREEZE.scorecardVersion}</dd>
          </div>
          <div className="bg-bench-bg px-4 py-3 sm:col-span-2">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">Board sha256</dt>
            <dd className="mt-1 break-all font-mono text-xs text-bench-text">{LAUNCH_FREEZE.boardSha256}</dd>
          </div>
          {LAUNCH_FREEZE.itemSetHashes.map((set) => (
            <div key={set.file} className="bg-bench-bg px-4 py-3 sm:col-span-2">
              <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">
                {set.label} | {set.file}
              </dt>
              <dd className="mt-1 break-all font-mono text-xs text-bench-text">{set.sha256}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm">Benchmark item licenses and scorer attribution are listed in the next section.</p>
      </section>

      <section id="licenses" className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Benchmark sources &amp; licenses</h2>
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
        <p className="pt-1">Candidate and opt-in modules draw on additional sources, credited the same way:</p>
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
          maker.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Editorial versioning</h2>
        <p>
          Domain weights are explicit editorial choices tied to a named composite version — index-v2.1 for the
          full five-axis index, static-suite-v1 for the static composite — and item sets are tagged by a separate
          suite version. Weights live in the scorer axis registry and are hashed into the scorecard, so history
          cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
