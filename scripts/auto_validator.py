from __future__ import annotations

import argparse
import sys
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from auto_validator_core import AutoValidator
from auto_validator_model import (
    ApiError,
    Config,
    ConfigurationError,
    ConflictError,
    backoff_seconds,
    guard_tripped,
    map_rejection,
    scrub_text,
    sort_fifo,
)
from auto_validator_state import AlreadyRunningError, PidLock

__all__ = [
    "AlreadyRunningError",
    "ApiError",
    "AutoValidator",
    "Config",
    "ConflictError",
    "PidLock",
    "backoff_seconds",
    "guard_tripped",
    "map_rejection",
    "scrub_text",
    "sort_fifo",
]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FIFO publish-then-moderate auto-validator")
    parser.add_argument("--site", required=True)
    parser.add_argument("--suite-dir", type=Path)
    parser.add_argument("--suite-cache-root", type=Path)
    parser.add_argument("--validator-secret-file", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validator-commit")
    parser.add_argument("--coding-pass", action="store_true")
    parser.add_argument("--coding-image")
    parser.add_argument("--receipt-signing-key", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.coding_pass and args.suite_dir is None:
        raise ConfigurationError("--coding-pass requires an explicit --suite-dir")
    secret = args.validator_secret_file.read_text(encoding="utf-8").strip()
    if not secret:
        raise ConfigurationError("validator secret file is empty")
    root = Path.home() / ".localbench" / "auto-validator"
    suite_cache_root = args.suite_cache_root or (Path.home() / ".cache" / "localbench" / "suites")
    config = Config(
        site=args.site,
        suite_dir=args.suite_dir,
        suite_cache_root=suite_cache_root,
        validator_secret=secret,
        root_dir=root,
        work_dir=args.work_dir,
        dry_run=args.dry_run,
        validator_commit=args.validator_commit,
        coding_image=args.coding_image,
        receipt_signing_key=args.receipt_signing_key,
    )
    daemon = AutoValidator(config)
    lock = PidLock(config.lock_file, log=daemon.log)
    try:
        with lock:
            while not daemon.reconcile_intents():
                if args.once or daemon.consecutive_api_failures >= 5:
                    return 1
                time.sleep(backoff_seconds(daemon.consecutive_api_failures))
            if args.coding_pass:
                return 0 if daemon.run_coding_pass() == "ok" else 2
            while True:
                outcome = daemon.run_cycle()
                if outcome == "stop":
                    return 1
                if args.once:
                    return 0 if outcome in {"ok", "guarded"} else 1
                delay = backoff_seconds(daemon.consecutive_api_failures) if outcome == "retry" else args.interval
                time.sleep(delay)
    except AlreadyRunningError as error:
        daemon.log(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
