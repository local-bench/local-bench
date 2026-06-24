import type { CSSProperties } from "react";
import styles from "./hero-banner.module.css";

// Decorative benchmark "trace" that streams during the intro animation. It is on-brand and specific
// but deliberately carries NO synthetic score and NO model-specific result — a fabricated number
// would undermine the reproducible / judge-free trust posture. This layer is aria-hidden.
const TRACE_LINES = [
  "> local-bench session",
  "runtime: local / open-weight / judge-free",
  "cloud: off",
  "load: weights from disk",
  "warmup: deterministic prompts",
  "run: answer-key eval · code · math · reasoning",
  "measure: tokens/s · vram · latency · accuracy",
  "index: normalize → compare → lock",
  "artifact: reproducible run hash",
  "resolve: local-bench",
] as const;

/**
 * Server-rendered hero banner. Pure static markup — no "use client", no per-token React state, no
 * timers. The final logo + tagline is the DEFAULT state present from first paint; the intro motion
 * is opt-in CSS gated behind `prefers-reduced-motion: no-preference` in the module stylesheet.
 */
export function HeroBanner() {
  // CSS Module classes are read via bracket notation because this repo's tsconfig sets
  // `noPropertyAccessFromIndexSignature` (the generated module type is an index signature).
  return (
    <section className={styles["hero"]} aria-labelledby="home-hero-title" data-testid="home-hero">
      <div className={styles["panelGrid"]} aria-hidden="true" />
      <div className={styles["thinking"]} aria-hidden="true" data-testid="home-hero-thinking">
        <span className={styles["core"]} />
        <span className={styles["thinkingText"]}>thinking locally</span>
        <span className={styles["caret"]}>▌</span>
      </div>
      <div className={styles["stream"]} aria-hidden="true" data-testid="home-hero-stream">
        {TRACE_LINES.map((line, index) => (
          <p key={line} className={styles["streamRow"]} style={{ "--row": index } as CSSProperties}>
            {line}
          </p>
        ))}
      </div>
      <div className={styles["finalMark"]} data-testid="home-hero-mark">
        <h1 id="home-hero-title" className={`${styles["logo"]} neon-heading`}>
          local-bench
        </h1>
        <p className={styles["tagline"]}>Open weights. Local hardware. Reproducible results.</p>
      </div>
    </section>
  );
}
