import type { Config } from "tailwindcss";

const config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Synthwave / Outrun palette: neon orange primary + magenta + purple, with cyan as the cool
        // counterpoint (frontier ceilings), on deep indigo. Panels stay opaque and dark so the data
        // (numbers, charts) keeps full contrast — the neon lives on the chrome.
        bench: {
          bg: "#0a0418",
          panel: "#150a2b",
          line: "#2c1a52",
          text: "#f2ecff",
          muted: "#c4b8e6",
          accent: "#ff7a33",
          anchor: "#22e0e8",
          "panel-2": "#0f0622",
          "line-strong": "#463070",
          "muted-2": "#a99cc9",
          "accent-dim": "#d9621f",
          "anchor-soft": "#8ee9ee",
          better: "#36e0b0",
          worse: "#ff3d81",
          tied: "#a99cc9",
          mixed: "#b388ff",
          "lane-reasoning-edge": "#9d6bff",
          warn: "#ffb627",
          "warn-soft": "#ffd98a",
          community: "#4ff0c4",
          magenta: "#ff2e97",
          purple: "#a64dff",
          grid: "#3a1f6e",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular"],
      },
    },
  },
  plugins: [],
} satisfies Config;

export default config;
