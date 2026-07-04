# Generated-Math Contamination Canary

The generated-math benchmark now has two item sets with the same methodology surface:

- public generated-math files in `suite/v0/genmath_standard.jsonl` and `suite/v0/genmath_quick.jsonl`
- a private held-back sentinel in `suite/v0/private/genmath_sentinel.jsonl`

The public files remain the committed suite-v0 artifacts. They use the public seed and keep the
120-item standard set and 40-item quick set byte-stable across rebuilds.

The private sentinel is built locally from the same template bank with a separate private seed
source. It targets the same category/difficulty distribution as the public standard set at half
size, and the builder asserts there is no public/private overlap by rendered statement or by
`(template, params)`.

This supports the contamination/gaming canary in methodology v2 section 6 and the threat model:
a setup's public generated-math score and private-sentinel score should agree within expected
sampling noise when the difficulty mix is matched. A large `public >> private` gap is evidence
for contamination, answer lookup, or benchmark-specific gaming.

The sentinel directory is gitignored and must not be committed or published. Its lock file records
only aggregate integrity metadata: item count, SHA-256, and a seed-source note. It does not record
the private seed value.

Server-side injection of sentinel items into benchmark runs, aggregation of private-only results,
and the public/private gap test are later server tasks. This document only covers the repository
generation split and gitignore hygiene.
