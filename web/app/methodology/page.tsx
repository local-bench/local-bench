import { Breadcrumbs } from "@/components/breadcrumbs";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  SEASON_2_INDEX_PROFILE,
  SEASON_2_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";
import { publicProtocolLabel } from "@/lib/board-adapter";
import {
  INDEX_VERSION_V4,
  SEASON_2_DIAGNOSTICS,
  TOOL_USE_FACETS,
  TOOL_USE_WEIGHT,
} from "@/lib/scoring-seasons";

type Attribution = {
  readonly name: string;
  readonly owner: string;
  readonly license: string;
  readonly role: string;
};

const HEADLINE_SOURCES: readonly Attribution[] = [
  { name: "AppWorld-C", owner: "AppWorld authors", license: "Apache-2.0", role: "Agentic-execution facet of the Agentic macro-axis (task-success module)." },
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
      <Breadcrumbs items={[{ label: "Model families", href: "/" }, { label: "Methodology" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
          {publicProtocolLabel(INDEX_VERSION_V4)} | scorecard-v6 methodology
        </p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">How local-bench scores runs</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({SEASON_2_INDEX_QUALIFIER}):
          25% Agentic, 22.5% Knowledge, 22.5% Instruction-Following, 22.5% Coding, and 7.5% Math.
          {` ${SEASON_2_INDEX_PROFILE}`} stays visible beside every score. Season-1 (index-v3.0) results
          remain published as history and diagnostics; the two scales are never directly compared — see the
          season bridge below.
        </p>
      </header>

      <section id="season-2" className="space-y-4 rounded-lg border border-bench-accent/30 bg-bench-panel/55 p-5 text-bench-muted">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
            Season 2 · {publicProtocolLabel(INDEX_VERSION_V4)}
          </p>
          <h2 className="mt-1 text-xl font-semibold text-bench-text">Agentic macro-axis</h2>
        </div>
        <p>
          Season 2 replaces the separate season-1 Agentic and Tool-calling headline axes with one Agentic macro-axis
          (structural data key <span className="font-mono">tool_use</span>, public axis label under {publicProtocolLabel(INDEX_VERSION_V4)}) worth{" "}
          {Math.round(TOOL_USE_WEIGHT * 100)}% of the full Index. Its facets are first scored independently, then
          combined using the declared facet weights below. This is a <span className="font-semibold text-bench-text">bench-normalized weighted mean</span>,
          not item-count pooling: a bench with more test items does not silently gain more influence.
        </p>
        <div className="overflow-hidden rounded border border-bench-line">
          <p className="border-b border-bench-line px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-bench-accent sm:hidden">
            Swipe horizontally for all methodology columns &rarr;
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-[680px] border-collapse text-sm">
            <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wide text-bench-text/85">
              <tr>
                <th className="px-3 py-2">Sub-facet</th>
                <th className="px-3 py-2">Bench</th>
                <th className="px-3 py-2">Declared weight</th>
                <th className="px-3 py-2">Construct</th>
              </tr>
            </thead>
            <tbody>
              {TOOL_USE_FACETS.map((facet) => (
                <tr key={facet.key} className="border-t border-bench-line/70">
                  <td className="px-3 py-2 font-semibold text-bench-text">{facet.label}</td>
                  <td className="px-3 py-2 font-mono text-xs">{facet.bench}</td>
                  <td className="px-3 py-2 font-mono">{Math.round(facet.weight * 100)}%</td>
                  <td className="px-3 py-2">{facet.construct}</td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
        </div>
        <p className="text-sm">
          These are the final ratio-preserving weights after calibration. The table and board breakdown read the same
          constants, so the published split remains a one-place definition.
        </p>

        <div className="space-y-2 border-t border-bench-line pt-4">
          <h3 className="text-lg font-semibold text-bench-text">Unweighted diagnostics</h3>
          <p>
            {SEASON_2_DIAGNOSTICS.map((diagnostic) => diagnostic.label).join(", ")} are displayed when a result carries
            them. They are never weighted and never used for ranking. Call formatting remains coverage-required and
            powers the separate tc_json conformance gate; the other diagnostics are opt-in and not coverage-required.
            BFCL single-turn overlaps the call-formatting material; BFCL multi-turn long-context and RULER 32K also mix
            capability with context and cache limits, so they remain diagnostic evidence rather than headline score inputs.
          </p>
        </div>

        <div className="space-y-2 border-t border-bench-line pt-4">
          <h3 className="text-lg font-semibold text-bench-text">Season 1 → 2 bridge</h3>
          <p>
            Index-v3.0 and index-v4.x composites are different editorial scales and are never directly compared
            (as are index-v4.0 and {publicProtocolLabel(INDEX_VERSION_V4)}, which weight the same axes differently).
            Lineage deltas and ordinary compare views require matching index versions. The versioned season bridge is
            the only sanctioned pairing: for an artifact measured completely in both seasons, it presents the frozen
            v3 composite beside the full v4 composite without treating their numerical gap as a performance delta.
          </p>
          <p>
            Under Option D, an anchor without complete season-2 coverage keeps its season-1 label and season-1
            composite. A partial v4 composite is never displayed or ranked.
          </p>
        </div>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What index-v3.0 measures</h2>
        <p>
          The Index is a weighted arithmetic mean of measured, judge-free axes. Agentic is AppWorld-C task success
          rate. Knowledge is MMLU-Pro. Instruction is IFBench. Tool calling is tc_json_v1 structural tool selection
          and argument construction. Coding is BigCodeBench-Hard Instruct execution pass rate. Math combines
          OlymMATH-Hard and AMO. Season-1 headline weights were 40% Agentic, 15% Knowledge, 15% Instruction-Following,
          10% Tool calling, 15% Coding, and 5% Math.
        </p>
        <p>
          The static ranked Index removes Agentic and reweights the remaining five axes: 25% Knowledge,
          25% Instruction-Following, 20% Tool calling, 20% Coding, and 10% Math. Static-Core measures only
          Knowledge, Instruction, Tool calling, and Math; it has no sandbox, no Agentic, and no executable Coding, so it is
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
          <span className="text-bench-text">Agentic headroom is deliberate.</span>{" "}Low agentic scores on today&apos;s
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
          Rows whose agentic phase shows an elevated infrastructure timeout rate (over 5 percent) do not rank until
          re-run on hardware that clears it.
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
          Every publishable bundle includes Coding results produced on the submitter&apos;s machine in the pinned,
          network-isolated local-bench sandbox. Coding and Agentic evidence travel with the bundle; the publication
          service validates the complete projection and does not re-run model-generated code.
        </p>
        <p>
          The Coding axis reports pass rate over the 141 sandbox-scoreable BigCodeBench-Hard items; seven
          network/data-dependent upstream items are excluded as unscoreable under mandatory network isolation. lcb, the
          old LiveCodeBench output-prediction proxy, is legacy diagnostic data and is never pooled into index-v3.0.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What publication means</h2>
        <p>
          Community-reported results publish immediately after the complete six-axis contract, suite pins, schema,
          size limits, and duplicate-retry checks pass. The site preserves the submitted identity, protocol, scores,
          and evidence bundle, computes the common composite, and suppresses rows when problems are demonstrated.
          Results are not independently reproduced by default.
        </p>
        <ul className="list-disc space-y-3 pl-5">
          <li>
            <span className="text-bench-text">One provenance badge.</span>{" "}Only rows whose server-owned origin is
            <span className="font-mono"> project_anchor</span> receive the <span className="font-mono">project run</span>
            {" "}badge. Community reports are the unmarked default.
          </li>
          <li>
            <span className="text-bench-text">Names are details, not identity proof.</span>{" "}An optional free-text handle
            appears only as &ldquo;submitted as … — unverified&rdquo;. It never replaces the model or artifact identity.
          </li>
          <li>
            <span className="text-bench-text">One ranking rule.</span> Every complete published row enters the same
            score order. Incomplete legacy records remain available on family pages as history, never as partial board rows.
          </li>
          <li>
            <span className="text-bench-text">Moderation happens after publication.</span> Evidence-backed problems
            can trigger a consistency check or independent re-run, and the maintainer suppresses a row when the evidence
            warrants it. There is no pending truth judgment or promotion tier.
          </li>
        </ul>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Evidence and reproduction</h2>
        <p>
          Each row keeps its structured model artifact identity, immutable bundle hash, protocol and suite identity,
          axis scores, sample counts, confidence intervals, and downloadable evidence. Anyone can use
          <span className="font-mono"> localbench verify</span> for a consistency check or independently re-run the
          public suite; those are different claims, and the site does not call a consistency check a reproduction.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Threat posture, honestly</h2>
        <p>
          An OpenAI-compatible endpoint can be a cheat proxy: it can look up public answers and fabricate
          plausible transcripts, and no server-side check proves which model — or whose hardware — actually
          produced a bundle. Public evidence and family-page outliers make scrutiny practical, but they do not prove
          model identity or honest execution. The policy is publish complete reports, audit consequential leaders or
          evidence-backed disputes, and suppress demonstrated problems.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Determinism and reproducibility</h2>
        <p>{LAUNCH_FREEZE.determinismWording}</p>
        <p>
          Every displayed score carries a bootstrap confidence interval. Repeatability, paired quant-delta, and
          generalization are kept separate. Per-axis confidence intervals are part of the score display; coding deltas
          under about 8-10 raw points are not ranking claims unless rank containment and intervals support that read.
          Incomplete historical runs remain diagnostics. The current board admits only complete protocol runs.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Serving engine lanes</h2>
        <p>
          Rows identify the serving engine as well as the model format. Community-submitted llama.cpp runs use a pinned
          GGUF artifact. Safetensors/NVFP4 rows use the project-operated vLLM path in WSL2; that runtime is not yet a
          supported community provisioning path and remains so until the appliance ships.
        </p>
        <p>
          A vLLM receipt pins the Hugging Face repository and full 40-character revision, the snapshot Merkle identity
          and per-file hashes, the server-reported engine version and dependency identity, a two-start determinism
          canary with engine-log evidence, and the declared model, KV-cache, and Mamba SSM-state dtypes. Its reproduction
          form is <span className="font-mono text-bench-text">localbench bench --runtime vllm --model-ref hf://&lt;repo&gt;@&lt;revision&gt;</span>.
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
            <dd className="mt-1 text-sm text-bench-text">{publicProtocolLabel(INDEX_VERSION_V4)} / scorecard-v6</dd>
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
          Domain weights are explicit editorial choices tied to named releases: {publicProtocolLabel(INDEX_VERSION_V4)}{" "}
          (scorecard-v6) for the
          current five-axis Index (Agentic raised to 25% from index-v4.0&apos;s 20%, the other four axes scaled by
          15/16), index-v4.0 (scorecard-v5) for the initial season-2 scale, index-v3.0 for the season-1 six-axis
          Index, static-suite-v2 for the ranked no-agentic Index, and static-core diagnostic for the unranked
          no-sandbox profile. Weights live in the scorer axis registry and are hashed into the scorecard, so history
          cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
