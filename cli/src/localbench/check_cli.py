from __future__ import annotations

import argparse
import importlib.metadata
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from localbench.check.command import check_command


class _CommandArgs(Protocol):
    command: str


class _CheckArgs(_CommandArgs, Protocol):
    file: Path
    parent: str | None
    dry_run: bool
    smoke: bool
    manifest: Path
    out: Path | None
    resume: Path | None
    reference_bundle: Path | None
    reference_public_key: str | None
    reference_checkset_edition: str | None
    reference_run: Path | None
    allow_untrusted_code: bool


class _ChecksetArgs(_CommandArgs, Protocol):
    repo_root: Path
    output: Path
    offline_upstream: bool
    freeze: bool
    reviewed_draft_sha: str | None


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "checkset" / "check-set-v1.manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw == ["--version"]:
        print(_version())
        return 0
    parser = _parser()
    args = cast(_CommandArgs, cast(object, parser.parse_args(raw)))
    if args.command == "check":
        check_args = cast(_CheckArgs, args)
        exit_code, message = check_command(
            check_args.file,
            parent=check_args.parent,
            dry_run=check_args.dry_run,
            smoke=check_args.smoke,
            manifest=check_args.manifest,
            out=check_args.out,
            resume=check_args.resume,
            reference_bundle=check_args.reference_bundle,
            reference_public_key=check_args.reference_public_key,
            reference_checkset_edition=check_args.reference_checkset_edition,
            reference_run=check_args.reference_run,
            allow_untrusted_code=check_args.allow_untrusted_code,
        )
        print(message)
        return exit_code
    if args.command == "checkset":
        from localbench.checkset.command import build_command

        checkset_args = cast(_ChecksetArgs, args)
        exit_code, message = build_command(
            checkset_args.repo_root,
            checkset_args.output,
            offline_upstream=checkset_args.offline_upstream,
            freeze=checkset_args.freeze,
            reviewed_draft_sha=checkset_args.reviewed_draft_sha,
        )
        print(message)
        return exit_code
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localbench",
        description="Compare a local GGUF artifact with its pinned family reference.",
    )
    _ = parser.add_argument("--version", action="store_true", help="print the localbench package version")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="run the fixed local artifact comparison")
    _ = check.add_argument("file", type=Path, help="candidate GGUF file")
    _ = check.add_argument("--parent", help="explicit parent/reference lineage id")
    _ = check.add_argument("--dry-run", action="store_true", help="run the complete pipeline with deterministic fixtures")
    _ = check.add_argument("--smoke", action="store_true", help="run the pinned non-scoring GPU validation subset")
    _ = check.add_argument("--resume", type=Path, help="explicitly resume an existing run directory")
    _ = check.add_argument("--out", type=Path, help="new run directory")
    _ = check.add_argument("--manifest", type=Path, default=default_manifest_path(), help=argparse.SUPPRESS)
    _ = check.add_argument("--reference-bundle", type=Path, help="signed immutable reference-edition bundle")
    _ = check.add_argument("--reference-run", type=Path, help="complete immutable run for the signed reference")
    _ = check.add_argument("--reference-public-key", help="trusted Ed25519 reference-edition public key")
    _ = check.add_argument(
        "--allow-untrusted-code",
        action="store_true",
        help="consent to execute generated coding answers in the restricted Docker sandbox",
    )
    _ = check.add_argument("--reference-checkset-edition", help=argparse.SUPPRESS)
    checkset = subparsers.add_parser("checkset", help=argparse.SUPPRESS)
    checkset_subparsers = checkset.add_subparsers(dest="checkset_command", required=True)
    build = checkset_subparsers.add_parser("build", help=argparse.SUPPRESS)
    _ = build.add_argument("--repo-root", type=Path, default=Path.cwd())
    _ = build.add_argument("--output", type=Path, default=Path("checkset/check-set-v1.manifest.json"))
    _ = build.add_argument("--offline-upstream", action="store_true", help=argparse.SUPPRESS)
    _ = build.add_argument("--freeze", action="store_true", help=argparse.SUPPRESS)
    _ = build.add_argument("--reviewed-draft-sha", help=argparse.SUPPRESS)
    return parser


def _version() -> str:
    try:
        return importlib.metadata.version("local-bench-ai")
    except importlib.metadata.PackageNotFoundError:
        return "1.0.0.dev0"


if __name__ == "__main__":
    raise SystemExit(main())
