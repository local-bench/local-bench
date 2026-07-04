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
        <h2 className="text-xl font-semibold text-bench-text">Two composites, one suite</h2>
        <p>
          Not every platform can run the agentic axis — AppWorld executes in a Linux sandbox — so the board
          carries two named composites:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <span className="text-bench-text">index-v2.1</span> (the main index): Agentic 50 / Knowledge 15 /
            Instruction-Following 15 / Tool calling 10 / Coding 10. Requires all five headline axes.
          </li>
          <li>
            <span className="text-bench-text">static-suite-v1</span> (the static composite): Knowledge 30 /
            Instruction-Following 30 / Tool calling 20 / Coding 20. Requires the four static axes and applies
            to rows without agentic results.
          </li>
        </ul>
        <p>
          The two are not score-comparable — agentic is deliberately half the main index, and the static
          composite renormalizes over what was actually measured rather than pretending the gap isn&apos;t there.
          Rows with fewer than the four static axes display per-axis scores and confidence intervals only and
          are not ranked. Both weight sets are explicit editorial choices, versioned and hashed like everything
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
            <span className="text-bench-text">Origin: project anchor vs community.</span> Anchor rows are runs
            the project executed on its own hardware; community rows are everything submitted from outside.
            The server derives this; submitters cannot set it.
          </li>
          <li>
            <span className="text-bench-text">Static axes: always re-scored.</span> For every accepted bundle —
            anchor or community — the four static axes are independently recomputed from the submitted
            transcripts against the frozen, sha256-pinned item sets. A submitted static score never enters the
            board as claimed, so fabricated static scores do not survive.
          </li>
          <li>
            <span className="text-bench-text">Agentic axis: provenance-labeled, not re-scored.</span> Agentic
            verdicts are produced by live task execution and cannot be recomputed from a transcript after the
            fact, so carried verdicts wear a provenance label instead.{" "}
            <span className="text-bench-text">Attested</span> means every carried verdict has a valid Ed25519
            attestation, signed at the moment the sandbox verdict was accepted and checked against the
            project&apos;s pinned attester key — project-run rows carry this. (One historical anchor row, the
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
          transcripts), signed anchor attestations make the project&apos;s own agentic verdicts tamper-evident, and
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
          Domain weights are explicit editorial choices tied to a named composite version — index-v2.1 for the
          full five-axis index, static-suite-v1 for the static composite — and item sets are tagged by a separate
          suite version. Weights live in the scorer axis registry and are hashed into the scorecard, so history
          cannot be silently re-scored under the same label.
        </p>
      </section>
    </main>
  );
}
