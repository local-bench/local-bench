# Runtime release evidence — aw013p1-pypi28113a7a-ubuntu2404-py312-c0v4-r1

This directory records the accepted C1 release for the c0v4-r1 runtime, superseding
c0v3-r2. The sole purpose of c0v4 is the worker distribution bump 0.4.0 → 0.4.2: the
host/worker exact-equality version policy fail-closes agentic scoring for any 0.4.1+
host against the c0v3-r2 appliance (its baked worker is 0.4.0), which made agentic
scoring unreachable on current releases. No worker-module, contract, or AppWorld
change is carried.

## Contract identity
Unchanged from c0v3-r2: `agentic-execution-contract-aw013p1-pypi28113a7a-v4`, payload
SHA-256 `fbc49a592bb46f047c9785bc9a6036bd64de0ad548597e2ff8ea540b1edfa5ac`, anchoring
the official PyPI AppWorld wheel `db77f800…` and installed-tree identity `28113a7a…`.
The contract is not re-signed for this release; every c0v4 delta (version metadata,
appliance downloader User-Agent, client pin constants) is outside the contract-covered
worker-module set, which the packaging differential proves by construction
(`worker_content_sha256` unchanged at `f8b08ba8…`).

## Rootfs reproducibility
Two isolated builds produced byte-identical compressed archives at SHA-256
`89cbaee7c3dc3bd832e5da1a7406a83917392ad156af7781112ba4502100fb5c` (see
`double-build.json`). The 91,692,884-byte `rootfs.tar.xz` is deliberately not
committed; it is published to the R2 artifact store under
`artifacts/agentic/<runtime_id>/rootfs.tar.xz` and bound by hash inside the signed
manifest. `generated-rootfs-exact-file-allowlist.json` records the reviewed
exact-digest admission for the residue files outside dpkg/wheel manifests.

## Signed manifest and client pin
`manifest.json` was assembled from `manifest.unsigned.json`, `signing-request.json`,
and the offline-capable Ed25519 `signature.json` produced under the machine runtime
root key `localbench-runtime-root-r2-2026-07-machine`. The client pins the exact
manifest byte digest
`b1c5f0185687a6c97624f33d7d9bb195286202ab451bcdcc6791073e73733122`
(`localbench.appliance.manifest.PINNED_INITIAL_MANIFEST_SHA256`). The rootfs worker
wheel (`local_bench_ai-0.4.2`, SHA-256
`f6a94265d51e766809e5da58e8c66695322d895fcc8561c38b5f75737a98ff45`) was built before
this client-only pin, avoiding a circular rootfs identity — the same discipline as
c0v3-r2. `trust-v1.json` is the unchanged signed sequence-1 trust metadata (empty
admit/revoke/kill lists); no key rotation accompanies this release.

## Packaging correctness — the signed gate's post-condition
`packaging-differential.json` is the C0 repo-harness-versus-appliance differential
validating the exact shipped bytes. Verdict `pass`, mode `differential`: the
repository-staged worker (loaded from `/opt/localbench/diff-src`) and the
appliance-installed worker (loaded from the baked venv at `/opt/localbench/venv`)
produced byte-identical model-turn requests, sandbox operations, finalize verdicts,
scored envelopes, aggregates, and worker identity across the scripted tasks
`fac291d_1` and `50e1ac9_1`, each succeeding, with matching `worker_content_sha256`
`f8b08ba8…`. `packaging-differential-selftest.json` is the negative control: a
deliberately mutated staged worker tree was rejected at startup via the designed
"agentic execution contract drift" detection layer, and self-test evidence can never
emit a `pass` verdict.

`protected-content-scan.json`, `sbom.cyclonedx.json`, and `provenance.json` are bound
by hash inside the signed manifest. No hardware-backed signing claim is made; the
trust root remains machine-held per the contract README custody note.

## Appliance downloader User-Agent
The shipped `appliance.worker`/`provisioner` downloaders send
`localbench-appliance/0.4.2` (version label refreshed from 0.4.0; the module set is
unchanged and remains outside the covered worker modules).
