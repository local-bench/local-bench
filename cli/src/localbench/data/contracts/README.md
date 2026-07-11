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
