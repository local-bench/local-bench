from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.execution_contract import (
    V5_CONTRACT_ID,
    SuccessorContractMetadata,
    extract_contract_payload,
)
from localbench.submissions.canon import (
    canonical_json_bytes,
    canonical_json_hash,
    sha256_file,
    write_json_file,
)

_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_REPO_ROOT: Final = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize the human-approved c0v5 execution contract",
    )
    parser.add_argument("--candidate-rootfs-sha256", required=True)
    parser.add_argument(
        "--differential-report",
        action="append",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--native-conformance-evidence",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument("--supersedes", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--sign", action="store_true")
    parser.add_argument("--signing-key", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    if not args.allow_dirty:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        if completed.stdout:
            parser.error("tracked git tree is dirty; pass --allow-dirty to override")
    if args.sign and args.signing_key is None:
        parser.error("--sign requires --signing-key")
    if not args.sign and args.signing_key is not None:
        parser.error("--signing-key requires --sign")
    if not _SHA256_PATTERN.fullmatch(args.candidate_rootfs_sha256):
        parser.error("--candidate-rootfs-sha256 must be 64 lowercase hex characters")

    predecessor = _load_predecessor(args.supersedes, parser)
    predecessor_payload = predecessor["payload"]
    if not isinstance(predecessor_payload, dict):
        parser.error("--supersedes must contain a payload object")
    predecessor_id = predecessor_payload.get("contract_id")
    if not isinstance(predecessor_id, str) or not predecessor_id:
        parser.error("--supersedes payload must contain a contract_id string")
    predecessor_sha256 = canonical_json_hash(predecessor_payload)
    if predecessor.get("payload_sha256") != predecessor_sha256:
        parser.error("--supersedes payload_sha256 does not match its canonical payload")
    differential_sha256 = tuple(
        sorted(sha256_file(path) for path in args.differential_report)
    )
    native_sha256 = tuple(
        sorted(sha256_file(path) for path in args.native_conformance_evidence)
    )
    line_count = len(Path(__file__).read_text(encoding="utf-8").splitlines())
    payload = extract_contract_payload(
        predecessor_payload=predecessor_payload,
        successor_metadata=SuccessorContractMetadata(
            contract_id=V5_CONTRACT_ID,
            contract_version=5,
            supersedes_contract_id=predecessor_id,
            supersedes_payload_sha256=predecessor_sha256,
            candidate_rootfs_sha256=args.candidate_rootfs_sha256,
            differential_report_sha256=differential_sha256,
            native_conformance_evidence_sha256=native_sha256,
            provenance_citation=(
                f"cli/tools/finalize_agentic_execution_contract.py:1-{line_count}"
            ),
        ),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    write_json_file(args.out / "payload.json", payload)
    payload_sha256 = canonical_json_hash(payload)
    print(f"payload_sha256={payload_sha256}")
    if args.sign:
        from localbench.scoring.agentic_exec import execution_contract
        from localbench.scoring.agentic_exec.contract_scope import (
            execution_contract_scope,
        )
        from localbench.submissions.crypto import verify_bytes

        execution_contract.load_execution_contract(
            args.supersedes,
            expected_contract_id=predecessor_id,
        )
        contract = execution_contract.signed_contract(payload, args.signing_key)
        signature = contract["signature"]
        if not isinstance(signature, dict):
            parser.error("signer returned an invalid signature object")
        key_id = str(signature.get("key_id"))
        trusted_public_key = execution_contract.CONTRACT_PUBLIC_KEYS.get(key_id)
        signature_hex = signature.get("signature")
        if (
            trusted_public_key is None
            or signature.get("public_key") != trusted_public_key
            or not isinstance(signature_hex, str)
            or not verify_bytes(
                execution_contract.CONTRACT_SIGNATURE_DOMAIN
                + canonical_json_bytes(payload),
                signature_hex,
                trusted_public_key,
            )
        ):
            parser.error("signature is not trusted by CONTRACT_PUBLIC_KEYS")
        with tempfile.TemporaryDirectory() as temporary_directory:
            self_check_path = Path(temporary_directory) / f"{V5_CONTRACT_ID}.json"
            write_json_file(self_check_path, contract)
            execution_contract.load_execution_contract(
                self_check_path,
                expected_contract_id=V5_CONTRACT_ID,
            )
            with execution_contract_scope(
                self_check_path,
                expected_contract_id=V5_CONTRACT_ID,
            ):
                execution_contract.assert_execution_contract()
        final_path = args.out / f"{V5_CONTRACT_ID}.json"
        write_json_file(final_path, contract)
        print(f"signed_contract={final_path}")
    return 0


def _load_predecessor(path: Path, parser: argparse.ArgumentParser) -> JsonObject:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read --supersedes contract: {type(exc).__name__}")
    if not isinstance(document, dict):
        parser.error("--supersedes must contain a signed contract object")
    return document


if __name__ == "__main__":
    raise SystemExit(main())
