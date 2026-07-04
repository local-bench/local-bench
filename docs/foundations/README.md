# local-bench foundations

Current status: 2026-06-28. The canonical public methodology is the modular v2.1 suite:

- Agentic: 50%
- Knowledge: 15%
- Instruction-Following: 15%
- Tool-calling: 10%
- Coding: 10%

Math, long-context, and coding-exec stay as diagnostic or opt-in modules until they have enough local-model evidence, runtime safety, and public-repeatability guarantees to carry headline weight.

## Start Here

Read these first for current work:

1. [`STATUS-2026-06-28.md`](STATUS-2026-06-28.md) - current axis split, module registry, and cleanup note.
2. [`../REPRODUCE.md`](../REPRODUCE.md) - how to run the default reproducible suite.
3. [`../scoring-methodology.md`](../scoring-methodology.md) - scoring and governance rules.
4. [`../../README.md`](../../README.md) - operator-facing overview.

## Historical Notes

Files dated 2026-06-14 to 2026-06-26 are research and decision history. They remain useful for provenance, but they are not the current source of truth when they conflict with the v2.1 registry or the files listed above.

In particular, older language about "Core Text", v1/v2.0 headline weights, or agentic-only rows is superseded by the v2.1 axis registry and scorecard. Keep those files for audit trail; use this README and `STATUS-2026-06-28.md` for active planning.
