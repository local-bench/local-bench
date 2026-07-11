# Runtime release evidence

This directory records the accepted C1 release for `aw013p1-pypi28113a7a-ubuntu2404-py312-c0v2-r1`. The two isolated builds produced byte-identical compressed archives at SHA-256 `d6d7d86cc578c2c34e0f846b55142d7e912beebadb06470fcda892d43184b426`; the 91,650,844-byte tar.xz is deliberately not committed.

The successor C0 contract is `agentic-execution-contract-aw013p1-pypi28113a7a-v2`, payload SHA-256 `f921ff7cf1401361e1bc7b5c416ad023d9cd3d9cc729201f99d2b8ad5ec3aec7`. It governs the official PyPI AppWorld wheel SHA-256 `db77f8003982502383a50fa2974983894bd1c54f64e2fd3f7e1540d5edd037eb` and installed-tree identity `28113a7a68f5d5a4c5e9ea5bce4743633916e741430cfb96b56030660707308a`.

The old `agentic-execution-contract-v1` remains valid and authoritative for existing board rows and the currently running wave-1 bench. There is no bridge or retargeting between the identities. The local live harness remains on that legacy identity until its separately tracked post-wave-1 migration; this release process did not access it.

`manifest.json` was assembled from `manifest.unsigned.json`, `signing-request.json`, and the separately produced offline-capable Ed25519 `signature.json`. The client pins the exact manifest byte digest `60b808c41da3652dea8b1cf08534cb743abdb44f4dcb5465e1bc57e549483164`. The rootfs worker wheel was built before this final client-only pin, avoiding a circular rootfs identity; both wheel digests are recorded in `artifact-digests.json`. No hardware-backed signing claim is made.

`protected-content-scan.json`, the complete CycloneDX `sbom.cyclonedx.json`, and `provenance.json` are bound by hash inside the signed manifest. `wsl-rehearsal.json` contains raw stdout/stderr bytes as base64, detected encodings, exit codes, WSL 2.6.3.0 and Windows build 26200 evidence, the intentional post-registration interruption, restart-boundary hardening checks, real AppWorld NDJSON/direct-session differential canaries, marker verification, unregister, and cleanup. The transcript contains no private-key material or personal filesystem paths.

`build-transcript.txt` is the complete captured build output. Its committed bytes equal the raw transcript hash in `artifact-digests.json`; no redaction was required after a path/private-material scan.
