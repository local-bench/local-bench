from __future__ import annotations

import importlib.metadata
from typing import Final

_DISTRIBUTION_NAMES: Final = ("local-bench-ai", "local-bench", "localbench")


def installed_package_version() -> str | None:
    """Return the installed localbench distribution version, or fail closed with ``None``."""
    for distribution in _DISTRIBUTION_NAMES:
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None
