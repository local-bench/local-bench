# Managed appliance C1/C2 maintainer notes

The runtime rootfs is a reproducible, signed maintainer artifact. AppWorld protected code and
data are not included in it. User setup downloads the exact official AppWorld wheel and encrypted
data bundle named by the signed manifest, verifies their byte hashes, and only then decrypts them
inside the user's managed VHD.

## Build

The networked build never receives a signing key. Private key material is never accepted in a
build config or written to the repository. Run the build first:

```powershell
cd cli
uv run python tools/build_agentic_runtime.py `
  --config <release-input.json> `
  --out build/runtime-release
```

It emits `manifest.unsigned.json` and `signing-request.json`. Transfer only the signing request
to an offline-capable machine, then run `tools/sign_runtime_release.py --request ...
--signing-key ... --out signature.json`. Return only `signature.json` and combine it with the
unsigned payload using `tools/assemble_runtime_release.py`. No HSM exists for this release and
the process does not claim hardware-backed key storage. Mutable rotation, cumulative revocation,
and runtime kill-switch state use the separately domain-signed trust document produced by
`tools/sign_runtime_trust.py`.

The config is release input and must pin the Ubuntu base hash, snapshot apt-index hash, exact apt
versions, worker wheel hash, hash-required dependency lock and wheelhouse, official AppWorld wheel
and encrypted-data hashes, expected installed/data tree hashes, measured peak/steady disk bytes,
and publication URLs. `cli/runtime/runtime-build-v1.schema.json` defines the required release
input. A path-independent public input lock and the complete build evidence are committed below
`cli/runtime/release-evidence/<runtime-id>/`; path-bearing local build configuration is not. The builder runs twice
inside the named existing WSL distribution and rejects
anything except byte-identical `tar.xz` output. GNU tar 1.35 metadata and xz 5.4.5 flags are fixed in
`tools/runtime_rootfs_build.sh`. It emits an unsigned canonical manifest, complete CycloneDX 1.5
inventory, provenance statement, and a recursive protected-content scan before offline signing.

The rootfs worker wheel is built before the rootfs and retains no client trust decision. After the
accepted manifest is assembled, its exact raw-byte SHA-256 is embedded in the final Windows client
wheel. This ordering avoids a circular rootfs/manifest hash while preventing a fresh client from
accepting a retargeted initial manifest.

The legacy `agentic-execution-contract-v1` remains authoritative for existing board rows and the
already-running wave-1 bench. The appliance uses the separately signed
`agentic-execution-contract-aw013p1-pypi28113a7a-v2`, anchored to the current official PyPI wheel.
This is an owner-authorized successor identity, not a bridge or rewrite of legacy evidence.

## WSL command ground truth

The 2026-07-11 maintainer probe recorded Windows build 26200 and Store WSL 2.6.3.0. Raw byte
fixtures cover every parsed command (`--version`, `--list --verbose`, and `--list --quiet`);
the real staging rehearsal records the import, distribution/user/exec, terminate, and unregister
commands. The encoded support floor is conservative: Windows 11 build 22000 and Store WSL
2.6.3.0, followed by runtime feature probes rather than version trust alone.

Microsoft documents `wsl --import <name> <location> <tar> --version 2`, `wsl --list --verbose`,
`wsl --terminate`, and the destructive semantics of `wsl --unregister` in its
[WSL basic-command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
Microsoft's [per-distribution configuration reference](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
defines `automount.enabled=false`, `mountFsTab=false`, `interop.enabled=false`,
`appendWindowsPath=false`, and `[user] default=...`. C2 still proves each effect after a terminate
and restart; configuration text alone is not accepted as evidence.

The initial Windows 11 x64 floor is build 22000. Microsoft documents that WSL2 itself is available
from older Windows builds, but this product intentionally supports Windows 11 only. The Store-WSL
floor is the lowest fully measured appliance baseline currently recorded; lowering it requires a
new recorded feature rehearsal.

## User operations

`localbench setup-agentic` prewarms and diagnoses the pinned runtime. `--list`,
`--remove <runtime-id>`, and `--prune` implement inventory and cleanup. Active removal requires
`--confirm-active`. A distro is never unregistered unless its in-distro ownership marker matches.

All runtime state, journals, caches, and VHDs live below
`%LOCALAPPDATA%\LocalBench\WSL\<runtime-id>`. OneDrive/cloud, UNC, reparse-point, removable, and
network locations are rejected. Downloads honor `HTTPS_PROXY`/`NO_PROXY`; pass `--ca-bundle` or
set `LOCALBENCH_CA_BUNDLE` for an explicit corporate CA. Automatic Windows-certificate import,
PAC discovery, and integrated-auth proxy discovery are not supported.

Agentic task-journal file contents and renames are crash-safe, but directory `fsync` is POSIX-only.
On native Windows/NTFS, process death is fully covered; a machine-wide power loss immediately after
journal creation can still lose the not-yet-referenced journal file. Journal paths hosted in
WSL/ext4 receive the full directory-`fsync` durability semantics.

Do not export or upload a provisioned VHD: it contains locally decrypted AppWorld material.
