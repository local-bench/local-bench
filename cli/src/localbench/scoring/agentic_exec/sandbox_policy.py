from __future__ import annotations


def mandatory_bubblewrap_isolation(hostname: str) -> tuple[str, ...]:
    return (
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--hostname",
        hostname,
    )


def provisioning_bubblewrap_isolation(hostname: str) -> tuple[str, ...]:
    return (
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--hostname",
        hostname,
    )
