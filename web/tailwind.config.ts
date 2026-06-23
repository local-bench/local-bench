import type { Config } from "tailwindcss";

const config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Calm synthwave: a soft aqua-cyan accent with pink + purple secondaries, on a clean
        // near-neutral dark canvas (no violet haze). Panels stay opaque and dark so the numbers and
        // charts keep full contrast — the neon lives on the chrome.
        bench: {
          bg: "#0a0d14",
          panel: "#11151f",
          line: "#222a38",
          text: "#eef2fa",
          muted: "#aab4c6",
          accent: "#3fd0d4",
          anchor: "#ff5fa8",
          "panel-2": "#0c0f17",
          "line-strong": "#38455a",
          "muted-2": "#98a4ba",
          "accent-dim": "#2a9ba0",
          "anchor-soft": "#ffa9cf",
          better: "#36e0b0",
          worse: "#ff5c6e",
          tied: "#98a4ba",
          mixed: "#b388ff",
          "lane-reasoning-edge": "#7c9fff",
          warn: "#ffb627",
          "warn-soft": "#ffd98a",
          community: "#4fe0c4",
          magenta: "#ff5fa8",
          purple: "#b388ff",
          grid: "#243044",
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
