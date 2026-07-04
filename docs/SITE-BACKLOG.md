# Site / UX backlog (ideas for later — not scheduled)

Product/UX ideas captured during the build, to pick up post-foundations.

## Live run progress bar (Michael, 2026-06-20)
When a user runs our benchmark (`localbench run` / `localbench code`), show a **live progress bar** with
per-bench / per-item progress + ETA — nice UX while a long reasoning-on run executes. Surface it both in the
CLI and, where a run is in flight, on the site.
- Reference UI: https://x.com/MiaAI_lab/status/2067845236328472770
- Notes: the runner already drives items concurrently and the manifest captures per-item timing, so the data for
  a progress bar + tok/s + ETA is already produced; this is a presentation layer (CLI: a tqdm-style bar gated to
  a TTY; site: stream/poll run state). Keep it from interfering with the deterministic scoring.
