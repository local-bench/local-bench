from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "b2a-client-compat.json"
HELPER = r'''
import hashlib, importlib.metadata, inspect, json, sys, tempfile
from datetime import UTC, datetime
from pathlib import Path
from localbench.submissions.client import SiteCredentials, SubmissionStatusRequest, SubmissionTicketRequest, SubmissionUploadRequest, TicketProofOfPossession, get_submission_status, request_submission_ticket, upload_submission_bundle
from localbench.submissions.crypto import sign_bytes
from localbench.submissions.keys import write_private_key
site = sys.argv[1]
root = Path(tempfile.mkdtemp())
bundle = root / "bundle.json"
bundle.write_text(json.dumps({"schema_version":"localbench.result_bundle.v1","client_version":importlib.metadata.version("local-bench-ai")}), encoding="utf-8")
sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
release_id = "suite-v1-full-exec-6axis-v1"
manifest_sha = "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468"
key_path = root / "submission-key.pem"
public_key = write_private_key(key_path, seed=bytes(range(32)))
timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
message = "\n".join(("localbench.ticket_pop.v1", sha, release_id, manifest_sha, timestamp))
pop = TicketProofOfPossession(timestamp=timestamp, signature=sign_bytes(message.encode("utf-8"), key_path), message=message)
credentials = SiteCredentials(site=site)
kwargs = dict(credentials=credentials, raw_bundle_sha256=sha, public_key=public_key, declared_model_slug="compat-model", expected_suite_release_id=release_id, expected_suite_manifest_sha256=manifest_sha, pop=pop)
if "community_model_group_id" in inspect.signature(SubmissionTicketRequest).parameters:
    kwargs["community_model_group_id"] = "community-group:" + "1" * 32
ticket = request_submission_ticket(SubmissionTicketRequest(**kwargs))
assert ticket["origin"] == "community"
complete = upload_submission_bundle(SubmissionUploadRequest(bundle_path=bundle, credentials=credentials, envelope=ticket))
status = get_submission_status(SubmissionStatusRequest(credentials=credentials, ticket_id=ticket["ticket_id"]))
assert complete["status"] == "pending_verification" and status["status"] == "pending_verification"
print(json.dumps({"ticket_id": ticket["ticket_id"], "status": status["status"]}, sort_keys=True))
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutate-admission", action="store_true")
    parser.add_argument("--role")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="b2a-compat-") as temp:
        temp_path = Path(temp)
        wheels = _materialize_wheels(manifest, temp_path, role=args.role)
        server, port = _start_worker_server(temp_path, mutate_admission=args.mutate_admission)
        try:
            failures = sum(
                0 if _run_isolated(client, wheel, temp_path, port) else 1
                for client, wheel in wheels
            )
        finally:
            (temp_path / "stop").touch()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=10)
        if server.returncode != 0:
            raise RuntimeError("Worker compatibility server failed")
    if args.mutate_admission:
        return 1 if failures > 0 else 0
    return 0 if failures == 0 else 1


def _start_worker_server(root: Path, *, mutate_admission: bool) -> tuple[subprocess.Popen[str], int]:
    port_file = root / "port"
    stop_file = root / "stop"
    env = {
        **os.environ,
        "B2A_COMPAT_SERVER": "1",
        "B2A_COMPAT_PORT_FILE": str(port_file),
        "B2A_COMPAT_STOP_FILE": str(stop_file),
        "B2A_COMPAT_MUTATE_ADMISSION": "1" if mutate_admission else "0",
    }
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is required for the Worker compatibility server")
    process = subprocess.Popen(
        [npm, "test", "--", "--run", "tests/b2a-compat-worker-server.test.ts"],
        cwd=ROOT / "web",
        env=env,
        text=True,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if port_file.exists():
            return process, int(port_file.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"Worker compatibility server exited early: {process.returncode}")
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("Worker compatibility server did not publish a port")


def _materialize_wheels(manifest: dict[str, Any], root: Path, *, role: str | None) -> list[tuple[dict[str, Any], Path]]:
    result = []
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(manifest["source_date_epoch"])}
    for client in manifest["clients"]:
        if role is not None and client["role"] != role:
            continue
        if client["source"] == "build:cli":
            rc_source = root / "rc-source"
            shutil.copytree(
                ROOT / "cli",
                rc_source,
                ignore=shutil.ignore_patterns(".venv", "build", "dist", "runs", "runtime", "__pycache__", "*.egg-info"),
            )
            pyproject = rc_source / "pyproject.toml"
            contents = pyproject.read_text(encoding="utf-8")
            if f'version = "{client["version"]}"' not in contents:
                contents = contents.replace('version = "0.3.1"', f'version = "{client["version"]}"', 1)
                pyproject.write_text(contents, encoding="utf-8")
            subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", str(rc_source), "-w", str(root)], check=True, env=env, stdout=subprocess.DEVNULL)
        else:
            subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", f"local-bench-ai=={client['version']}", "-d", str(root)], check=True, stdout=subprocess.DEVNULL)
        wheel = root / client["filename"]
        actual_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if actual_sha != client["sha256"]:
            raise RuntimeError(f"wheel hash mismatch: {wheel.name}: expected {client['sha256']}, got {actual_sha}")
        result.append((client, wheel))
    return result


def _run_isolated(client: dict[str, Any], wheel: Path, root: Path, port: int) -> bool:
    target = root / f"venv-{client['role']}"
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", str(wheel)], check=True, stdout=subprocess.DEVNULL)
    result = subprocess.run([str(python), "-c", HELPER, f"http://127.0.0.1:{port}"], text=True, capture_output=True)
    print(f"{client['role']} {client['filename']} sha256={client['sha256']} result={result.returncode}")
    if result.returncode != 0:
        print(result.stderr)
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
