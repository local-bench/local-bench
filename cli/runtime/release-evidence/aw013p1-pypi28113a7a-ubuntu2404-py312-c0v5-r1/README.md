# Runtime release evidence — aw013p1-pypi28113a7a-ubuntu2404-py312-c0v5-r1

This directory records the accepted C1 release for the c0v5-r1 runtime, superseding
c0v4-r1. c0v5 ships the 0.4.3 worker (wheel SHA-256
`83825e2c68e29397b3ea61e5e7bb1eefe667be2e281a03228c06fd183181fe1b`), whose native-Linux
host support changed `wsl_worker.py` — a contract-covered module — so unlike c0v4 this
release re-signs the execution contract.

## Contract identity
`agentic-execution-contract-aw013p1-pypi28113a7a-v5`, payload SHA-256
`b18d903b3bffcaf3fa291fd78d5612910e90c4ce3617b4c10a6cd36fa5930bb0`, superseding v4
(`fbc49a59…`) with asserted-then-proven score-protocol equivalence. The v5 contract was
signed pre-mark (packaging gate recorded with the pre-sign probe rootfs `049ebe06…` and
native-conformance evidence `775bcdd0…`; publication authority delegated to this signed
manifest), because the contract is baked into the rootfs and therefore cannot bind the
final rootfs hash without a fixpoint. The shipped binding below closes the loop.

## Rootfs reproducibility
Two isolated builds produced byte-identical compressed archives at SHA-256
`053eb073aa0b8f4c3e9e4797b9c02b2bcca863c22dc3218128fe7bde6cb1b00a` (91,727,800 bytes,
see `double-build.json`). The rootfs archive is published to the R2 artifact store under
`artifacts/agentic/<runtime_id>/rootfs.tar.xz` and bound by hash inside the signed
manifest. In-rootfs identity was verified against the signed contract before signing the
manifest: the baked worker measures `covered_behavior` == the signed v5 value (no drift),
`worker_content_sha256` `ff7dda42…`, and `/usr/bin/bwrap` `52231e1c…`.

## Signed manifest and client pin
`manifest.json` binds the rootfs `053eb073…`, the worker wheel `83825e2c…`, and the v5
contract payload `b18d903b…`, signed under the Ed25519 runtime root key
`localbench-runtime-root-2026-07` (present in the client's static trust map; the c0v4
machine key remains trusted for c0v4 verification). The client pins the exact manifest
byte digest `1abc3a10b25534b043c787ab4b5ee76c4efbb9168b93dd365b12a8f1570ad319`
(`localbench.appliance.manifest.PINNED_INITIAL_MANIFEST_SHA256`). The rootfs worker
wheel was built before this client-only pin, avoiding a circular rootfs identity.
`trust-v1.json` is the unchanged signed sequence-1 trust metadata; no key rotation
accompanies this release.

## Packaging correctness — the signed gate's post-condition
`packaging-differential.json` is the C0 repo-harness-versus-appliance differential over
the exact shipped bytes (rootfs `053eb073…`, wheel `83825e2c…`). Verdict `pass`, mode
`differential`: the repository-staged worker and the appliance-installed worker produced
byte-identical model-turn requests, sandbox operations, finalize verdicts, scored
envelopes, aggregates, and worker identity across the scripted tasks `fac291d_1` and
`50e1ac9_1`, each succeeding. `packaging-differential-selftest.json` is the negative
control: a deliberately mutated staged worker tree was rejected at startup via the
designed "agentic execution contract drift" detection layer.

Pre-sign activation evidence: a stock Ubuntu 24.04 VM (default AppArmor) reached full
activation green (state=active, both canaries, handshake accepted) with this rootfs and
the 0.4.3 client under a test-key manifest whose payload differed from the release
manifest only in the x86_64 AppWorld lock URL serving path (bytes hash-identical).

`protected-content-scan.json`, `sbom.cyclonedx.json`, and `provenance.json` are bound by
hash inside the signed manifest. No hardware-backed signing claim is made; the trust
root remains machine-held per the contract README custody note.
