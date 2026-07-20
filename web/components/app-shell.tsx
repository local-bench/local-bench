import Link from "next/link";
import { FamilyNavMenu } from "@/components/family-nav-menu";
import { LAUNCH_FREEZE, shortHash } from "@/components/launch-freeze";
import { publicProtocolLabel } from "@/lib/board-adapter";

export function AppShell({
  children,
  families,
  usesDemoData,
  suiteVersion,
  indexVersion,
}: {
  readonly children: React.ReactNode;
  readonly families: readonly string[];
  readonly usesDemoData: boolean;
  readonly suiteVersion: string | null;
  readonly indexVersion: string;
}) {
  return (
    <div className="relative z-10 flex min-h-screen flex-col">
      <a
        href="#content"
        className="sr-only z-50 rounded bg-bench-bg px-3 py-2 font-semibold text-bench-text focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-20 border-b border-bench-line bg-bench-bg/85 backdrop-blur">
        <nav aria-label="Main" className="mx-auto flex w-full max-w-[1480px] flex-col items-start justify-between gap-3 px-5 py-3 sm:flex-row sm:items-center sm:gap-4 lg:px-8">
          <div className="flex w-full flex-wrap items-center gap-x-6 gap-y-1 sm:w-auto">
            <Link href="/" className="neon-heading text-lg font-bold tracking-tight transition-opacity hover:opacity-80">
              local-bench
            </Link>
            <div className="flex flex-wrap gap-4 text-sm text-bench-muted">
              <FamilyNavMenu families={families} />
              <Link href="/leaderboard/" className="hover:text-bench-text">
                Global board
              </Link>
              <Link href="/submissions/" className="hover:text-bench-text">
                Submissions
              </Link>
              <Link href="/compare/" className="hover:text-bench-text">
                Compare
              </Link>
              <Link href="/methodology/" className="hover:text-bench-text">
                Methodology
              </Link>
              <Link href="/submit/" className="hover:text-bench-text">
                Submit
              </Link>
              <Link href="/feedback/" className="hover:text-bench-text">
                Feedback
              </Link>
            </div>
          </div>
          <span className="shrink-0 whitespace-nowrap font-mono text-xs uppercase text-bench-accent">
            {suiteVersion ?? "scoreless catalog"} / {publicProtocolLabel(indexVersion)}
          </span>
        </nav>
        {usesDemoData ? (
          <div className="border-t border-bench-warn/25 bg-bench-warn/10 px-5 py-2 text-center text-sm font-medium text-bench-warn">
            Synthetic demo rows are marked with a DEMO badge; only measured runs carry a real Local Intelligence Index.
          </div>
        ) : null}
      </header>
      <div id="content" className="min-w-0 flex-1">{children}</div>
      <footer className="mt-10 border-t border-bench-line bg-bench-bg/60">
        <div className="mx-auto w-full max-w-[1480px] px-5 py-6 lg:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl space-y-1.5">
              <p className="font-mono text-[11px] uppercase tracking-wide text-bench-accent">
                Board data as of {LAUNCH_FREEZE.asOfDate}
              </p>
            </div>
            <div className="space-y-1 font-mono text-[11px] text-bench-muted">
              <div className="flex items-center justify-between gap-3 lg:justify-end">
                <Link
                  href="/methodology/#frozen"
                  className="uppercase tracking-wide text-bench-muted/70 hover:text-bench-text"
                  title="sha256 pins of the frozen artifacts behind this board — anyone can re-hash the served files and check them"
                >
                  integrity pins ·
                </Link>
              </div>
              <dl>
                <div className="flex items-center justify-between gap-3 lg:justify-end">
                  <dt className="uppercase tracking-wide text-bench-muted/70">board</dt>
                  <dd title={LAUNCH_FREEZE.boardSha256}>{shortHash(LAUNCH_FREEZE.boardSha256)}</dd>
                </div>
              </dl>
            </div>
          </div>
          <div className="mt-5 flex flex-col gap-2 border-t border-bench-line/60 pt-4 text-xs text-bench-muted/80 sm:flex-row sm:items-center sm:justify-between">
            <p>
              local-bench is an independent, judge-free leaderboard for local and open-weight LLMs. Model and
              benchmark names belong to their respective owners; listing a model is evaluation, not endorsement.
            </p>
            <div className="flex shrink-0 gap-4">
              <Link href="/methodology/" className="hover:text-bench-text">
                Methodology
              </Link>
              <Link href="/methodology/#licenses" className="hover:text-bench-text">
                Licenses
              </Link>
              <Link href="/feedback/" className="hover:text-bench-text">
                Feedback
              </Link>
              <a href="https://github.com/local-bench/local-bench" className="hover:text-bench-text">
                GitHub
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
