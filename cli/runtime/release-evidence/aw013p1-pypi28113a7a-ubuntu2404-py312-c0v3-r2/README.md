# Runtime release evidence — aw013p1-pypi28113a7a-ubuntu2404-py312-c0v3-r2

This directory records the accepted C1 release for the R2 fail-closed successor runtime
`aw013p1-pypi28113a7a-ubuntu2404-py312-c0v3-r2`. It supersedes the c0v2-r1 release, which
R2 review found had unproven official-wheel installation and overstated packaging evidence.

## Contract identity
Governed by `agentic-execution-contract-aw013p1-pypi28113a7a-v4` (C6 bounded-retry successor),
payload SHA-256 `fbc49a592bb46f047c9785bc9a6036bd64de0ad548597e2ff8ea540b1edfa5ac`. It anchors
the official PyPI AppWorld wheel SHA-256
`db77f8003982502383a50fa2974983894bd1c54f64e2fd3f7e1540d5edd037eb` and installed-tree identity
`28113a7a68f5d5a4c5e9ea5bce4743633916e741430cfb96b56030660707308a`. The v4 contract was signed
under the machine-held release key `localbench-agentic-contract-r3-2026-07-machine`; the older
owner and r2 keys remain admitted so prior artifacts continue to verify. `agentic-execution-
contract-v1` remains authoritative for legacy board rows; there is no bridge or retargeting.

## Rootfs reproducibility
Two isolated builds produced byte-identical compressed archives at SHA-256
`257108fb8b17ec11374acf81d80d24419c677aea7de78dcf9ee8f3ece730ac11` (see `double-build.json`).
The 91,694,444-byte `rootfs.tar.xz` is deliberately not committed; it is published to the R2
artifact store under `artifacts/agentic/<runtime_id>/rootfs.tar.xz` and bound by hash inside
the signed manifest. `generated-rootfs-exact-file-allowlist.json` records the reviewed
exact-digest admission for the 1,507 residue files outside dpkg/wheel manifests.

## Signed manifest and client pin
`manifest.json` was assembled from `manifest.unsigned.json`, `signing-request.json`, and the
offline-capable Ed25519 `signature.json` produced under the machine runtime root key
`localbench-runtime-root-r2-2026-07-machine`. The client pins the exact manifest byte digest
`81b1054cbd788e706a64f0708f3570ea40cca7330046ad7f77b6cd7c7be4a675` (see
`localbench.appliance.manifest.PINNED_INITIAL_MANIFEST_SHA256`). The rootfs worker wheel
(`local_bench_ai-0.4.0`, SHA-256 `9d2b7962932e6b3b6ae57f338ee3fab4b2233ab48333c7a124b53794d9c6ab3f`)
was built before this client-only pin, avoiding a circular rootfs identity. `trust-v1.json`
is the signed sequence-1 trust metadata (empty admit/revoke/kill lists).

## Packaging correctness — the signed gate's post-condition
`packaging-differential.json` is the C0 repo-harness-versus-appliance differential that
validates the exact shipped bytes as the mandatory post-condition of the sign-first contract
gate. Verdict `pass`, mode `differential`: both the repository-staged worker (loaded entirely
from `/opt/localbench/diff-src`) and the appliance-installed worker (loaded entirely from the
baked venv at `/opt/localbench/venv`) produced byte-identical model-turn requests, sandbox
operations, finalize verdicts, scored envelopes, aggregates, and worker identity across the
two scripted tasks `fac291d_1` and `50e1ac9_1`, each succeeding, with matching
`worker_content_sha256` `f8b08ba8…`. `packaging-differential-selftest.json` is the negative
control: a deliberately mutated staged worker tree was rejected at startup via the designed
"agentic execution contract drift" detection layer, and self-test evidence can never emit a
`pass` verdict.

`protected-content-scan.json`, `sbom.cyclonedx.json`, and `provenance.json` are bound by hash
inside the signed manifest. No hardware-backed signing claim is made. This release's trust root
is machine-held (see the contract README custody note); rotation to an offline root remains a
pure re-sign under the retained key admissions.

## Downloader User-Agent re-pin
The bytes here supersede an earlier c0v3-r2 build (rootfs `b1fd82aa…`, pin `2347cdb8…`) whose
appliance downloader sent an anonymous urllib User-Agent that the local-bench.ai edge
bot-protection 403'd on a real public provision. The shipped `appliance.worker`/`provisioner`
downloaders now send an explicit `localbench-appliance/0.4.0` User-Agent. Those modules are not
covered worker modules, so `worker_content_sha256` and the v4 execution contract are unchanged;
the rootfs and manifest bytes moved and were re-validated by a fresh C0 packaging differential
and re-signed.
