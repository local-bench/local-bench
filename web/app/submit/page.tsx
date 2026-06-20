import { Breadcrumbs } from "@/components/breadcrumbs";

export default function SubmitPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Submit a run" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs uppercase text-bench-accent">community submissions</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submit a run</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          One command points the frozen suite at any OpenAI-compatible endpoint (Ollama / vLLM / LM Studio /
          llama.cpp); results are server-scored and placed on the boards.
        </p>
      </header>

      <pre className="overflow-x-auto rounded-md border border-bench-line bg-bench-panel-2 p-4 font-mono text-sm text-bench-text">
        {`localbench run \\
  --endpoint http://localhost:11434/v1 \\
  --model your-model-name \\
  --lane capped-thinking \\
  --tier standard \\
  --out my-run.json`}
      </pre>
      <p className="-mt-3 text-sm leading-6 text-bench-muted">
        <code className="font-mono text-bench-text">--lane capped-thinking</code> is the headline reasoning-on
        lane; ranks only compare within a lane, so keep it to land on the ranked board.
      </p>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What uploads</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            The result JSON: per-axis scores + bootstrap CIs, item-set hashes (provenance), and
            hardware/runtime/quant metadata (the manifest summary). No raw prompts or model outputs.
          </p>
        </div>
        <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-lg font-semibold text-bench-text">What stays local</h2>
          <p className="mt-3 leading-7 text-bench-muted">
            Your model weights, the raw prompts and generated responses, and any API keys (read from the env var
            named by <code className="font-mono text-bench-text">--api-key-env</code>, never written to the result).
          </p>
        </div>
      </section>

      <section className="space-y-3 text-bench-muted">
        <p>
          Quick tier is an unranked personal estimate; Standard tier is the ranked board. Independent re-runs of the
          same setup earn a Replicated badge.
        </p>
        <p className="text-sm text-bench-muted/80">This page is a stub; the hosted upload endpoint lands with Track 2.</p>
      </section>
    </main>
  );
}
