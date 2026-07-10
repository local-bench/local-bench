# Changelog

## 0.3.1 - 2026-07-10

- Checks AppWorld agentic eligibility before downloading tokenizer or GGUF assets and reports missing harness setup with dedicated exit code 15.
- Adds `--static-only` for an explicit five-axis run under the existing `static-exec-5axis-v1` coverage identity, with the full-index consequence shown before work starts.
- Removes maintainer-specific WSL and AppWorld paths from defaults and help output; agentic runs now require explicit harness configuration.
- Keeps the 0.3.0 recoverable empty-turn behavior for transport/HTTP failures, with additive typed diagnostics. The accepted behavioral deltas are precisely: (1) generations lasting 121-600 seconds now complete instead of timing out; and (2) a turn reached after task transport-deadline exhaustion returns the recoverable empty turn without making an HTTP request. Nothing else changes versus 0.3.0 transport semantics. A task-wide monotonic deadline, socket cancellation, and joined teardown bound the longer request floor.
- Records WSL bridge operation timeouts as infrastructure timeouts visible in run diagnostics.
- Includes the 1,800-second per-task watchdog for supported slow local hardware.
