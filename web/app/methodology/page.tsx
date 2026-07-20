import { readFileSync } from "node:fs";
import path from "node:path";

import { Breadcrumbs } from "@/components/breadcrumbs";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  SEASON_2_INDEX_PROFILE,
  SEASON_2_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";
import { publicProtocolLabel } from "@/lib/board-adapter";
import { CURRENT_RANKED_SUITE } from "@/lib/cli-onboarding";
import {
  INDEX_VERSION_V4,
  SEASON_2_DIAGNOSTICS,
  TOOL_USE_WEIGHT,
} from "@/lib/scoring-seasons";

type ProtocolView = {
  readonly canonical_sha256: string;
  readonly agentic_protocol: {
    readonly ordered_task_ids_sha256: string;
    readonly seed: number;
    readonly selection_recipe_sha256: string;
    readonly selection_version: string;
    readonly split: string;
    readonly subset_sha256: string;
  };
};

const protocol = JSON.parse(
  readFileSync(path.join(process.cwd(), "..", "protocol", "index-v4.2.json"), "utf-8"),
) as ProtocolView;

type Attribution = {
  readonly name: string;
  readonly owner: string;
  readonly license: string;
  readonly role: string;
};

const HEADLINE_SOURCES: readonly Attribution[] = [
  { name: "AppWorld-C", owner: "AppWorld authors", license: "Apache-2.0", role: "Agentic task-goal completion axis (96-task fixed subset)." },
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
    name: "BigCodeBench-Hard Instruct",
    owner: "BigCodeBench authors",
    license: "Apache-2.0",
    role: "Coding axis generation tasks (141 sandbox-scoreable items) scored by hardened execution.",
  },
  {
    name: "OlymMATH-Hard",
    owner: "OlymMATH authors",
    license: "MIT",
    role: "Math axis hard olympiad-style item set (100 items).",
  },
  {
    name: "AMO",
    owner: "AMO-Bench authors",
    license: "MIT",
    role: "Math axis newly-authored olympiad-style item set (39 items; Math 139 total).",
  },
];

const CANDIDATE_SOURCES: readonly Attribution[] = [
  {
    name: "TC-JSON v1",
    owner: "local-bench + Gorilla LLM / UC Berkeley",
    license: "Apache-2.0",
    role: "Unweighted call-formatting diagnostic and structural JSON scorer.",
  },
  {
    name: "LiveCodeBench / RULER / BFCL expansions",
    owner: "LiveCodeBench authors / NVIDIA / Gorilla LLM and UC Berkeley",
    license: "various open licenses",
    role: "Legacy or candidate diagnostic modules credited in their suite manifests.",
  },
];

const V42_RESCORE_ROWS = [
  { model: "Gemma 4 31B IT", before: 53.12, after: 51.69 },
  { model: "Qwen3.6 27B", before: 44.35, after: 43.22 },
  { model: "Qwopus 3.6 27B v2 MTP", before: 43.27, after: 42.08 },
  { model: "Qwen3.6 35B A3B", before: 42.12, after: 41.01 },
  { model: "Gemma 4 12B IT", before: 42.03, after: 40.29 },
] as const;

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
      <Breadcrumbs items={[{ label: "Model families", href: "/families" }, { label: "Methodology" }]} />
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
            Protocol v4.2 · {publicProtocolLabel(INDEX_VERSION_V4)}
          </p>
          <h2 className="mt-1 text-xl font-semibold text-bench-text">One scoring protocol for every ranked row</h2>
        </div>
        <p>
          Community and project rows must be scored identically. The previous Agentic axis blended AppWorld with a
          benchmark that community runs could not execute, so the two populations were ranked on unequal compositions.
          Protocol v4.2 corrects that comparability defect by making Agentic AppWorld-only everywhere. The structural
          key remains <span className="font-mono">tool_use</span>, and its {Math.round(TOOL_USE_WEIGHT * 100)}% headline
          weight does not change.
        </p>
        <p>
          <span className="font-mono">{CURRENT_RANKED_SUITE}</span> is the current ranked suite. The suite measures six axes;
          five are weighted in the Index, tool-calling is reported as an unweighted diagnostic.
        </p>
        <p>
          Agentic measures AppWorld task-goal completion under the published runner: a fixed 96-task subset from{" "}
          <span className="font-mono">{protocol.agentic_protocol.split}</span>, selected with seeded stratified recipe{" "}
          <span className="font-mono">{protocol.agentic_protocol.selection_version}</span> and seed{" "}
          <span className="font-mono">{protocol.agentic_protocol.seed}</span>. The subset is identical for every row.
          The published protocol exposes counts and hashes, never upstream task contents.
        </p>
        <dl className="grid gap-2 rounded border border-bench-line bg-bench-bg/45 p-3 text-xs sm:grid-cols-2">
          <div><dt className="text-bench-muted">Subset sha256</dt><dd className="break-all font-mono text-bench-text">{protocol.agentic_protocol.subset_sha256}</dd></div>
          <div><dt className="text-bench-muted">Ordered task-ID sha256</dt><dd className="break-all font-mono text-bench-text">{protocol.agentic_protocol.ordered_task_ids_sha256}</dd></div>
          <div><dt className="text-bench-muted">Selection recipe sha256</dt><dd className="break-all font-mono text-bench-text">{protocol.agentic_protocol.selection_recipe_sha256}</dd></div>
          <div><dt className="text-bench-muted">Protocol manifest sha256</dt><dd className="break-all font-mono text-bench-text">{protocol.canonical_sha256}</dd></div>
        </dl>

        <div className="space-y-2 border-t border-bench-line pt-4">
          <h3 className="text-lg font-semibold text-bench-text">Correction impact</h3>
          <p>
            Raw inference outputs are unchanged; no model was re-run. Existing item verdicts were re-scored under the
            equal v4.2 protocol. The rank order is unchanged.
          </p>
          <p className="font-mono text-[10px] uppercase tracking-wide text-bench-accent sm:hidden">
            Swipe horizontally for v4.1 and v4.2 scores &rarr;
          </p>
          <div className="overflow-x-auto rounded border border-bench-line">
            <table className="w-full min-w-[520px] border-collapse text-sm">
              <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wide text-bench-text/85">
                <tr><th className="px-3 py-2">Model</th><th className="px-3 py-2">v4.1</th><th className="px-3 py-2">v4.2</th></tr>
              </thead>
              <tbody>
                {V42_RESCORE_ROWS.map((row) => (
                  <tr key={row.model} className="border-t border-bench-line/70">
                    <td className="px-3 py-2 font-semibold text-bench-text">{row.model}</td>
                    <td className="px-3 py-2 font-mono">{row.before.toFixed(2)}</td>
                    <td className="px-3 py-2 font-mono text-bench-accent">{row.after.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm">
            Archived v4.1 snapshots: <a className="text-bench-accent underline" href="/data/archive/index-v4.1.json">board JSON</a>{" "}
            and <a className="text-bench-accent underline" href="/data/archive/agentic-v4.1.json">Agentic JSON</a>.
          </p>
        </div>

        <div className="space-y-2 border-t border-bench-line pt-4">
          <h3 className="text-lg font-semibold text-bench-text">Unweighted diagnostics</h3>
          <p>
            {SEASON_2_DIAGNOSTICS.map((diagnostic) => diagnostic.label).join(", ")} are displayed when measured and shown
            as not measured when absent. They are never weighted, never zero-filled, and never used for ranking. BFCL v3
            multi-turn base is retained as a frozen, version-pinned diagnostic.
          </p>
        </div>

        <div className="space-y-2 border-t border-bench-line pt-4">
          <h3 className="text-lg font-semibold text-bench-text">Season 1 → 2 bridge</h3>
          <p>
            Index-v3.0 and index-v4.x composites are different editorial scales and are never directly compared.
            Index-v4.0, index-v4.1, and {publicProtocolLabel(INDEX_VERSION_V4)} are also distinct protocol snapshots.
            Lineage deltas and ordinary compare views require matching index versions. The versioned season bridge is
            the only sanctioned pairing: for an artifact measured completely in both seasons, it presents the frozen
            v3 composite beside the full v4 composite without treating their numerical gap as a performance delta.
          </p>
          <p>
            An anchor without complete season-2 coverage keeps its season-1 label and composite. A partial v4
            composite is never displayed or ranked.
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

      <section id="coding-trust" className="space-y-4 text-bench-muted">
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
          Community-reported results publish immediately after the complete headline profile, suite pins, schema,
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

      <section id="serving-engine-lanes" className="space-y-4 text-bench-muted">
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
          (scorecard-v6) is the current five-axis Index with AppWorld-only Agentic. Index-v4.1 retains the same
          headline weights but its unequal Agentic composition is archived; index-v4.0 is the initial season-2 scale,
          and index-v3.0 is the season-1 six-axis Index. Static-suite-v2 and static-core remain non-rankable diagnostics;
          neither can produce an active board row. Weights and membership live in the versioned protocol
          manifest and scorer registry, so history cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
