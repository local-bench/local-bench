# Changelog

## 0.3.1 - 2026-07-10

- Checks AppWorld agentic eligibility before downloading tokenizer or GGUF assets and reports missing harness setup with dedicated exit code 15.
- Adds `--static-only` for an explicit five-axis run under the existing `static-exec-5axis-v1` coverage identity, with the full-index consequence shown before work starts.
- Removes maintainer-specific WSL and AppWorld paths from defaults and help output; agentic runs now require explicit harness configuration.
- Sizes chat request timeouts from the legal output-token budget with a 600-second floor and one task-wide monotonic deadline. Rows whose calls never reached the old 120-second timeout reproduce identically; transport failures remain recoverable empty turns and now carry additive typed diagnostics.
- Records WSL bridge operation timeouts as infrastructure timeouts visible in run diagnostics.
- Includes the 1,800-second per-task watchdog for supported slow local hardware.
