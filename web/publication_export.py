from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class PublicationExportError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def export_publication_bundle(base_url: str, admin_secret: str, snapshot_id: str, out_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cursor: int | None = 0
    header: dict[str, Any] | None = None
    while cursor is not None:
        query = urllib.parse.urlencode({"snapshot_id": snapshot_id, "cursor": cursor})
        page = _get_json(f"{base_url.rstrip('/')}/api/admin/publication-snapshot?{query}", admin_secret)
        if header is None:
            header = {key: page[key] for key in (
                "snapshot_id", "publication_revision", "snapshot_digest", "total_count",
                "created_at", "activated_at", "publication_control",
            )}
        elif page.get("publication_control") != header["publication_control"]:
            raise PublicationExportError("publication control changed during export")
        rows.extend(_objects(page.get("rows")))
        next_cursor = page.get("next_cursor")
        cursor = next_cursor if isinstance(next_cursor, int) else None
    if header is None or len(rows) != header["total_count"]:
        raise PublicationExportError("snapshot truncation: exported count does not match total_count")
    if _sha256(canonical_bytes(rows)) != header["snapshot_digest"]:
        raise PublicationExportError("snapshot digest mismatch")
    control = _publication_control(header["publication_control"])
    if control["active_snapshot_id"] != header["snapshot_id"]:
        raise PublicationExportError("bundle snapshot is not active")
    if control["publication_revision"] != header["publication_revision"]:
        raise PublicationExportError("active publication revision mismatch")
    if not isinstance(header["activated_at"], str) or not header["activated_at"]:
        raise PublicationExportError("active snapshot is not completed and activated")
    out_dir.mkdir(parents=True, exist_ok=True)
    projections_dir = out_dir / "projections"
    projections_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        digest = _text(row, "projection_object_sha256")
        query = urllib.parse.urlencode({"sha256": digest})
        payload = _get_bytes(f"{base_url.rstrip('/')}/api/admin/publication-projection?{query}", admin_secret)
        if _sha256(payload) != digest:
            raise PublicationExportError("projection object digest mismatch")
        (projections_dir / f"{digest}.json").write_bytes(payload)
    snapshot = {**header, "rows": rows}
    (out_dir / "snapshot.json").write_bytes(canonical_bytes(snapshot))
    (out_dir / "export-metadata.json").write_bytes(canonical_bytes({
        "exporter": "web/publication_export.py",
        "schema_version": "localbench.publication_export.v1",
        "snapshot_digest": header["snapshot_digest"],
        "snapshot_id": header["snapshot_id"],
    }))
    return snapshot


def fetch_live_publication_control(base_url: str, admin_secret: str, snapshot_id: str) -> dict[str, Any]:
    """Re-read D1 control at build time; bundle-captured control is not authoritative."""
    query = urllib.parse.urlencode({"snapshot_id": snapshot_id, "cursor": 0})
    page = _get_json(f"{base_url.rstrip('/')}/api/admin/publication-snapshot?{query}", admin_secret)
    return _publication_control(page.get("publication_control"))


def _get_json(url: str, secret: str) -> dict[str, Any]:
    value = json.loads(_get_bytes(url, secret))
    if not isinstance(value, dict):
        raise PublicationExportError("snapshot endpoint did not return an object")
    return value


def _get_bytes(url: str, secret: str) -> bytes:
    request = urllib.request.Request(url, headers={"x-localbench-admin-secret": secret})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - operator-selected deployment URL
        return response.read()


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PublicationExportError("snapshot rows must be objects")
    return list(value)


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise PublicationExportError(f"{key} must be a string")
    return item


def _publication_control(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PublicationExportError("publication_control must be an object")
    if value.get("active_snapshot_id") is not None and not isinstance(value.get("active_snapshot_id"), str):
        raise PublicationExportError("publication_control.active_snapshot_id must be a string or null")
    if not isinstance(value.get("publication_revision"), int):
        raise PublicationExportError("publication_control.publication_revision must be an integer")
    suppressed = value.get("suppressed_submission_ids")
    if not isinstance(suppressed, list) or not all(isinstance(item, str) for item in suppressed):
        raise PublicationExportError("publication_control.suppressed_submission_ids must be strings")
    return value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
