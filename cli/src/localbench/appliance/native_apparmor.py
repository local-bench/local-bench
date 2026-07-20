from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from localbench.appliance.provisioner import ProvisioningError

_APPARMOR_ENABLED_PATH: Final = Path("/sys/module/apparmor/parameters/enabled")
_APPARMOR_USERNS_RESTRICTION_PATH: Final = Path(
    "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"
)


def classify_userns_denial(
    rootfs: Path, expected_bwrap_sha256: str, failure: str
) -> ProvisioningError | None:
    if "setting up uid map" not in failure or "Permission denied" not in failure:
        return None
    bwrap = (rootfs / "usr/bin/bwrap").resolve()
    try:
        apparmor_enabled = _APPARMOR_ENABLED_PATH.read_bytes().strip().upper() == b"Y"
        userns_restricted = (
            _APPARMOR_USERNS_RESTRICTION_PATH.read_bytes().strip() == b"1"
        )
        observed_bwrap_sha256 = hashlib.sha256(bwrap.read_bytes()).hexdigest()
    except OSError:
        return None
    if (
        not apparmor_enabled
        or not userns_restricted
        or observed_bwrap_sha256 != expected_bwrap_sha256
    ):
        return None
    return ProvisioningError(
        "host_userns_blocked_by_apparmor",
        "Ubuntu AppArmor blocked LocalBench's bundled bubblewrap from creating an "
        "unprivileged user namespace",
        "\nObserved:\n"
        "- AppArmor enabled\n"
        "- kernel.apparmor_restrict_unprivileged_userns=1\n"
        f"- bundled bwrap: {bwrap}\n"
        f"- bundled bwrap SHA-256: {expected_bwrap_sha256}\n"
        "- failure: setting up uid map: Permission denied\n"
        "LocalBench made no system changes.\n"
        "Setting the following sysctl to 0 permits unprivileged user namespaces "
        "system-wide\n"
        "while it remains disabled. This affects processes other than LocalBench "
        "and weakens a\n"
        "host security restriction. Prefer running LocalBench in a disposable or "
        "dedicated VM,\n"
        "or consult the machine administrator.\n"
        "Keep the setting at 0 during both setup and benchmark execution, then "
        "restore it:\n"
        "    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0\n"
        "    # run localbench setup-agentic and the benchmark\n"
        "    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=1\n"
        "Do not run LocalBench as root, disable AppArmor, or persist this setting "
        "unless you\n"
        "understand and accept the system-wide effect.\n"
        "This release does not install an AppArmor exception automatically because "
        "the bundled\n"
        "executable is materialized under a user-owned path; granting that path "
        "additional\n"
        "permission would not safely pin the permission to the signed executable.",
    )
