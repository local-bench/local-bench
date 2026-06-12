import type { Config } from "tailwindcss";

const config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bench: {
          bg: "#0b0e14",
          panel: "#11161f",
          line: "#273244",
          text: "#eef4fb",
          muted: "#99a7b8",
          accent: "#32d2b4",
          anchor: "#f6b24b",
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
