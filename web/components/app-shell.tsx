import Link from "next/link";

export function AppShell({
  children,
  usesDemoData,
  suiteVersion,
  indexVersion,
}: {
  readonly children: React.ReactNode;
  readonly usesDemoData: boolean;
  readonly suiteVersion: string;
  readonly indexVersion: string;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-bench-line bg-bench-bg/85 backdrop-blur">
        <nav className="mx-auto flex w-full max-w-[1480px] items-center justify-between gap-4 px-5 py-3 lg:px-8">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
            <Link href="/" className="font-semibold text-bench-text hover:text-bench-accent">
              local-bench
            </Link>
            <div className="flex flex-wrap gap-4 text-sm text-bench-muted">
              <Link href="/" className="hover:text-bench-text">
                Leaderboard
              </Link>
              <Link href="/compare" className="hover:text-bench-text">
                Compare
              </Link>
              <Link href="/methodology" className="hover:text-bench-text">
                Methodology
              </Link>
              <Link href="/trust" className="hover:text-bench-text">
                Trust
              </Link>
              <Link href="/submit" className="hover:text-bench-text">
                Submit
              </Link>
            </div>
          </div>
          <span className="font-mono text-xs uppercase text-bench-accent">
            {suiteVersion} · {indexVersion}
          </span>
        </nav>
        {usesDemoData ? (
          <div className="border-t border-bench-warn/25 bg-bench-warn/10 px-5 py-2 text-center text-sm font-medium text-bench-warn">
            Preview uses synthetic demo data — not real measurements (Track 2 will replace it).
          </div>
        ) : null}
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
