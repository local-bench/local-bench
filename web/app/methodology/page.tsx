import { Breadcrumbs } from "@/components/breadcrumbs";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";

type Attribution = {
  readonly name: string;
  readonly owner: string;
  readonly license: string;
  readonly role: string;
};

const HEADLINE_SOURCES: readonly Attribution[] = [
  { name: "AppWorld-C", owner: "AppWorld authors", license: "Apache-2.0", role: "Agentic axis task-success module." },
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
    name: "BigCodeBench-Hard Instruct",
    owner: "BigCodeBench authors",
    license: "Apache-2.0",
    role: "Coding axis generation tasks scored by hardened execution.",
  },
  {
    name: "OlymMATH-Hard",
    owner: "OlymMATH authors",
    license: "MIT",
    role: "Math axis hard olympiad-style item set.",
  },
  {
    name: "AMO",
    owner: "AMO-Bench authors",
    license: "MIT",
    role: "Math axis newly-authored olympiad-style item set.",
  },
];

const CANDIDATE_SOURCES: readonly Attribution[] = [
  {
    name: "LiveCodeBench / RULER / BFCL expansions",
    owner: "LiveCodeBench authors / NVIDIA / Gorilla LLM and UC Berkeley",
    license: "various open licenses",
    role: "Legacy or candidate diagnostic modules credited in their suite manifests.",
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
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Methodology" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
          suite-v2 | index-v3.0 methodology
        </p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">How local-bench scores runs</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}):
          40% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, 15% Coding, and 5% Math.
          Static ranked rows use the no-agentic five-axis profile: 25% Knowledge, 25% Instruction-Following,
          20% Tool calling, 20% Coding, and 10% Math.
          {` ${LOCAL_INTELLIGENCE_INDEX_PROFILE}`} stays visible beside every score.
        </p>
      </header>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What index-v3.0 measures</h2>
        <p>
          The Index is a weighted arithmetic mean of measured, judge-free axes. Agentic is AppWorld-C task success
          rate. Knowledge is MMLU-Pro. Instruction is IFBench. Tool calling is tc_json_v1 structural tool selection
          and argument construction. Coding is BigCodeBench-Hard Instruct execution pass rate. Math combines
          OlymMATH-Hard and AMO.
        </p>
        <p>
          The static ranked Index removes Agentic and reweights the remaining five axes. Static-Core measures only
          Knowledge, Instruction, Tool calling, and Math; it has no sandbox, no Agentic, and no verified Coding, so it is
          an unranked diagnostic release and is not comparable to ranked static.
        </p>
        <h3 className="text-lg font-semibold text-bench-text">Why the Index is not a parameter-count score</h3>
        <p>
          The Local Intelligence Index is a fixed, published weighted average of six local-use capabilities measured
          under the same generated-token budget — not a proxy for model size. Larger models often gain on knowledge,
          math, and agentic tasks, but smaller instruction-tuned models can legitimately close the headline gap by
          following instructions better, producing stronger executable code, or tying on tool-call structure. A 12B
          model landing within a few points of a 27B is expected behavior on this index, and the per-axis columns show
          exactly where each model earns or loses its score.
        </p>
        <p>
          <span className="text-bench-text">Agentic headroom is deliberate.</span> Low agentic scores on today&apos;s
          board are expected: this axis is not rescaled upward to make current models look more spread out, so future
          local models that are genuinely capable agents have room to separate rather than saturating the benchmark.
        </p>
        <p>
          <span className="text-bench-text">The agentic budget cap is a benchmark restriction, not a usage claim.</span>{" "}
          Agentic tasks run under the same bounded token budget and per-task time limit as every other axis. That is a
          constraint we impose for comparability and feasible run times, not a claim that local agents need to be
          token-efficient — at home, letting a model think longer is essentially free. A model cut off by the budget
          scores the same as one that had no idea, so thinking-heavy models may perform better in unbounded local use
          than their agentic score here suggests.
        </p>
        <p>
          <span className="text-bench-text">Tool calling scope note.</span> The tool-calling axis measures structural
          JSON tool selection and argument construction (tc_json_v1), not full real-world tool-use competence. The
          first ranked rows show low spread on this axis; a harder versioned itemset is planned, and v1 history will
          be preserved when it lands.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Lane and ranking rules</h2>
        <p>
          Ranked rows run the bounded-final lane. Each item gets the same total generated-token budget for that item;
          optional thinking is force-closed inside that budget, and only the final answer is scored. Code items carry a
          larger final-answer reserve of 4096 tokens, while ordinary bounded-final items default to 1024.
        </p>
        <p>
          Execution profiles replace family gating. Eligibility is audits, conformance, and an allowlisted profile digest,
          never the model family. Legacy v1-lane rows keep their lane and index labels until they are re-run; the default
          board shows only the current index identity.
        </p>
        <p>
          The &ldquo;best at its size&rdquo; tag and the dotted line on the front-page chart mark the size-vs-score
          Pareto frontier: a model is on it when no measured model is both higher-scoring and smaller (by the benchmarked
          artifact&rsquo;s on-disk size plus estimated KV cache). It is a value-per-VRAM marker computed from point
          estimates, not a capability tier. The chart shows one point per weights family &mdash; the best measured
          variant across a base model, its fine-tunes, and their quants &mdash; while each model page compares variants
          within the family.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Coding execution and trust</h2>
        <p>
          Every ranked bundle must include code artifacts; the ranked Coding score is produced by maintainer project
          re-execution in a hardened rootless sandbox, so submitters do not need Docker and self-reported execution
          verdicts never rank.
        </p>
        <p>
          The Coding axis reports pass rate over the 141 sandbox-scoreable BigCodeBench-Hard items; seven
          network/data-dependent upstream items are excluded as unscoreable under mandatory network isolation. lcb, the
          old LiveCodeBench output-prediction proxy, is legacy diagnostic data and is never pooled into index-v3.0.
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
            <span className="text-bench-text">Text and math axes: always re-scored.</span> For every accepted bundle —
            project-run or community — transcript-scored axes are independently recomputed against the frozen,
            sha256-pinned item sets. A submitted score never enters the board as claimed, so fabricated static scores do
            not survive.
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
            <span className="text-bench-text">Coding axis: artifact-backed.</span> The submitted bundle carries code
            artifacts, but the ranked verdict is the maintainer re-execution result. Self-reported execution verdicts are
            displayed only as diagnostics.
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
          verified. Coding execution is stricter: self-reported execution verdicts never rank. Until then, treat labels as
          what they are: re-scored means recomputed from your transcripts, attested means cryptographically signed by the
          project at verdict time, self-reported means taken at your word, and none of them proves model identity.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Determinism and reproducibility</h2>
        <p>{LAUNCH_FREEZE.determinismWording}</p>
        <p>
          Every displayed score carries a bootstrap confidence interval. Repeatability, paired quant-delta, and
          generalization are kept separate. Per-axis confidence intervals are part of the score display; coding deltas
          under about 8-10 raw points are not ranking claims unless rank containment and intervals support that read.
          Quick-tier fixed-item runs are personal estimates and stay unranked; only Standard-tier runs can be ranked.
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
          The board is a point-in-time snapshot. Run receipts carry their suite, lane, scorecard, and item-set hashes;
          legacy receipts keep their original labels until they are re-run under the current release.
        </p>
        <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-bench-line bg-bench-line sm:grid-cols-2">
          <div className="bg-bench-bg px-4 py-3">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">As-of date</dt>
            <dd className="mt-1 text-sm text-bench-text">{LAUNCH_FREEZE.asOfDate}</dd>
          </div>
          <div className="bg-bench-bg px-4 py-3">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">Index identity</dt>
            <dd className="mt-1 text-sm text-bench-text">suite-v2 / index-v3.0</dd>
          </div>
          <div className="bg-bench-bg px-4 py-3 sm:col-span-2">
            <dt className="font-mono text-[11px] uppercase tracking-wide text-bench-muted/70">Board sha256</dt>
            <dd className="mt-1 break-all font-mono text-xs text-bench-text">{LAUNCH_FREEZE.boardSha256}</dd>
          </div>
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
          their respective owners; listing a model is benchmark evaluation, not an endorsement by, or of, its
          maker.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Editorial versioning</h2>
        <p>
          Domain weights are explicit editorial choices tied to named releases: index-v3.0 for the full six-axis
          Index, static-suite-v2 for the ranked no-agentic Index, and static-core diagnostic for the unranked no-sandbox
          profile. Weights live in the scorer axis registry and are hashed into the scorecard, so history cannot be
          silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
