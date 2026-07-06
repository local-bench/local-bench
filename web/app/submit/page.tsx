import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";

export default function SubmitPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Submit a run" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">community submissions</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submit a run</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          Run the frozen suite against your own local model, then submit the signed result bundle with
          one command. No account, no email, no signup — your submission is identified by an Ed25519
          key generated on your machine, and nothing appears on the board until a maintainer reviews
          and accepts it.
        </p>
      </header>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">Your key is your identity</h2>
        <p>
          There is no signup. The first time you submit, the CLI generates an Ed25519 keypair at{" "}
          <code className="font-mono text-bench-text">~/.localbench/submitter_ed25519.pem</code> and
          prints the public key. That key is your leaderboard identity: every bundle you submit is
          signed with it, and accepted rows are credited to it. Back the file up — there is no
          password reset, and a new key is a new identity.
        </p>
        <p>
          You can optionally attach a display name (2–40 characters, ASCII letters and digits only —
          no accents or parentheses — starting and ending with a letter or digit; spaces,{" "}
          <code className="font-mono text-bench-text">.</code>,{" "}
          <code className="font-mono text-bench-text">_</code>,{" "}
          <code className="font-mono text-bench-text">&apos;</code>, and{" "}
          <code className="font-mono text-bench-text">-</code> allowed in between — no URLs). Accepted
          rows carry it as your credit line on the board. Display names are plain-text credit, not
          unique handles.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">The loop</h2>

        <h3 className="text-base font-semibold text-bench-text">1. Install the CLI</h3>
        <p>Python 3.11+ required:</p>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`pip install "local-bench-ai[hf]"`}
        </pre>
        <p className="text-sm">
          Installs the <code className="font-mono text-bench-text">localbench</code> command. Working
          from source instead? Clone{" "}
          <code className="font-mono text-bench-text">github.com/local-bench/local-bench</code> and{" "}
          <code className="font-mono text-bench-text">pip install -e cli</code>.
        </p>

        <h3 className="text-base font-semibold text-bench-text">2. Fetch the frozen suite</h3>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`localbench fetch-suite \\
  --site https://local-bench.ai \\
  --suite suite-v1-full-exec-6axis-v1 \\
  --accept-suite-terms`}
        </pre>
        <p>
          This downloads the sha256-pinned item sets, verifies them against the release manifest, and
          caches them locally.{" "}
          <code className="font-mono text-bench-text">--accept-suite-terms</code> acknowledges the
          upstream benchmark licenses listed under{" "}
          <Link href="/methodology#licenses" className="text-bench-accent hover:underline">
            benchmark sources &amp; licenses
          </Link>{" "}
          on the methodology page.
        </p>

        <h3 className="text-base font-semibold text-bench-text">3. Cache your model&apos;s tokenizer</h3>
        <p>
          Ranked runs pass <code className="font-mono text-bench-text">--hf-model-id</code> so the
          harness can introspect your model&apos;s chat template. That introspection is deliberately
          offline (the run never phones home mid-benchmark), so the tokenizer files must already be
          in your Hugging Face cache before you start:
        </p>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`hf download <the-model's-HF-repo> --include "*.json" --include "*.model" --include "*.jinja"`}
        </pre>
        <p className="text-sm">
          The <code className="font-mono text-bench-text">hf</code> command ships with the{" "}
          <code className="font-mono text-bench-text">[hf]</code> install above. Use the original
          model&apos;s repo (the transformers-format one), not the GGUF repo. Gated repos (for
          example <code className="font-mono text-bench-text">google/gemma-*</code>) additionally
          need a one-time <code className="font-mono text-bench-text">hf auth login</code> after
          accepting the license on huggingface.co — or use an ungated mirror such as the{" "}
          <code className="font-mono text-bench-text">unsloth/</code> upload of the same model. If
          this step is skipped, the run stops in its first seconds with{" "}
          <code className="font-mono text-bench-text">could not load tokenizer … from the offline HF cache</code>.
        </p>

        <h3 className="text-base font-semibold text-bench-text">4. Run the benchmark</h3>
        <p>
          The strongest-provenance path is <code className="font-mono text-bench-text">bench</code>:
          the CLI launches the llama.cpp server itself with pinned serving flags.
        </p>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`localbench bench \\
  --runtime llama.cpp \\
  --model-file <model.gguf> \\
  --model-id <model-slug> \\
  --hf-model-id <the-model's-HF-repo> \\
  --lane bounded-final-v2 \\
  --profile auto \\
  --ctx 32768 \\
  --seed 1234 \\
  --out runs/my-bench`}
        </pre>
        <p>
          Already serving the model yourself (LM Studio, ollama, vLLM, anything OpenAI-compatible)?
          Use <code className="font-mono text-bench-text">run</code> instead:
        </p>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`localbench run \\
  --endpoint http://localhost:8080/v1 \\
  --model <name-your-server-reports> \\
  --hf-model-id <the-model's-HF-repo> \\
  --lane bounded-final-v2 \\
  --profile auto \\
  --tier standard \\
  --publishable \\
  --sampler-seed 1234 \\
  --out runs/my-run.json`}
        </pre>
        <p>
          The ranked board is the bounded-final lane at standard tier: every model gets the same
          generated-token budget per item, and <code className="font-mono text-bench-text">--profile auto</code>{" "}
          reads your model&apos;s own chat template to decide whether it thinks (bounded) or answers directly.
          A run must pin its sampler settings to be publishable (
          <code className="font-mono text-bench-text">--publishable</code>{" "}
          requires <code className="font-mono text-bench-text">--sampler-seed</code>); the CLI warns up
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
          The full ranked release is <code className="font-mono text-bench-text">suite-v1-full-exec-6axis-v1</code>.
          Static-only submitters can use{" "}
          <code className="font-mono text-bench-text">suite-v1-static-exec-5axis-v1</code> and need no Docker:
          coding artifacts are packed by the CLI and the ranked coding score is produced later by project
          re-execution. <code className="font-mono text-bench-text">suite-v1-static-core-diag-v1</code> is
          unranked diagnostic only.
        </p>

        <h3 className="text-base font-semibold text-bench-text">5. Submit</h3>
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`localbench submit run --run runs/my-run.json`}
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
        <pre className="whitespace-pre overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
          {`localbench submit status <submission_id> --site https://local-bench.ai`}
        </pre>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What happens after you submit</h2>
        <p>
          Nothing auto-publishes. Every submission lands as pending; the maintainer reviews it and must
          explicitly accept it before it can appear on the board. As part of review, transcript-scored
          axes are re-scored server-side from the transcripts in your bundle, and Coding ranks only after
          project re-execution of the submitted artifacts. The score you claim is never the score that
          publishes. Agentic (AppWorld) results are carried as you submitted them and labeled{" "}
          <span className="text-bench-text">self-reported</span> on the board; they count in the
          composite but are not independently verified. The public board is regenerated only after
          these checks, maintainer review, and an explicit deploy.
        </p>
      </section>

      <section className="space-y-4 text-bench-muted">
        <h2 className="text-xl font-semibold text-bench-text">What you can submit</h2>
        <p>All current release profiles are accepted, with rankability determined by the release identity.</p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <span className="text-bench-text">Full 6-axis ranked</span> —{" "}
            <code className="font-mono text-bench-text">suite-v1-full-exec-6axis-v1</code>, ranked on
            index-v3.0: Agentic 40 / Knowledge 15 / Instruction-Following 15 / Tool calling 10 /
            Coding 15 / Math 5.
          </li>
          <li>
            <span className="text-bench-text">Static 5-axis ranked</span> —{" "}
            <code className="font-mono text-bench-text">suite-v1-static-exec-5axis-v1</code>, no Agentic,
            verified Coding, and no submitter Docker requirement. It ranks only against static rows:
            Knowledge 25 / Instruction-Following 25 / Tool calling 20 / Coding 20 / Math 10.
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
            only ever sees your public key and signatures. Do not submit a run if the transcript
            contains anything you are unwilling to share with maintainer review.
          </p>
        </div>
      </section>

      <section className="space-y-3 text-bench-muted">
        <p>
          Labels mean exactly what they say. Re-scored means we recomputed transcript-scored axes from
          your transcripts; re-executed means Coding was run again by the project; self-reported means
          we carried your agentic verdicts as submitted. None of it proves model identity, hardware identity,
          or runtime honesty — see the{" "}
          <Link href="/methodology" className="text-bench-accent hover:underline">
            methodology page
          </Link>{" "}
          for what each label does and does not claim.
        </p>
      </section>
    </main>
  );
}
