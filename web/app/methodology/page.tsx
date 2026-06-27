import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
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
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Methodology" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
          {index.suite_version} | {index.index_version} methodology
        </p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">How local-bench scores runs</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          The sortable number is the {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}):
          50% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, and 10% Coding.
          {` ${LOCAL_INTELLIGENCE_INDEX_PROFILE}`} stays visible beside it.
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
          A ranked row requires all headline axes in the current scope. Partial rows still display their measured
          axes and confidence intervals, but they are not rank-comparable until the missing headline modules land.
          Math, Long-Context, and BigCodeBench-Hard coding-exec remain diagnostic or opt-in expansion modules.
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
                {set.label} | {set.file}
              </dt>
              <dd className="mt-1 break-all font-mono text-xs text-bench-text">{set.sha256}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm">
          Benchmark item licenses and scorer attribution are listed on the{" "}
          <Link href="/trust" className="text-bench-accent hover:underline">
            trust &amp; licenses page
          </Link>
          .
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Editorial versioning</h2>
        <p>
          Domain weights are explicit editorial choices tied to an index version, and item sets are tagged by a
          separate suite version. Weights live in the scorer axis registry and are hashed into the scorecard, so
          history cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
