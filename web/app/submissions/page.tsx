import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { SubmissionsLifecycle } from "@/components/submissions-lifecycle";

export default function SubmissionsPage() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Model families", href: "/families" }, { label: "Submissions" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">public pipeline</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submission lifecycle</h1>
        <p className="mt-3 max-w-3xl leading-7 text-bench-muted">
          Follow every public submission from receipt through validation, publication, review holds, or rejection.
        </p>
      </header>

      <section className="grid gap-4 rounded-lg border border-bench-line bg-bench-panel p-5 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <h2 className="text-lg font-semibold text-bench-text">Lifecycle states</h2>
          <p className="mt-2 font-mono text-sm text-bench-muted">
            received → validated → published → review-hold → rejected
          </p>
          <noscript>
            <p className="mt-3 text-sm text-bench-muted">
              JavaScript is off, so the live submission list cannot load. You can still check a known submission by id.
            </p>
          </noscript>
        </div>
        <Link
          className="rounded-md border border-bench-accent/60 px-4 py-2 text-center text-sm font-semibold text-bench-accent hover:bg-bench-accent/10"
          href="/submission/"
        >
          Check a submission
        </Link>
      </section>

      <SubmissionsLifecycle />
    </main>
  );
}
