import Link from "next/link";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";
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
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}):
          Knowledge (MMLU-Pro) and Instruction-Following (IFBench), equal-weight and chance-corrected.
          {` ${LOCAL_INTELLIGENCE_INDEX_PROFILE}`} stays visible beside it. Candidate axes wait for measured
          discrimination before any broader Overall tier exists.
        </p>
      </header>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What the headline Index is — and is not</h2>
        <p>
          The Index is the equal-weighted arithmetic mean of two chance-corrected, judge-free axes —{" "}
          <span className="text-bench-text">Knowledge</span> (MMLU-Pro, 400 items) and{" "}
          <span className="text-bench-text">Instruction-Following</span> (IFBench, 294 items) — rendered on a
          0..100 scale. These are the axes that reproduce anywhere without an LLM judge. We deliberately do{" "}
          <span className="text-bench-text">not</span> call this an &ldquo;AI intelligence&rdquo; score: two axes
          are a narrow, honest slice, not a claim about general capability.
        </p>
        <p>
          A run missing one of the two headline axes normalizes over the axis it has and is flagged{" "}
          <span className="text-bench-text">partial</span> — not comparable to a full headline run. The weaker of
          the two axes is shown beside the composite, because an arithmetic mean can hide a single-axis collapse.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Candidate axes carry 0% weight</h2>
        <p>
          <span className="text-bench-text">Math</span>, <span className="text-bench-text">Coding-exec</span>, and{" "}
          <span className="text-bench-text">Agentic</span> are <span className="text-bench-text">candidate axes</span>.
          They are measured and displayed where data exists, but they sit at{" "}
          <span className="text-bench-text">0% Index weight</span> and never enter the headline. A candidate is
          promoted only when it demonstrably separates local models on our own harness (a pre-registered
          discrimination gate with confidence-bound spread), at which point it earns a spread-proportional weight.
          Until then, a full &ldquo;Overall&rdquo; intelligence number does not exist here — by design, rather than
          by averaging in axes that do not discriminate.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">One lane: capped-thinking</h2>
        <p>
          Reasoning lanes are never mixed. The ranked board is the{" "}
          <span className="text-bench-text">capped-thinking</span> lane: reasoning is on, with a graceful 8192-token
          reasoning budget and a 16384-token answer ceiling. Answer-only and uncapped-API runs are secondary views
          that compare only within their own lane and never merge into the headline. Tokens-to-answer is captured as
          a first-class dimension, so a model that buys accuracy with far more compute is visible as such, not hidden.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Determinism and reproducibility</h2>
        <p>{LAUNCH_FREEZE.determinismWording}</p>
        <p>
          Every displayed score carries a bootstrap confidence interval (benchmark items are not i.i.d., so CIs are
          bootstrapped rather than normal-approximated). Three uncertainty questions are kept separate and never
          conflated: <span className="text-bench-text">repeatability</span> (same setup, same items, re-run),{" "}
          <span className="text-bench-text">paired quant-delta</span> (one quant vs another on these exact items),
          and <span className="text-bench-text">generalization</span> (whether the result transfers beyond this item
          set). Quick-tier, fixed-item runs are personal estimates and stay unranked; only Standard-tier runs are
          ranked.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Contamination — what we can and cannot promise</h2>
        <p>
          MMLU-Pro and IFBench are public benchmarks, so we cannot rule out that some items appear in model training
          data. We mitigate, we do not pretend to eliminate: the exact item subsets are frozen and their sha256
          hashes are published (below and in the footer), so the question set cannot drift silently between runs;
          contamination status is shown per run rather than asserted clean; and a private generated-math sentinel
          acts as a contamination canary, since static answer lookup fails when the answers are withheld. Treat small
          deltas between models with caution — a one-to-two-point gap on a few hundred items is inside the noise band,
          not a reliable ranking.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Quant degradation is a drift story, not an accuracy headline</h2>
        <p>
          The honest finding on quantization is that, with reasoning on, accuracy stays roughly flat from Q8 down to
          Q4 and only falls off a cliff at very low bit-widths — while the model spends meaningfully more tokens to
          get there. So the model page reports the quant trade-off as <span className="text-bench-text">VRAM</span>,{" "}
          <span className="text-bench-text">speed</span>, and output-<span className="text-bench-text">drift</span>{" "}
          (KL-divergence and answer-churn versus a full-precision reference), with accuracy as a flat reassurance line
          that surfaces the low-bit cliff where one exists. Drift is labeled as drift, never as a task score, and the
          reference type (BF16/FP16, or a labeled Q8 proxy where full precision will not fit) is always stated.
        </p>
      </section>

      <section className="space-y-3 text-bench-muted">
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
                {set.label} — {set.file}
              </dt>
              <dd className="mt-1 break-all font-mono text-xs text-bench-text">{set.sha256}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm">
          Benchmark item licenses and scorer attribution are listed on the{" "}
          <Link href="/trust" className="text-bench-accent hover:underline">
            trust &amp; licenses
          </Link>{" "}
          page.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Editorial versioning</h2>
        <p>
          Domain weights are explicit editorial choices tied to an index version, and the item sets are tagged by a
          separate suite version — so a scoring change and an item change are always visible as distinct version
          bumps, never silent. Weights live in exactly one place (the scorer&rsquo;s axis registry) and are hashed
          into the scorecard, so history cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
