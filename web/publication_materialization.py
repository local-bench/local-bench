from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from publication_export import PublicationExportError, canonical_bytes


def publication_tree_digest(out_dir: Path, staged_community: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted(item for item in out_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(out_dir)
        if relative.parts and (relative.parts[0] == "community" or relative.parts[0].startswith(".community-")):
            continue
        entries.append({"path": relative.as_posix(), "sha256": _digest(path.read_bytes())})
    for path in sorted(item for item in staged_community.rglob("*") if item.is_file()):
        relative = path.relative_to(staged_community).as_posix()
        if relative != "publication-build.json":
            entries.append({"path": f"community/{relative}", "sha256": _digest(path.read_bytes())})
    return _digest(canonical_bytes(sorted(entries, key=lambda entry: entry["path"])))


def replace_community_tree(staged_community: Path, community_dir: Path) -> None:
    backup = community_dir.with_name(f".community-backup-{uuid4().hex}")
    had_community = community_dir.exists()
    if had_community:
        community_dir.rename(backup)
    try:
        staged_community.rename(community_dir)
    except OSError as error:
        if had_community:
            backup.rename(community_dir)
        raise PublicationExportError("failed to install staged community tree") from error
    if not had_community:
        return
    try:
        shutil.rmtree(backup)
    except OSError as error:
        community_dir.rename(staged_community)
        backup.rename(community_dir)
        raise PublicationExportError("failed to retire prior community tree") from error


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
