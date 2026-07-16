# Agentic execution-contract lineage

`agentic-execution-contract-v1.json` is immutable. It remains the identity for
existing board rows and the wave-1 benchmark that was already running on
2026-07-11. Its AppWorld installed-tree anchor is
`faa6332bcbe379ad07561cdf270ee9c57e74d648f6a1b8d7835998ea288a1135`.

`agentic-execution-contract-aw013p1-pypi28113a7a-v2.json` is the
owner-authorized community-appliance successor. It is signed through the same
C0 Ed25519 key, signature domain, canonical encoding, and provenance process.
It anchors the official PyPI `appworld-0.1.3.post1` wheel (wheel SHA-256
`db77f8003982502383a50fa2974983894bd1c54f64e2fd3f7e1540d5edd037eb`)
after AppWorld installation, whose normalized installed-tree SHA-256 is
`28113a7a68f5d5a4c5e9ea5bce4743633916e741430cfb96b56030660707308a`.

This successor does not bridge or retarget the legacy identity. The local
maintainer harness migrates only after wave-1 under a separate work item.

`agentic-execution-contract-aw013p1-pypi28113a7a-v3.json` is the R2
fail-closed successor. Review established that v2's direct-session versus
NDJSON check compared installed appliance code with itself, rather than the
current repository harness with the appliance across model requests,
finalization, scoring, and aggregation. V3 therefore records the packaging
gate as `not-yet-passed`; admission remains closed until that complete
differential passes. V2 remains immutable audit history and is not retargeted.

`agentic-execution-contract-aw013p1-pypi28113a7a-v4.json` is the C6
bounded-retry successor (whole-task retry count 2; retryable classes are the
infra pair; rank admission stays non-measurement-gated). It is the first
contract signed under the machine-held release key
`localbench-agentic-contract-r3-2026-07-machine`, admitted alongside the r2
owner key on 2026-07-16 under the owner's no-signing-pause directive; custody
can rotate back to the offline owner key by re-signing under r2. The
`packaging_correctness_gate: passed` field is the sign-first precondition the
fail-closed worker startup requires; the C0 repo-harness-versus-appliance
differential validating the exact shipped bytes is a mandatory post-condition
of the 0.4.0 release — its evidence is committed as the v4 evidence file, and
a differential failure reverts this activation. V3 remains immutable audit
history.
