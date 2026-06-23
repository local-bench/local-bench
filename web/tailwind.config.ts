import type { Config } from "tailwindcss";

const config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Synthwave / Outrun palette: neon cyan + magenta + purple on deep indigo. Panels stay opaque
        // and dark so the data (numbers, charts) keeps full contrast — the neon lives on the chrome.
        bench: {
          bg: "#0a0418",
          panel: "#150a2b",
          line: "#2c1a52",
          text: "#f2ecff",
          muted: "#a99cc9",
          accent: "#22e0e8",
          anchor: "#ff9e3d",
          "panel-2": "#0f0622",
          "line-strong": "#463070",
          "muted-2": "#8073a6",
          "accent-dim": "#17a7ad",
          "anchor-soft": "#ffc98a",
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
