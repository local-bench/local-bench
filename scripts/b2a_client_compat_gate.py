from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import venv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "b2a-client-compat.json"
HELPER = r'''
import hashlib, importlib.metadata, json, sys, tempfile
from pathlib import Path
from localbench.submissions.client import SiteCredentials, SubmissionStatusRequest, SubmissionTicketRequest, SubmissionUploadRequest, get_submission_status, request_submission_ticket, upload_submission_bundle
site = sys.argv[1]
bundle = Path(tempfile.mkdtemp()) / "bundle.json"
bundle.write_text(json.dumps({"schema_version":"localbench.result_bundle.v1","client_version":importlib.metadata.version("local-bench-ai")}), encoding="utf-8")
sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
credentials = SiteCredentials(site=site, admin_secret="compat-admin")
ticket = request_submission_ticket(SubmissionTicketRequest(credentials=credentials, raw_bundle_sha256=sha, submitter_id="compat-maintainer", declared_model_slug="compat-model"))
complete = upload_submission_bundle(SubmissionUploadRequest(bundle_path=bundle, credentials=credentials, envelope=ticket))
status = get_submission_status(SubmissionStatusRequest(credentials=credentials, ticket_id=ticket["ticket_id"]))
assert complete["status"] == "pending_verification" and status["status"] == "pending_verification"
print(json.dumps({"ticket_id": ticket["ticket_id"], "status": status["status"]}, sort_keys=True))
'''


class ContractServer(BaseHTTPRequestHandler):
    mutate_admission = False
    objects: dict[str, bytes] = {}

    def do_POST(self) -> None:  # noqa: N802
        body = self._json()
        if self.path == "/api/submissions/tickets":
            if self.mutate_admission and "community_model_group_id" not in body:
                self._send(400, {"code": "invalid_ticket_request", "error": "mutated admission break"})
                return
            sha = str(body["bundle_sha256"])
            self._send(201, {
                "accepted_suite_terms": True, "allowed_schema": "localbench.result_bundle.v1", "bundle_sha256": sha,
                "community_model_group_id": f"community-group:{'1' * 32}", "expected_suite_manifest_sha256": None,
                "expected_suite_release_id": None, "expiry": "2099-01-01T00:00:00Z", "max_upload_bytes": 67108864,
                "one_use": True, "origin": "project_anchor", "schema_version": "localbench.submission_envelope.v2",
                "submitter_id": "compat-maintainer", "ticket_id": f"ticket_{sha[:32]}", "upload_capability": f"upload_{'2' * 32}",
            })
        elif self.path == "/api/submissions/request-upload":
            sha = str(body["raw_bundle_sha256"])
            self._send(200, {"bucket": "compat", "content_sha256": sha, "expires_seconds": 3600, "method": "PUT", "r2_key": f"raw/{sha}.json", "upload_url": f"http://127.0.0.1:{self.server.server_port}/upload/{sha}", "upload_headers": {"if-none-match": "*"}})
        elif self.path.endswith("/complete"):
            self._send(200, {"status": "pending_verification", "submission_id": self.path.split("/")[-2]})
        else:
            self._send(404, {"code": "not_found"})

    def do_PUT(self) -> None:  # noqa: N802
        size = int(self.headers.get("content-length", "0"))
        payload = self.rfile.read(size)
        sha = self.path.rsplit("/", 1)[-1]
        if hashlib.sha256(payload).hexdigest() != sha or sha in self.objects:
            self._send(412, {"code": "create_only_failed"})
            return
        self.objects[sha] = payload
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/submissions/ticket_"):
            self._send(200, {"status": "pending_verification", "submission_id": self.path.rsplit("/", 1)[-1]})
        else:
            self._send(404, {"code": "not_found"})

    def log_message(self, _format: str, *args: Any) -> None:
        pass

    def _json(self) -> dict[str, Any]:
        value = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
        assert isinstance(value, dict)
        return value

    def _send(self, status: int, value: dict[str, Any]) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutate-admission", action="store_true")
    parser.add_argument("--role")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="b2a-compat-") as temp:
        temp_path = Path(temp)
        wheels = _materialize_wheels(manifest, temp_path, role=args.role)
        server = ThreadingHTTPServer(("127.0.0.1", 0), ContractServer)
        ContractServer.mutate_admission = args.mutate_admission
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            failures = 0
            for client, wheel in wheels:
                failures += 0 if _run_isolated(client, wheel, temp_path, server.server_port) else 1
        finally:
            server.shutdown()
            server.server_close()
    if args.mutate_admission:
        return 1 if failures > 0 else 0
    return 0 if failures == 0 else 1


def _materialize_wheels(manifest: dict[str, Any], root: Path, *, role: str | None) -> list[tuple[dict[str, Any], Path]]:
    result = []
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(manifest["source_date_epoch"])}
    for client in manifest["clients"]:
        if role is not None and client["role"] != role:
            continue
        if client["source"] == "build:cli":
            subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", str(ROOT / "cli"), "-w", str(root)], check=True, env=env, stdout=subprocess.DEVNULL)
        else:
            subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", f"local-bench-ai=={client['version']}", "-d", str(root)], check=True, stdout=subprocess.DEVNULL)
        wheel = root / client["filename"]
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != client["sha256"]:
            raise RuntimeError(f"wheel hash mismatch: {wheel.name}")
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
