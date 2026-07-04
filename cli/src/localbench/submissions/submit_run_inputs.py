from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.submissions.archive import json_object_from_bytes, unpack_bundle
from localbench.submissions.bundle import suite_release_pair
from localbench.submissions.client import raw_bundle_sha256
from localbench.submissions.crypto import load_private_key, sign_manifest_payload
from localbench.submissions.keys import Ed25519SeedError, write_private_key

# Top-level fields excluded from the signed payload — matches the server's
# run_payload_sha256 exclusion list (submission contract v2 AS-BUILT).
_UNSIGNED_TOP_LEVEL_FIELDS = ("signature", "envelope", "submission_envelope")

DEFAULT_SITE = "https://local-bench.ai"
KEY_BACKUP_LINE = "this key is your leaderboard identity — back it up."


@dataclass(frozen=True, slots=True)
class SubmitConfig:
    display_name: str | None
    site: str | None


@dataclass(frozen=True, slots=True)
class KeyIdentity:
    path: Path
    public_key: str
    generated: bool


@dataclass(frozen=True, slots=True)
class BundleInfo:
    path: Path
    sha256: str
    suite_release_id: str
    suite_manifest_sha256: str
    declared_model_slug: str | None
    inferred_line: str | None = None


@dataclass(frozen=True, slots=True)
class LocatedRun:
    path: Path
    inferred_line: str | None


class SubmitInputError(Exception):
    pass


def default_signing_key_path() -> Path:
    return Path.home() / ".localbench" / "submitter_ed25519.pem"


def submit_config_path() -> Path:
    return Path.home() / ".localbench" / "submit.json"


def read_config(path: Path) -> SubmitConfig:
    if not path.exists():
        return SubmitConfig(display_name=None, site=None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SubmitInputError(f"malformed submit config {path}: {error.msg}") from error
    if not isinstance(data, dict):
        raise SubmitInputError(f"malformed submit config {path}: expected JSON object")
    return SubmitConfig(display_name=_text(data.get("display_name")), site=_text(data.get("site")))


def write_config(path: Path, config: SubmitConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {"site": config.site or DEFAULT_SITE}
    if config.display_name is not None:
        payload["display_name"] = config.display_name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_key(path: Path | None) -> KeyIdentity:
    key_path = path.expanduser() if path is not None else default_signing_key_path()
    if not key_path.exists():
        if path is not None:
            raise SubmitInputError(f"signing key does not exist: {key_path}")
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            public_key = write_private_key(key_path)
        except (Ed25519SeedError, OSError, ValueError) as error:
            raise SubmitInputError(str(error)) from error
        return KeyIdentity(path=key_path, public_key=public_key, generated=True)
    return KeyIdentity(path=key_path, public_key=load_private_key(key_path).public_key.hex(), generated=False)


def prepare_bundle(
    *,
    run: Path | None,
    bundle: Path | None,
    suite_dir: Path | None,
    signing_key: Path,
    temp_dir: Path,
) -> BundleInfo:
    source = run or bundle
    if source is None:
        raise SubmitInputError("one of --run or --bundle is required")
    if source.is_file() and zipfile.is_zipfile(source):
        raise SubmitInputError(
            "the submission server accepts the publishable run JSON, not .lbsub.zip "
            "archives (zips are the offline verification format); pass the run JSON "
            "or its campaign directory",
        )
    if bundle is not None:
        return bundle_info(source, None)
    located = locate_run(source)
    prepared = _prepare_run_upload(
        run_path=located.path,
        suite_dir=suite_dir,
        signing_key=signing_key,
        temp_dir=temp_dir,
    )
    return bundle_info(prepared, located.inferred_line)


def _prepare_run_upload(
    *,
    run_path: Path,
    suite_dir: Path | None,
    signing_key: Path,
    temp_dir: Path,
) -> Path:
    run_record = json_object_from_bytes(run_path.read_bytes(), str(run_path))
    manifest = _object(run_record.get("manifest"))
    suite = _object(manifest.get("suite"))
    if _text(suite.get("suite_release_id")) is None or _text(suite.get("suite_manifest_sha256")) is None:
        if suite_dir is None:
            raise SubmitInputError(
                "--suite-dir is required when the run record does not carry the suite "
                "release pair (pass the cached suite dir printed by fetch-suite)",
            )
        pair = suite_release_pair(suite, suite_dir)
        if "suite_release_id" not in pair or "suite_manifest_sha256" not in pair:
            raise SubmitInputError("bundle manifest missing suite_release_id or suite_manifest_sha256")
        suite.update(pair)
        manifest["suite"] = suite
        run_record["manifest"] = manifest
    payload = {key: value for key, value in run_record.items() if key not in _UNSIGNED_TOP_LEVEL_FIELDS}
    signed: JsonObject = dict(payload)
    signed["signature"] = sign_manifest_payload(payload, signing_key)
    out = temp_dir / "submission-run.json"
    out.write_text(
        json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return out


def locate_run(path: Path) -> LocatedRun:
    if path.is_file():
        return LocatedRun(path=path, inferred_line=None)
    if not path.is_dir():
        raise SubmitInputError(f"run path does not exist: {path}")
    candidates = [candidate for candidate in (path / "localbench-run.json", path.with_suffix(".json")) if candidate.is_file()]
    if len(candidates) == 1:
        chosen = candidates[0]
        return LocatedRun(path=chosen, inferred_line=f"run       using {chosen}")
    if not candidates:
        raise SubmitInputError(f"could not find a finished run JSON under {path}")
    raise SubmitInputError(f"multiple candidate run JSON files found under {path}; pass --run <file>")


def run_model_name(path: Path) -> str:
    run = json_object_from_bytes(path.read_bytes(), str(path))
    model = _object(run.get("model"))
    return _text(model.get("name")) or _text(model.get("declared_model_id")) or "localbench-model"


def bundle_info(path: Path, inferred_line: str | None) -> BundleInfo:
    bundle_sha = raw_bundle_sha256(path)
    top: JsonObject = {}
    if not zipfile.is_zipfile(path):
        top = json_object_from_bytes(path.read_bytes(), str(path))
    manifest = bundle_manifest(path)
    suite = _object(manifest.get("suite"))
    release_id = _text(suite.get("suite_release_id"))
    manifest_sha = _text(suite.get("suite_manifest_sha256"))
    if release_id is None or manifest_sha is None:
        raise SubmitInputError("bundle manifest missing suite_release_id or suite_manifest_sha256")
    model = _object(manifest.get("model"))
    model_claim = _object(manifest.get("model_claim"))
    top_model = _object(top.get("model"))
    return BundleInfo(
        path=path,
        sha256=bundle_sha,
        suite_release_id=release_id,
        suite_manifest_sha256=manifest_sha,
        declared_model_slug=(
            _text(model.get("name"))
            or _text(model_claim.get("display_name"))
            or _text(top_model.get("name"))
            or _text(top_model.get("declared_model_id"))
        ),
        inferred_line=inferred_line,
    )


def bundle_manifest(path: Path) -> JsonObject:
    if zipfile.is_zipfile(path):
        unpacked = unpack_bundle(path)
        payload = _object(unpacked.manifest.get("payload"))
        if "suite" in payload:
            return payload
        if unpacked.run_original is not None:
            return _object(unpacked.run_original.get("manifest"))
        return payload
    return _object(json_object_from_bytes(path.read_bytes(), str(path)).get("manifest"))


def key_lines(key: KeyIdentity) -> list[str]:
    if not key.generated:
        return []
    return [f"public_key {key.public_key}", KEY_BACKUP_LINE]


def bundle_lines(bundle: BundleInfo) -> list[str]:
    return [bundle.inferred_line] if bundle.inferred_line is not None else []


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None
