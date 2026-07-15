from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import venv
import zipfile
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
    parser.add_argument("--verify-rc-rebuild", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not args.mutate_admission and not args.verify_rc_rebuild:
        _assert_repo_source_is_current(manifest, ROOT)
    with tempfile.TemporaryDirectory(prefix="b2a-compat-") as temp:
        temp_path = Path(temp)
        if args.verify_rc_rebuild:
            wheels = _materialize_wheels(manifest, temp_path, role="rc_n")
            _client, wheel = wheels[0]
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            print(f"rc_rebuild {wheel.name} sha256={digest}")
            return 0
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
        # The negative gate succeeds only by returning non-zero when BOTH N and N-1
        # independently reject the mutated Worker admission contract.
        return 1 if failures == len(wheels) and len(wheels) == 2 else 0
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
            _build_rc_wheel(manifest, client, root, env)
        else:
            subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", f"local-bench-ai=={client['version']}", "-d", str(root)], check=True, stdout=subprocess.DEVNULL)
        wheel = root / client["filename"]
        actual_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if actual_sha != client["sha256"]:
            raise RuntimeError(f"wheel hash mismatch: {wheel.name}: expected {client['sha256']}, got {actual_sha}")
        result.append((client, wheel))
    return result


def _build_rc_wheel(
    manifest: dict[str, Any],
    client: dict[str, Any],
    root: Path,
    env: dict[str, str],
) -> None:
    provenance = manifest.get("rc_build")
    if not isinstance(provenance, dict):
        raise RuntimeError("compatibility manifest is missing rc_build provenance")
    if provenance.get("wheel_sha256") != client.get("sha256"):
        raise RuntimeError("rc_build wheel hash does not match the RC client pin")
    if str(provenance.get("source_date_epoch")) != env.get("SOURCE_DATE_EPOCH"):
        raise RuntimeError("rc_build SOURCE_DATE_EPOCH does not match the build environment")
    source_commit = str(provenance["source_commit"])
    source_tree = str(provenance["source_tree"])
    if _git_output("rev-parse", f"{source_commit}^{{commit}}") != source_commit:
        raise RuntimeError("rc_build source_commit is not the named clean Git object")
    if _git_output("rev-parse", f"{source_commit}:cli") != source_tree:
        raise RuntimeError("rc_build source_tree does not match source_commit:cli")

    archive = subprocess.run(
        ["git", "archive", "--format=zip", source_commit, "cli"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    source_root = root / "rc-source"
    with zipfile.ZipFile(io.BytesIO(archive)) as source_zip:
        source_zip.extractall(source_root)
    pyproject = source_root / "cli" / "pyproject.toml"
    contents = pyproject.read_text(encoding="utf-8")
    released_version = f'version = "{client["version"]}"'
    if released_version not in contents:
        original_version = 'version = "0.3.1"'
        if contents.count(original_version) != 1:
            raise RuntimeError("clean rc source has an unexpected project version")
        contents = contents.replace(original_version, released_version, 1)
        pyproject.write_text(contents, encoding="utf-8")
    _assert_build_toolchain(pyproject, provenance)

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required for the reproducible RC wheel build")
    build_env = {
        **env,
        "UV_OFFLINE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    result = subprocess.run(
        [
            uv,
            "build",
            "--offline",
            "--wheel",
            "--no-build-logs",
            "--no-progress",
            "--python",
            sys.executable,
            str(source_root / "cli"),
            "--out-dir",
            str(root),
        ],
        cwd=ROOT,
        env=build_env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("reproducible RC wheel build failed:\n" + result.stdout + result.stderr)


def _assert_build_toolchain(pyproject: Path, provenance: dict[str, Any]) -> None:
    tools = provenance.get("tool_versions")
    if not isinstance(tools, dict):
        raise RuntimeError("rc_build tool_versions must be an object")
    python_version = f"{platform.python_implementation()} {platform.python_version()}"
    if python_version != tools.get("python"):
        raise RuntimeError(f"RC wheel build requires {tools.get('python')}, got {python_version}")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required for the reproducible RC wheel build")
    uv_version = subprocess.run(
        [uv, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()[1]
    if uv_version != tools.get("uv"):
        raise RuntimeError(f"RC wheel build requires uv {tools.get('uv')}, got {uv_version}")
    build_requires = tomllib.loads(pyproject.read_text(encoding="utf-8"))["build-system"]["requires"]
    expected = [f"setuptools=={tools['setuptools']}", f"wheel=={tools['wheel']}"]
    if build_requires != expected:
        raise RuntimeError(f"RC wheel backend pins do not match provenance: {build_requires!r}")


def _assert_repo_source_is_current(manifest: dict[str, Any], repo: Path) -> None:
    provenance = manifest.get("rc_build")
    if not isinstance(provenance, dict):
        raise RuntimeError("compatibility manifest is missing rc_build provenance")
    source_commit = str(provenance.get("source_commit"))
    repo_head = _git_output_at(repo, "rev-parse", "HEAD")
    if source_commit != repo_head:
        raise RuntimeError(
            "rc_build source_commit does not match repository HEAD: "
            f"expected {repo_head}, got {source_commit}"
        )
    tracked_status = _git_output_at(repo, "status", "--short", "--untracked-files=no")
    if tracked_status:
        raise RuntimeError(
            "compatibility gate requires a clean tracked tree; tracked changes:\n"
            f"{tracked_status}"
        )


def _git_output(*args: str) -> str:
    return _git_output_at(ROOT, *args)


def _git_output_at(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
