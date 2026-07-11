# Managed appliance C1/C2 maintainer notes

The runtime rootfs is a reproducible, signed maintainer artifact. AppWorld protected code and
data are not included in it. User setup downloads the exact official AppWorld wheel and encrypted
data bundle named by the signed manifest, verifies their byte hashes, and only then decrypts them
inside the user's managed VHD.

## Build

Set `LOCALBENCH_RUNTIME_ROOT_SIGNING_KEY` to the offline Ed25519 runtime-root PEM path. Private key
material is never accepted in a build config or written to the repository. Then run:

```powershell
cd cli
uv run python tools/build_agentic_runtime.py `
  --config <release-input.json> `
  --out build/runtime-release
```

The config is release input and must pin the Ubuntu base hash, snapshot apt-index hash, exact apt
versions, worker wheel hash, hash-required dependency lock and wheelhouse, official AppWorld wheel
and encrypted-data hashes, expected installed/data tree hashes, measured peak/steady disk bytes,
and publication URLs. `cli/runtime/runtime-build-v1.schema.json` defines the required release
input; a path-bearing maintainer config is deliberately not committed. The builder runs twice
inside the named existing WSL distribution and rejects
anything except byte-identical `tar.xz` output. GNU tar 1.35 metadata and xz 5.4.5 flags are fixed in
`tools/runtime_rootfs_build.sh`. It emits the signed canonical manifest, SPDX inventory, provenance
statement, and runs the protected-content path scan before signing.

## WSL command ground truth

The 2026-07-11 maintainer probe recorded Windows build 26200 and Store WSL 2.6.3.0. The binary's
own help exposed every flag used by the provisioner: `--version`, `--import ... --version 2`,
`--list --verbose`, `--list --quiet`, `--distribution`, `--user`, `--exec`, `--terminate`, and
`--unregister`. The encoded support floor is conservative: Windows 11 build 22000 and Store WSL
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

Do not export or upload a provisioned VHD: it contains locally decrypted AppWorld material.
