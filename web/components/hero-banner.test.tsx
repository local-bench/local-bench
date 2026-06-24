import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HeroBanner } from "./hero-banner";

// The hero is a pure (synchronous) Server Component, so we can render it to a static markup string
// with react-dom/server in the node environment. This needs no jsdom and no testing-library — it
// asserts on the SSR HTML exactly as it ships to first paint.
const html = renderToStaticMarkup(<HeroBanner />);

function countOccurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("HeroBanner", () => {
  it("renders exactly one <h1> reading 'local-bench'", () => {
    expect(countOccurrences(html, "<h1")).toBe(1);
    expect(html).toMatch(/<h1[^>]*>local-bench<\/h1>/);
  });

  it("uses the shared .neon-heading class on the logo heading", () => {
    // The header logo in app-shell.tsx is `<Link className="neon-heading ...">local-bench</Link>`;
    // the hero <h1> must carry the same global class so the gradient text matches exactly.
    const h1 = /<h1\b[^>]*\bclass="([^"]*)"[^>]*>/.exec(html);
    expect(h1).not.toBeNull();
    const classes = (h1?.[1] ?? "").split(/\s+/);
    expect(classes).toContain("neon-heading");
  });

  it("marks the thinking and stream layers aria-hidden (kept off the a11y tree)", () => {
    const thinking = /<div[^>]*data-testid="home-hero-thinking"[^>]*>/.exec(html)?.[0] ?? "";
    const stream = /<div[^>]*data-testid="home-hero-stream"[^>]*>/.exec(html)?.[0] ?? "";
    expect(thinking).not.toBe("");
    expect(stream).not.toBe("");
    expect(thinking).toContain('aria-hidden="true"');
    expect(stream).toContain('aria-hidden="true"');
  });

  it("shows the tagline copy", () => {
    expect(html).toContain("Open weights. Local hardware. Reproducible results.");
  });

  it("contains no Claude / Anthropic-branded language in the trace", () => {
    // The judge-free posture means no LLM-judge branding in the decorative stream.
    expect(html).not.toMatch(/claude/i);
    expect(html).not.toMatch(/anthropic/i);
    expect(html).not.toMatch(/\bgpt\b/i);
    expect(html).not.toMatch(/openai/i);
    expect(html).not.toMatch(/\bllm[- ]?judge\b/i);
  });

  it("contains no fabricated model-specific benchmark scores in the trace", () => {
    // A synthetic "Local Intelligence Index 84.7"-style number would undermine the reproducible /
    // judge-free trust posture, so the trace must carry no concrete score figures at all.
    expect(html).not.toMatch(/local intelligence index/i);
    // No decimal "score" numbers (e.g. 84.7) and no percentages anywhere in the rendered trace.
    expect(html).not.toMatch(/\d+\.\d+/);
    expect(html).not.toMatch(/\d+\s?%/);
  });

  it("matches the stable SSR snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});
