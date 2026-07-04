from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

CLI_DIR: Final = Path(__file__).resolve().parent
ROOT: Final = CLI_DIR.parent
IMPORT_PATHS: Final = (CLI_DIR / "src", ROOT, ROOT / "web")
IMPORT_PATH_TEXTS: Final = tuple(str(path) for path in IMPORT_PATHS)

for path_text in reversed(IMPORT_PATH_TEXTS):
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

existing_pythonpath = [
    path
    for path in os.environ.get("PYTHONPATH", "").split(os.pathsep)
    if path and path not in IMPORT_PATH_TEXTS
]
os.environ["PYTHONPATH"] = os.pathsep.join((*IMPORT_PATH_TEXTS, *existing_pythonpath))
