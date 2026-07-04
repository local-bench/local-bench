"""Module entry point for python -m localbench."""

from __future__ import annotations

import sys

from localbench.cli import main


if __name__ == "__main__":
    sys.exit(main())
