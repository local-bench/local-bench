import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    testTimeout: 20_000,
    setupFiles: ["./tests/setup.ts"],
    // Library unit tests (tests/) plus component render tests (components/*.test.tsx). Component
    // tests render Server Components to static markup with react-dom/server in the node env — no
    // jsdom and no new dependency. CSS Module imports are auto-mocked to a class-name proxy because
    // `css` processing is left disabled (the default), so styling never needs to be evaluated here.
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx", "components/**/*.test.tsx"],
  },
});
