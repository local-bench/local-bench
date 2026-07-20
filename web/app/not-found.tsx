import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-5 py-16 lg:px-8">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">404</p>
      <h1 className="text-4xl font-semibold text-bench-text">Page not found</h1>
      <p className="max-w-2xl leading-7 text-bench-muted">
        That local-bench page does not exist or is no longer published. Return to the leaderboard or browse model families.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link className="font-semibold text-bench-accent hover:underline" href="/">Go to local-bench</Link>
        <Link className="font-semibold text-bench-accent hover:underline" href="/families/">Browse model families</Link>
      </div>
    </main>
  );
}
