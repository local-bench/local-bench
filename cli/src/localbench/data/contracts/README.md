# Agentic execution-contract lineage

`agentic-execution-contract-v1.json` is immutable. It remains the identity for
existing board rows and the wave-1 benchmark that was already running on
2026-07-11. Its AppWorld installed-tree anchor is
`faa6332bcbe379ad07561cdf270ee9c57e74d648f6a1b8d7835998ea288a1135`.

`agentic-execution-contract-aw013p1-pypi28113a7a-v2.json` (retired from the
shipped package after c0v5-r1 — nothing loads or cites it; the immutable audit
copy lives in git history) is the owner-authorized community-appliance
successor. It is signed through the same
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

`agentic-execution-contract-aw013p1-pypi28113a7a-v5.json` (payload SHA-256
`b18d903b…`) was cut for the c0v5-r1 runtime and CLI 0.4.3. The native-Linux agentic host changed `wsl_worker.py` (a covered
module), so unlike c0v4 this cut re-measures `covered_behavior` and asserts —
then proves via the committed c0v5-r1 packaging differential — score-protocol
equivalence with v4. It is signed under `localbench-agentic-contract-2026-07`
(the signer derives the key id from the signing key's public half in
`CONTRACT_PUBLIC_KEYS`; the retired r3 machine key stays trusted for v4
verification). v5 introduces the pre-mark packaging gate (oracle Fork-1
option B): the gate records the pre-sign probe rootfs and native-conformance
evidence, and delegates publication authority to the signed c0v5-r1 release
manifest, because a contract baked inside the rootfs cannot bind the final
rootfs hash without a fixpoint. V4 remains immutable audit history.

`agentic-execution-contract-aw013p1-pypi28113a7a-v6.json` (payload SHA-256
`6e63f93b…`) is the 0.4.7 host-side successor that healed the 0.4.6 drift
wall: score-affecting host modules were edited after v5 was signed, so v6
re-measured `covered_behavior` from the tree with the appliance unchanged
(published c0v5 rootfs `053eb073…`). Signed under
`localbench-agentic-contract-2026-07`; full rationale in commit 2ee2279.

`agentic-execution-contract-aw013p1-pypi28113a7a-v7.json` (payload SHA-256
`47695014…`) is the active contract, cut for CLI 0.4.12's execution-contract
work: agentic request template kwargs now derive from the run's resolved
execution contract instead of profile-ID reconstruction (a covered-behavior
change in `orchestrate`/`serving.agentic_support`), alongside the
gguf-repo-only tri-state profile resolution and runtime probe. The appliance
is again unchanged (same c0v5 rootfs `053eb073…`, same native-conformance
evidence). Signed under `localbench-agentic-contract-2026-07`. v7 also
generalized the manifest cross-bind: the c0v5 manifest's immutable v5 pin is
now accepted anywhere on the verified supersedes chain
(`supersedes_chain_payload_sha256s`), because the one-hop window used before
v7 broke as soon as the chain grew two links past the manifest pin.

`agentic-execution-contract-aw013p1-pypi28113a7a-v8.json` (payload SHA-256
`0d0c6073…`) is the active contract, cut for CLI 0.4.13: the generic GGUF
renderer work moved the orchestrate renderer guard and budget preparation
ahead of campaign-path mutation (a covered-behavior change in
`localbench.orchestrate`; the renderer itself delegates to the pinned
server's `/apply-template`). Appliance unchanged (same c0v5 rootfs
`053eb073…`, same native-conformance evidence). Signed under
`localbench-agentic-contract-2026-07`. The v7-introduced chain-aware
manifest cross-bind covers the deeper lineage (v8→v7→v6→v5) unchanged.
