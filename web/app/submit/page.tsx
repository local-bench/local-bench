import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import {
  CLI_PREREQUISITES,
  CURRENT_RANKED_SUITE,
  formatCanonicalBenchCommand,
  LOCALBENCH_INSTALL_COMMAND,
  LOCALBENCH_TESTED_VERSION,
} from "@/lib/cli-onboarding";

export default function SubmitPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Model families", href: "/families" }, { label: "Submit a run" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">community submissions</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submit a run</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          Run the frozen suite against your own local model, then submit the signed result bundle with
          one command. No account, no email, no signup — your submission is identified by an Ed25519
          key generated on your machine. Complete reports publish after automated contract checks.
        </p>
      </header>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Your key is your identity</h2>
        <p>
          There is no signup. The first time you submit, the CLI generates an Ed25519 keypair at{" "}
          <code className="font-mono text-bench-text">~/.localbench/submitter_ed25519.pem</code> and
          prints the public key. That key is your leaderboard identity: every bundle you submit is
          signed with it. Back the file up — there is no
          password reset, and a new key is a new identity.
        </p>
        <p>
          You can optionally attach a display name (2–40 characters, ASCII letters and digits only —
          no accents or parentheses — starting and ending with a letter or digit; spaces,{" "}
          <code className="font-mono text-bench-text">.</code>,{" "}
          <code className="font-mono text-bench-text">_</code>,{" "}
          <code className="font-mono text-bench-text">&apos;</code>, and{" "}
          <code className="font-mono text-bench-text">-</code> allowed in between — no URLs). Accepted
          rows show it only in details as “submitted as X — unverified”. Display names are plain-text
          credit, not unique handles or the primary board identity.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">The loop</h2>

        <h3 className="text-base font-semibold text-bench-text">1. Install the CLI</h3>
        <p>Tested with local-bench-ai {LOCALBENCH_TESTED_VERSION}. Prerequisites:</p>
        <ul className="list-disc space-y-1 pl-5">
          {CLI_PREREQUISITES.map((prerequisite) => <li key={prerequisite}>{prerequisite}</li>)}
        </ul>
        <p>
          For the one-command path, put{" "}
          <code className="font-mono text-bench-text">llama-server</code> on PATH from{" "}
          <a
            href="https://github.com/ggerganov/llama.cpp/releases"
            className="text-bench-accent hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            llama.cpp releases
          </a>{" "}
          or pass <code className="font-mono text-bench-text">--llama-server-path</code>.
        </p>
        <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
          {LOCALBENCH_INSTALL_COMMAND}
        </pre>
        <p className="text-sm text-bench-warn">
          The package name is <code className="font-mono text-bench-text">local-bench-ai</code> — plain{" "}
          <code className="font-mono text-bench-text">pip install localbench</code> installs an
          unrelated third-party package. Use the exact command above.
        </p>
        <p className="text-sm">
          Installs the <code className="font-mono text-bench-text">localbench</code> command. Working
          from source instead? Clone{" "}
          <code className="font-mono text-bench-text">github.com/local-bench/local-bench</code> and{" "}
          <code className="font-mono text-bench-text">pip install -e cli</code>.
        </p>

        <h3 className="text-base font-semibold text-bench-text">2. Bench the catalog model</h3>
        <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
          {formatCanonicalBenchCommand("qwen3-8b", "Q4_K_M")}
        </pre>
        <p className="text-sm">
          <code className="font-mono text-bench-text">--allow-untrusted-code</code> runs the benchmark&apos;s coding tasks in the pinned sandbox — see{" "}
          <Link href="/methodology#coding-trust" className="text-bench-accent hover:underline">Methodology</Link>.
        </p>
        <p>
          <code className="font-mono text-bench-text">bench</code> resolves the catalog slug and quant,
          checks publishability before downloading, verifies pinned GGUF hashes, starts llama-server
          with the deterministic config, shows progress and ETA, prints the scorecard, and offers
          submission at the end. The submission prompt defaults to No; complete submissions publish
          after the automated contract checks.
        </p>
        <p className="text-sm">
          Non-interactive shells must be explicit: add{" "}
          <code className="font-mono text-bench-text">--yes</code>,{" "}
          <code className="font-mono text-bench-text">--accept-suite-terms</code>, and either{" "}
          <code className="font-mono text-bench-text">--no-submit</code> or{" "}
          <code className="font-mono text-bench-text">--submit</code>.
        </p>

        <details className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <summary className="cursor-pointer text-base font-semibold text-bench-text">
            Advanced route: bring your own server
          </summary>
          <div className="mt-4 space-y-4">
            <p>
              Use this manual route for vLLM, LM Studio, custom llama.cpp rigs, or any server you
              already launched yourself. It is the publishable fallback when the catalog quant lacks
              artifact pins or a pasted repo run is local-only.
            </p>
            <h3 className="text-base font-semibold text-bench-text">A. Fetch the frozen suite</h3>
            <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
              {`localbench fetch-suite \\
  --site https://local-bench.ai \\
  --suite ${CURRENT_RANKED_SUITE} \\
  --accept-suite-terms`}
            </pre>
            <p>
              <code className="font-mono text-bench-text">{CURRENT_RANKED_SUITE}</code> is the current ranked suite: it
              measures six axes; five are weighted in the Index, and tool-calling is reported as an unweighted diagnostic.
            </p>
            <p>
              This downloads the sha256-pinned item sets, verifies them against the release manifest,
              and caches them locally.{" "}
              <code className="font-mono text-bench-text">--accept-suite-terms</code> acknowledges the
              upstream benchmark licenses listed under{" "}
              <Link href="/methodology#licenses" className="text-bench-accent hover:underline">
                benchmark sources &amp; licenses
              </Link>
              .
            </p>

            <h3 className="text-base font-semibold text-bench-text">B. Cache your model&apos;s tokenizer</h3>
            <p>
              Ranked runs pass <code className="font-mono text-bench-text">--hf-model-id</code> so the
              harness can introspect your model&apos;s chat template. That introspection is deliberately
              offline (the run never phones home mid-benchmark), so the tokenizer files must already be
              in your Hugging Face cache before you start:
            </p>
            <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
              {`localbench cache-tokenizer <the-model's-HF-repo>`}
            </pre>
            <p className="text-sm">
              Downloads exactly what introspection needs, verifies the tokenizer loads offline, and
              prints the resolved revision and chat-template hash. Use the tokenizer and
              tokenizer_config files from that Hugging Face snapshot in step 4. Use the original
              model&apos;s repo (the transformers-format one), not the GGUF repo. Gated repos (for example{" "}
              <code className="font-mono text-bench-text">google/gemma-*</code>) additionally need a
              one-time <code className="font-mono text-bench-text">hf auth login</code> after accepting
              the license on huggingface.co — or use an ungated mirror such as the{" "}
              <code className="font-mono text-bench-text">unsloth/</code> upload of the same model. No
              exact non-GGUF repo exists for your model? Skip this step and pass{" "}
              <code className="font-mono text-bench-text">--gguf-repo-only</code> instead of{" "}
              <code className="font-mono text-bench-text">--hf-model-id</code> in step 4 — the run is
              then labeled basic identity (tokenizer/template digests null).
            </p>

            <h3 className="text-base font-semibold text-bench-text">C. Run against your server</h3>
            <p>
              Already serving the model yourself (LM Studio, ollama, vLLM, anything OpenAI-compatible)?
              Use <code className="font-mono text-bench-text">run</code> instead:
            </p>
            <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
              {`localbench run \\
  --endpoint http://localhost:8080/v1 \\
  --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M \\
  --hf-model-id Qwen/Qwen3-8B \\
  --lane bounded-final-v2 \\
  --profile auto \\
  --tier standard \\
  --publishable \\
  --sampler-temperature 0 \\
  --sampler-top-k 1 \\
  --sampler-seed 1234 \\
  --determinism-policy gpu-greedy-single-slot-v1 \\
  --model-file <path-to-qwen3-8b-q4-k-m.gguf> \\
  --model-family Qwen3 \\
  --quant-label Q4_K_M \\
  --model-format gguf \\
  --tokenizer-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer.json \\
  --chat-template-file ~/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/<revision>/tokenizer_config.json \\
  --runtime-name llama.cpp \\
  --runtime-version <llama.cpp-build> \\
  --kv-cache-quant f16 \\
  --ctx-len-configured 32768 \\
  --parallel-slots 1 \\
  --out runs/qwen3-8b-q4-k-m.json`}
            </pre>
            <p>
              The ranked board uses the bounded-final protocol: every model gets the same
              generated-token budget per item, and <code className="font-mono text-bench-text">--profile auto</code>{" "}
              reads your model&apos;s own chat template to decide whether it thinks (bounded) or answers directly.
              A run must pin its sampler settings to be publishable (
              <code className="font-mono text-bench-text">--publishable</code>{" "}
              requires temperature 0, top-k 1, and a seed); the CLI warns up
              front — before any GPU time is spent — if your flags make the run unpublishable. Keep the{" "}
              <code className="font-mono text-bench-text">.json</code> extension on{" "}
              <code className="font-mono text-bench-text">--out</code> — the campaign directory is derived
              from it. Want these pre-filled for your VRAM and model? The{" "}
              <Link href="/" className="text-bench-accent hover:underline">
                recipe builder on the home page
              </Link>{" "}
              generates this exact sequence.
            </p>
            <p>
              <code className="font-mono text-bench-text">{CURRENT_RANKED_SUITE}</code> is the current ranked suite.{" "}
              <code className="font-mono text-bench-text">suite-v1-static-exec-5axis-v1</code> and{" "}
              <code className="font-mono text-bench-text">suite-v1-static-core-diag-v1</code> are static or diagnostic suites;
              they preserve evidence but do not produce rankable rows.
            </p>

            <h3 className="text-base font-semibold text-bench-text">D. Submit manually</h3>
            <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
              {`localbench submit run --run runs/qwen3-8b-q4-k-m.json`}
            </pre>
            <p>
              One command takes a finished run all the way in: it packs the signed bundle, requests a
              submission ticket (signing a proof-of-possession challenge with your key), uploads the
              bundle, completes the submission, and prints your submission id and status. The suite is
              auto-resolved from your <code className="font-mono text-bench-text">fetch-suite</code> cache;
              <code className="font-mono text-bench-text"> --suite-dir</code> overrides it.{" "}
              <code className="font-mono text-bench-text">--run</code> accepts the run JSON or its campaign
              directory; add <code className="font-mono text-bench-text">--display-name</code> once to set
              your credit line (remembered in{" "}
              <code className="font-mono text-bench-text">~/.localbench/submit.json</code>).
            </p>
            <p>
              Bundles are content-addressed by sha256, so duplicates are detected: re-running{" "}
              <code className="font-mono text-bench-text">submit run</code> with a bundle that is already
              in tells you its existing submission id instead of creating a new row, and a bundle whose
              payload matches an earlier submission is flagged for the reviewer. If a ticket expires
              mid-flight, a fresh one is minted automatically. The public status page is{" "}
              <code className="font-mono text-bench-text">local-bench.ai/submission?id=&lt;submission_id&gt;</code>.
              You can also check from the CLI:
            </p>
            <pre tabIndex={0} className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent sm:text-sm">
              {`localbench submit status <submission_id> --site https://local-bench.ai`}
            </pre>
          </div>
        </details>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What happens after you submit</h2>
        <p>
          A complete bundle publishes after automated schema, protocol, suite-pin, size, and duplicate-retry checks.
          The service preserves the submitted identity, scores, protocol, and evidence and computes the common
          composite. Publication does not mean the project independently reproduced the run. Demonstrated problems
          can cause a row to be suppressed after publication.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What you can submit</h2>
        <p>Runs with the complete headline profile enter the common ranking. Incomplete legacy profiles remain diagnostic.</p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <span className="text-bench-text">The complete headline profile</span> — every required headline axis,
            suite pin, artifact identity, and evidence record is present.
          </li>
          <li>
            <span className="text-bench-text">Legacy complete protocols</span> — preserved on their original
            protocol scale for history and never mixed into the active ranking.
          </li>
          <li>
            <span className="text-bench-text">Static-Core diagnostic</span> —{" "}
            <code className="font-mono text-bench-text">suite-v1-static-core-diag-v1</code>, no Agentic
            and no sandboxed Coding. It is displayed as diagnostic and never ranked.
          </li>
        </ul>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What uploads</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            A signed bundle (64 MiB cap) containing the manifest, item records, the original run JSON,
            prompt/response transcripts, suite hashes, and runtime metadata. The upload goes directly
            to object storage via a short-lived URL; the database stores metadata and status only.
          </p>
        </div>
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What stays local</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            Model weights, API keys, server credentials, and your private signing key — the server
            only ever sees your public key and signatures. Submissions publish immediately, so do
            not submit a run if the transcript contains anything you are unwilling to make public.
          </p>
        </div>
      </section>

      <section className="space-y-3 text-bench-muted">
        <p>
          Public evidence does not prove model identity, hardware identity, or runtime honesty. The board publishes
          complete reports, makes their evidence inspectable, and suppresses demonstrated problems — see the{" "}
          <Link href="/methodology" className="text-bench-accent hover:underline">
            methodology page
          </Link>{" "}
          for what each label does and does not claim.
        </p>
      </section>
    </main>
  );
}
