# Landing-page animated hero banner — build spec (oracle-designed, 2026-06-24)

GPT-5.5 Pro (oracle) session `localbench-animated-hero-banner`. A server-rendered, **CSS-first** hero
with a one-shot ~4.7s timeline: **local "thinking" indicator → benchmark-trace token stream → masked
crossfade into the real `.neon-heading` `local-bench` logo**. No animation dependency, no per-token
React state. The static final state is the DEFAULT; motion is opt-in under
`prefers-reduced-motion: no-preference`.

## Concept (feel: a quiet LOCAL inference session booting up — NOT a cyberpunk splash, NOT a chatbot)

Contained in a dark glassy panel matching the existing chart/card system (cyan/pink edge glow, soft
grid echo, mono trace text, large final logo).

| Time | Phase | Visual |
|---|---|---|
| 0–250ms | Arrival | Panel already laid out; faint terminal horizon |
| 250–1350ms | Thinking | a small "local core" chip pulses + blinks |
| 1350–3500ms | Token generation | mono trace rows stream downward |
| 3500–4450ms | Resolve | token layer fades while the real logo reveals via a horizontal `clip-path` mask |
| 4450ms+ | Settled | static logo + tagline; **no loop** |

**Thinking indicator** = a tiny "local inference core": a cyan rounded-square "chip" with two pink
bracket "arms" that twitch (`steps(2,end)`), a soft cyan pulse ring, and a pink caret that blinks
twice. No emoji, no mascot, no big spinner.

## Decisions (oracle recs; my picks marked — easy to change, all CSS/text)

- **Streamed content = Option B benchmark trace** (recommended; on-brand + specific). DECORATIVE
  (`aria-hidden="true"`). The exact lines:
  ```
  > local-bench session
  runtime: local / open-weight / judge-free
  cloud: off
  load: weights from disk
  warmup: deterministic prompts
  run: answer-key eval · code · math · reasoning
  measure: tokens/s · vram · latency · accuracy
  index: normalize → compare → lock
  artifact: reproducible run hash
  resolve: local-bench
  ```
  **Do NOT** show a fake "Local Intelligence Index 84.7" — a synthetic score undermines the
  reproducible/judge-free trust posture. (Rejected: Option A abstract glyphs = less meaningful;
  Option C faux chat = makes it feel like a chat product.)
- **Tagline (pick):** `Open weights. Local hardware. Reproducible results.` (punchier than the longer
  "Reproducible, judge-free rankings for local open-weight models.").
- **Eyebrow:** `judge-free local LLM benchmarks` (mono, uppercase, cyan).
- **Play ONCE per page mount, then settle** (no loop — the page is a leaderboard; attention should
  move to the data). No sessionStorage unless reviewers complain.
- **Resolve = masked crossfade, NOT character morph** (morph is fragile/gimmicky). The logo is real
  `<h1 class="neon-heading">local-bench</h1>` present in HTML from first paint, revealed via
  `clip-path: inset(0 50% 0 50%)` → `inset(0 0 0 0)` + opacity/translateY near the end.

## Implementation — CSS keyframes + static SSR markup (Server Component; no `"use client"`)

Files: `web/components/hero-banner.tsx`, `web/components/hero-banner.module.css`,
`web/components/hero-banner.test.tsx`. Wire into `web/app/page.tsx` as the FIRST child of `<main>`
(before `BestVariantVramScatter`). Logo stays REAL TEXT using the same `.neon-heading` class as the
header (`app-shell.tsx`). Reserve height with `min-height` so the chart below does not shift.

### Reference component (`hero-banner.tsx`)
```tsx
import type { CSSProperties } from "react";
import styles from "./hero-banner.module.css";

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

export function HeroBanner() {
  return (
    <section className={styles.hero} aria-labelledby="home-hero-title">
      <div className={styles.panelGrid} aria-hidden="true" />
      <div className={styles.thinking} aria-hidden="true">
        <span className={styles.core} />
        <span className={styles.thinkingText}>thinking locally</span>
        <span className={styles.caret}>▌</span>
      </div>
      <div className={styles.stream} aria-hidden="true">
        {TRACE_LINES.map((line, index) => (
          <p key={line} className={styles.streamRow} style={{ "--row": index } as CSSProperties}>
            {line}
          </p>
        ))}
      </div>
      <div className={styles.finalMark}>
        <p className={styles.eyebrow}>judge-free local LLM benchmarks</p>
        <h1 id="home-hero-title" className={`${styles.logo} neon-heading`}>local-bench</h1>
        <p className={styles.tagline}>Open weights. Local hardware. Reproducible results.</p>
      </div>
    </section>
  );
}
```

### Reference CSS module (`hero-banner.module.css`)
Bench tokens: bg `#0a0d14`, panel `#11151f`, line `#222a38`, text `#eef2fa`, muted `#aab4c6`, accent
cyan `#3fd0d4`, pink `#ff5fa8`, purple `#b388ff`; mono = `var(--font-mono)`.

```css
.hero {
  position: relative; isolation: isolate; overflow: hidden;
  min-height: clamp(20rem, 36vw, 32rem);
  display: grid; place-items: center;
  border: 1px solid rgba(34, 42, 56, 0.96); border-radius: 1.25rem;
  background:
    radial-gradient(circle at 50% 8%, rgba(63,208,212,0.13), transparent 34%),
    radial-gradient(circle at 80% 30%, rgba(255,95,168,0.08), transparent 32%),
    linear-gradient(180deg, rgba(17,21,31,0.92), rgba(10,13,20,0.96));
  box-shadow: 0 0 0 1px rgba(63,208,212,0.14), 0 24px 90px -50px rgba(63,208,212,0.6);
}
.panelGrid {
  position: absolute; inset: 0; z-index: -1; opacity: 0.28;
  background-image:
    linear-gradient(rgba(63,208,212,0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,95,168,0.10) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(circle at 50% 42%, #000 0 38%, transparent 74%);
}
.finalMark { position: relative; z-index: 3; max-width: 56rem; padding: 4rem 1.5rem; text-align: center; }
.eyebrow {
  margin: 0 0 0.8rem; font-family: var(--font-mono); font-size: 0.78rem;
  letter-spacing: 0.16em; text-transform: uppercase; color: rgba(63,208,212,0.92);
}
.logo {
  margin: 0; font-family: var(--font-mono); font-size: clamp(3.4rem, 9vw, 8.5rem);
  font-weight: 700; line-height: 0.95; letter-spacing: -0.08em;
}
.tagline { margin: 1.15rem auto 0; max-width: 40rem; color: #aab4c6; font-size: clamp(1rem, 2vw, 1.25rem); }
.thinking {
  position: absolute; z-index: 2; display: flex; align-items: center; gap: 0.75rem;
  font-family: var(--font-mono); color: #aab4c6;
}
.core {
  position: relative; width: 1.35rem; height: 1.35rem;
  border: 1px solid rgba(63,208,212,0.86); border-radius: 0.35rem;
  box-shadow: 0 0 18px rgba(63,208,212,0.28);
}
.core::before, .core::after {
  content: ""; position: absolute; top: 50%; width: 0.45rem; height: 1px; background: rgba(255,95,168,0.78);
}
.core::before { right: 100%; }
.core::after { left: 100%; }
.thinkingText { font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; }
.caret { color: #ff5fa8; }
.stream {
  position: absolute; inset: 0; z-index: 1; display: flex; flex-direction: column;
  justify-content: center; gap: 0.35rem; padding: clamp(1.5rem, 4vw, 4rem);
  font-family: var(--font-mono); font-size: clamp(0.72rem, 1.35vw, 0.98rem);
  color: rgba(238,242,250,0.74);
  mask-image: linear-gradient(to bottom, transparent, #000 24%, #000 76%, transparent);
}
.streamRow { margin: 0; opacity: 0; transform: translateY(-0.75rem); text-shadow: 0 0 16px rgba(63,208,212,0.18); }
.streamRow:nth-child(3n)   { color: rgba(63,208,212,0.78); }
.streamRow:nth-child(3n+1) { color: rgba(255,95,168,0.68); }
.streamRow:nth-child(3n+2) { color: rgba(179,136,255,0.72); }

@media (prefers-reduced-motion: no-preference) {
  .thinking { animation: hero-thinking 4.7s ease both; }
  .core { animation: hero-core-pulse 0.72s ease-in-out 2 both; }
  .core::before, .core::after { animation: hero-core-gesture 0.36s steps(2, end) 3 both; }
  .caret { animation: hero-caret-blink 0.28s steps(1, end) 5 both; }
  .stream { animation: hero-stream-plane 4.7s ease both; }
  .streamRow { animation: hero-stream-row 2.25s cubic-bezier(0.22,1,0.36,1) both; animation-delay: calc(1.28s + (var(--row) * 95ms)); }
  .finalMark { animation: hero-final-mark 4.7s cubic-bezier(0.22,1,0.36,1) both; }
  .logo { animation: hero-logo-resolve 4.7s cubic-bezier(0.22,1,0.36,1) both; }
}
@keyframes hero-thinking { 0%,5%{opacity:0;transform:translateY(0.4rem);} 10%,31%{opacity:1;transform:translateY(0);} 39%,100%{opacity:0;transform:translateY(-0.25rem);} }
@keyframes hero-core-pulse { 0%,100%{transform:scale(1);box-shadow:0 0 16px rgba(63,208,212,0.22);} 50%{transform:scale(1.08);box-shadow:0 0 26px rgba(63,208,212,0.42);} }
@keyframes hero-core-gesture { 0%,100%{transform:translateY(-50%) scaleX(0.8);opacity:0.55;} 50%{transform:translateY(-50%) scaleX(1.35);opacity:1;} }
@keyframes hero-caret-blink { 0%,49%{opacity:1;} 50%,100%{opacity:0;} }
@keyframes hero-stream-plane { 0%,25%{opacity:0;transform:translateY(-0.25rem);} 32%,68%{opacity:1;transform:translateY(0);} 80%,100%{opacity:0;transform:translateY(0.5rem);} }
@keyframes hero-stream-row { 0%{opacity:0;transform:translateY(-0.8rem);} 18%,70%{opacity:0.86;transform:translateY(0);} 100%{opacity:0;transform:translateY(1.1rem);} }
@keyframes hero-final-mark { 0%,70%{opacity:0;transform:translateY(0.45rem) scale(0.985);} 84%,100%{opacity:1;transform:translateY(0) scale(1);} }
@keyframes hero-logo-resolve { 0%,72%{clip-path:inset(0 50% 0 50%);} 90%,100%{clip-path:inset(0 0 0 0);} }

@media (prefers-reduced-motion: reduce) { .thinking, .stream { display: none; } }
@media (prefers-contrast: more) { .hero { box-shadow: none; } .panelGrid { opacity: 0.1; } }
@media (forced-colors: active) {
  .hero { border-color: CanvasText; background: Canvas; box-shadow: none; }
  .panelGrid, .thinking, .stream { display: none; }
  .eyebrow, .tagline { color: CanvasText; }
}
```
(Numbers tuneable; the principle is non-negotiable: **static final state is the default; motion gated
behind `prefers-reduced-motion: no-preference`; hydration must NOT depend on timers/random/viewport**.)

## Accessibility + performance (hard requirements)
One real `<h1>` (`neon-heading`); thinking + stream are `aria-hidden` (NOT exposed to screen readers).
Reduced-motion → final logo+tagline immediately, decorative layers hidden. forced-colors/contrast
fallbacks (above). NO animation lib, NO `setInterval`, NO per-char React state, NO canvas, NO
layout-changing animation — animate only `opacity`/`transform`/`clip-path`. `min-height` reserves space
→ zero CLS. Avoid animating blur/filter intensity; `will-change` sparingly or not at all.

## Tests
**Vitest** (`hero-banner.test.tsx`): exactly one `h1` with text `local-bench` + class `neon-heading`;
stream + thinking are `aria-hidden`; tagline visible; trace lines contain NO Claude-branded language;
trace lines contain NO fake model-specific scores; stable snapshot. **Playwright** (add a
`web/e2e/home-hero.spec.ts`): (1) reduced-motion (`emulateMedia({reducedMotion:'reduce'})`) → logo +
tagline visible immediately, stream/thinking hidden; (2) normal motion → after > animation duration,
logo + tagline visible, stream layer opacity 0 / hidden; (3) **no layout shift** — hero box + chart-top
position unchanged (within tolerance) immediately after load vs after the animation; (4) forced-colors
if supported. Do NOT assert intermediate animation frames (brittle).

## Reviewer checklist (REJECT if any are true)
logo is an image/canvas/SVG instead of real text · final logo not using `.neon-heading` · needs Framer
Motion/GSAP/new dep · tokens generated via React state on an interval · stream exposed to screen
readers · reduced-motion users still see streaming/pulsing · hero shifts the chart after load · stream
includes fake model-specific results · final state does not settle into a static logo+tagline.

*The strongest version is restrained: one local "thinking" pulse, one benchmark-trace stream, one masked
reveal into the real `local-bench` heading, then silence. Full oracle transcript: session
`localbench-animated-hero-banner` (2026-06-24).*
