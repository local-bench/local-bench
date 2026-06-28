import { Breadcrumbs } from "@/components/breadcrumbs";

export default function SubmitPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Submit a run" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">community submissions</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submit a run</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          Run the frozen suite locally against any OpenAI-compatible endpoint, then upload a signed
          bundle for deterministic re-scoring and maintainer review.
        </p>
      </header>

      <pre aria-label="localbench online submission commands" className="whitespace-pre-wrap break-words rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-xs text-bench-text sm:text-sm">
        {`localbench fetch-suite \
  --source-url https://local-bench.ai/api/suites/core-text-v1/manifest \
  --accept-suite-terms

localbench run \
  --endpoint http://localhost:8080/v1 \
  --model your-model-name \
  --lane capped-thinking \
  --tier standard \
  --out my-run.json

localbench submit keygen --out localbench-ed25519.pem
localbench submit ticket \
  --site https://local-bench.ai \
  --signing-key localbench-ed25519.pem \
  --out ticket.json
localbench submit pack \
  --run my-run.json \
  --suite-dir <cached-suite-dir> \
  --model-name your-model-name \
  --signing-key localbench-ed25519.pem \
  --ticket ticket.json \
  --out my-run.lbsub.zip
localbench submit upload --ticket ticket.json --bundle my-run.lbsub.zip
localbench submit status <submission_id> --site https://local-bench.ai`}
      </pre>
      <p className="-mt-3 text-sm leading-6 text-bench-muted">
        <code className="font-mono text-bench-text">--lane capped-thinking</code> is the headline reasoning-on
        lane. Accepted submissions are not published immediately; the public board is regenerated only
        after deterministic checks, local maintainer review, and an explicit deploy.
      </p>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What uploads</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            A signed bundle containing the manifest, item records, original run JSON, prompt/response
            transcript data, suite hashes, and runtime metadata. The upload goes directly to R2 using
            a short-lived URL; D1 stores metadata and status only.
          </p>
        </div>
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What stays local</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            Model weights, API keys, local server credentials, and any private machine access. Do not
            submit a run if the transcript contains data you are unwilling to share with the maintainer
            review process.
          </p>
        </div>
      </section>

      <section className="space-y-3 text-bench-muted">
        <p>
          Uploaded runs are labelled community re-scored after the server-side verifier recomputes scores
          from the signed bundle. That label does not prove model identity, hardware identity, or runtime
          honesty.
        </p>
      </section>
    </main>
  );
}
