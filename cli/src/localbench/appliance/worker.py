"""Fixed appliance worker maintenance entrypoint (handshake, provision, canaries)."""

from __future__ import annotations

import hashlib
import base64
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from localbench._types import JsonObject
from localbench.appliance.manifest import REQUIRED_CRITICAL_HASHES
from localbench.appliance.runtime_identity import AGENTIC_WORKER_PROTOCOL_VERSION
from localbench.scoring.agentic_exec.execution_contract import (
    assert_execution_contract,
    assert_packaging_correctness_gate,
    load_execution_contract,
)
from localbench.scoring.agentic_exec.task_pool import selection_recipe_sha256
from localbench.scoring.agentic_exec.wsl_worker import collect_identity
from localbench.scoring.agentic_exec.wsl_worker import _verified_appworld_tree_sha256
from localbench.submissions.canon import canonical_json_bytes

APPWORLD_ROOT = Path("/home/lbworker/appworld")
VENV = Path("/opt/localbench/venv")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["handshake", "--json"]:
        print(json.dumps(handshake(), sort_keys=True, separators=(",", ":")))
        return 0
    if args == ["canary", "--full"]:
        run_canaries()
        return 0
    if len(args) == 2 and args[0] == "provision":
        provision(_object(json.loads(args[1])))
        return 0
    print(
        "usage: localbench-worker handshake --json | canary --full | provision MANIFEST",
        file=sys.stderr,
    )
    return 2


def provision(manifest: JsonObject) -> None:
    appworld = _object(manifest["appworld"])
    version = str(appworld["version"])
    locks = _object(appworld["dependency_locks"])
    machine = platform.machine().lower()
    if machine != "x86_64":
        raise RuntimeError(
            f"unsupported AppWorld dependency-lock architecture: {machine}"
        )
    lock = _object(locks[machine])
    wheel = _object(appworld["package"])
    successor = _successor_appworld_identity()
    if str(wheel["sha256"]) != successor["official_wheel_sha256"]:
        raise RuntimeError(
            "signed manifest wheel digest differs from successor contract"
        )
    if str(appworld["installed_tree_sha256"]) != successor["installed_tree_sha256"]:
        raise RuntimeError(
            "signed manifest installed-tree digest differs from successor contract"
        )
    distribution = _object(appworld["data_distribution"])
    with tempfile.TemporaryDirectory(prefix="localbench-appworld-") as temporary:
        root = Path(temporary)
        wheel_path = root / str(wheel["filename"])
        lock_path = root / "requirements.lock"
        data_bundle = root / str(distribution["filename"])
        _download(
            str(wheel["url"]),
            wheel_path,
            str(wheel["sha256"]),
            int(wheel["size_bytes"]),
        )
        _download(
            str(lock["url"]), lock_path, str(lock["sha256"]), int(lock["size_bytes"])
        )
        _download(
            str(distribution["url"]),
            data_bundle,
            str(distribution["sha256"]),
            int(distribution["size_bytes"]),
        )
        subprocess.run(
            [
                str(VENV / "bin/python"),
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "-r",
                str(lock_path),
            ],
            check=True,
            env=_clean_env(),
        )
        wheel_install = subprocess.run(
            [
                str(VENV / "bin/python"),
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-deps",
                str(wheel_path),
            ],
            check=True,
            env=_clean_env(),
            capture_output=True,
            text=True,
        )
        print(
            json.dumps(
                {
                    "schema": "localbench.appworld_wheel_install_evidence.v1",
                    "wheel_path": str(wheel_path),
                    "wheel_sha256": _file_sha(wheel_path),
                    "pip_stdout": wheel_install.stdout,
                    "pip_stderr": wheel_install.stderr,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        env = _clean_env()
        env["APPWORLD_ROOT"] = str(APPWORLD_ROOT)
        subprocess.run([str(VENV / "bin/appworld"), "install"], check=True, env=env)
        _unpack_official_data(data_bundle)
    if _distribution_version("appworld") != version:
        raise RuntimeError("installed AppWorld version differs from signed manifest")
    expected_installed = str(appworld["installed_tree_sha256"])
    expected_data = str(appworld["data_tree_sha256"])
    installed_tree = _verified_appworld_tree_sha256()
    if installed_tree != expected_installed or installed_tree != successor["installed_tree_sha256"]:
        raise RuntimeError("AppWorld installed-tree digest mismatch")
    if _tree_sha(APPWORLD_ROOT / "data") != expected_data:
        raise RuntimeError("AppWorld data-tree digest mismatch")


def handshake() -> JsonObject:
    from localbench.scoring.agentic_exec import task_pool
    from localbench.scoring.agentic_exec.execution_contract import contract_task_ids

    contract_sha = assert_execution_contract()
    assert_packaging_correctness_gate()
    measured_identity = collect_identity(str(APPWORLD_ROOT))
    task_ids = contract_task_ids()
    semantic_contents = task_pool.load_semantic_task_contents(
        task_ids, root=APPWORLD_ROOT
    )
    critical: JsonObject = {
        "worker_entrypoint_sha256": _file_sha(
            Path("/opt/localbench/bin/localbench-worker")
        ),
        "worker_wheel_tree_sha256": _localbench_record_tree_sha256(),
        "bubblewrap_sha256": _file_sha(Path("/usr/bin/bwrap")),
        "appworld_installed_tree_sha256": _verified_appworld_tree_sha256(),
        "appworld_data_tree_sha256": _tree_sha(APPWORLD_ROOT / "data"),
        "wsl_conf_sha256": _file_sha(Path("/etc/wsl.conf")),
    }
    if tuple(critical) != REQUIRED_CRITICAL_HASHES:
        raise RuntimeError("critical hash enumeration drift")
    return {
        "runtime_id": _owner_marker()["runtime_id"],
        "protocol_version": AGENTIC_WORKER_PROTOCOL_VERSION,
        "python_version": measured_identity["python_version"],
        "bubblewrap_version": measured_identity["bwrap_version"],
        "appworld_package_sha256": measured_identity["appworld_package_sha256"],
        "appworld_data_sha256": critical["appworld_data_tree_sha256"],
        "execution_contract_sha256": contract_sha,
        "critical_hashes": critical,
        "ordered_task_ids_sha256": task_pool.ordered_task_ids_sha256(task_ids),
        "selection_recipe_sha256": selection_recipe_sha256(
            split="test_normal", seed=20260624, selection_version="v1"
        ),
        "semantic_task_sha256": task_pool.semantic_task_sha256(semantic_contents),
        "uid": _name("-un"),
        "gid": _name("-gn"),
        "mnt_c_absent": not Path("/mnt/c").exists(),
        "interop_blocked": shutil.which("cmd.exe") is None,
        "windows_path_absent": not any(
            part.startswith("/mnt/") for part in os.environ.get("PATH", "").split(":")
        ),
    }


def run_canaries() -> None:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Python canary failed")
    __import__("appworld")
    if shutil.which("bwrap") != "/usr/bin/bwrap":
        raise RuntimeError("bubblewrap canary failed")
    if Path("/mnt/c").exists() or shutil.which("cmd.exe") is not None:
        raise RuntimeError("Windows isolation canary failed")
    if os.geteuid() == 0 or shutil.which("sudo") is not None or _can_set_root():
        raise RuntimeError("privilege canary failed")
    if shutil.which("mount") is None:
        raise RuntimeError("mount negative-canary prerequisite missing")
    with tempfile.TemporaryDirectory() as target:
        mount = subprocess.run(
            ["mount", "-t", "drvfs", "C:", target], capture_output=True
        )
        if mount.returncode == 0:
            raise RuntimeError("DrvFs negative canary failed")
    listening_before = _listening_sockets()
    _run_real_ndjson_canary()
    if not _listening_sockets().issubset(listening_before):
        raise RuntimeError("listening-socket negative canary failed")
    handshake()


def _run_real_ndjson_canary() -> None:
    """Exercise production framing, worker session, AppWorldSandbox, and generated code."""
    from localbench.scoring.agentic_exec.execution_contract import contract_task_ids
    from localbench.scoring.agentic_exec.wsl_worker import WorkerSession

    env = _clean_env()
    env["APPWORLD_ROOT"] = str(APPWORLD_ROOT)
    process = subprocess.Popen(
        [str(VENV / "bin/python"), "-m", "localbench.scoring.agentic_exec.wsl_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert process.stdin is not None and process.stdout is not None
    requests = [
        {"op": "hello"},
        {"op": "open_task", "task_id": contract_task_ids()[0]},
        {"op": "run_block", "code": "print('generated-code-ok')"},
        {"op": "run_block", "code": "import socket\nsocket.create_connection(('1.1.1.1',53),0.2)\nprint('NETWORK-ESCAPE')"},
        {"op": "run_block", "code": f"print(open({str(APPWORLD_ROOT / 'data')!r}).read(1))"},
        {"op": "close"},
    ]
    replies = []
    for request in requests:
        process.stdin.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr = process.communicate(timeout=30)[1]
            raise RuntimeError(
                "NDJSON worker exited before canary response: "
                + stderr.decode(errors="replace")[-1000:]
            )
        replies.append(json.loads(line))
    stderr = process.communicate(timeout=30)[1]
    if process.returncode != 0 or any(reply.get("kind") != "ok" for reply in replies):
        raise RuntimeError(f"NDJSON worker canary failed: {stderr.decode(errors='replace')[-1000:]}")
    generated, network, ground_truth = replies[2:5]
    if str(generated.get("stdout")) != "generated-code-ok\n" or generated.get("error") is not None:
        raise RuntimeError("production generated-code canary failed")
    if network.get("error") is None or "NETWORK-ESCAPE" in str(network.get("stdout")):
        raise RuntimeError("production generated-code network canary failed")
    if ground_truth.get("error") is None or ground_truth.get("stdout"):
        raise RuntimeError("production ground-truth path canary failed")
    direct = WorkerSession()
    try:
        direct.open_task(contract_task_ids()[0])
        direct_replies = [direct.run_block(str(item["code"])) for item in requests[2:5]]
    finally:
        direct.close()
    if direct_replies != replies[2:5]:
        raise RuntimeError("direct-session versus NDJSON packaging differential failed")


def _download(url: str, path: Path, expected_sha: str, maximum: int) -> None:
    from urllib.request import urlopen

    with urlopen(url, timeout=120) as response, path.open("wb") as output:  # noqa: S310 - signed URL/hash
        if response.geturl() != url:
            raise RuntimeError("download redirect is forbidden")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > maximum:
                raise RuntimeError("download exceeds signed size")
            output.write(chunk)
    if total != maximum or _file_sha(path) != expected_sha:
        raise RuntimeError("download digest/size mismatch")


def _unpack_official_data(bundle: Path) -> None:
    from appworld.common.constants import PASSWORD, SALT
    from appworld.common.utils import unpack_bundle

    if APPWORLD_ROOT.exists():
        shutil.rmtree(APPWORLD_ROOT)
    APPWORLD_ROOT.mkdir(parents=True)
    unpack_bundle(
        bundle_file_path=str(bundle),
        base_directory=str(APPWORLD_ROOT),
        password=PASSWORD,
        salt=SALT,
    )


def _clean_env() -> dict[str, str]:
    result = {
        "HOME": "/home/lbworker",
        "PATH": f"{VENV}/bin:/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
    }
    for key in ("HTTPS_PROXY", "NO_PROXY", "https_proxy", "no_proxy", "SSL_CERT_FILE"):
        if value := os.environ.get(key):
            result[key] = value
    return result


def _successor_appworld_identity() -> dict[str, str]:
    payload = _object(load_execution_contract()["payload"])
    lineage = _object(payload["identity_lineage"])
    identity = _object(payload["appworld_identity"])
    return {
        "official_wheel_sha256": str(lineage["official_wheel_sha256"]),
        "installed_tree_sha256": str(identity["appworld_package_sha256"]),
    }


def _tree_sha(root: Path) -> str:
    if not root.is_dir():
        raise RuntimeError(f"tree missing: {root}")
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append([relative, "symlink", os.readlink(path)])
        elif path.is_file():
            entries.append([relative, "file", _file_sha(path), path.stat().st_size])
        elif path.is_dir():
            entries.append([relative, "dir"])
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution_version(name: str) -> str:
    import importlib.metadata

    return importlib.metadata.version(name)


def _distribution_root(name: str) -> Path:
    import importlib.metadata

    distribution = importlib.metadata.distribution(name)
    return Path(distribution.locate_file(""))


def _appworld_package_root() -> Path:
    return _distribution_root("appworld") / "appworld"


def _localbench_dist_info() -> Path:
    import importlib.metadata

    dist = importlib.metadata.distribution("local-bench-ai")
    for file in dist.files or ():
        if file.parts and file.parts[0].endswith(".dist-info"):
            return Path(dist.locate_file(file.parts[0]))
    raise RuntimeError("localbench dist-info missing")


def _localbench_record_tree_sha256() -> str:
    """Verify every installed wheel file against RECORD and hash the full set."""
    import importlib.metadata

    dist = importlib.metadata.distribution("local-bench-ai")
    files = list(dist.files or ())
    record_item = next(
        (item for item in files if item.parts and item.parts[-1] == "RECORD"), None
    )
    if record_item is None:
        raise RuntimeError("localbench RECORD missing")
    record = Path(dist.locate_file(record_item))
    entries: list[list[object]] = []
    with record.open(newline="", encoding="utf-8") as stream:
        for relative, recorded_hash, recorded_size in csv.reader(stream):
            normalized = relative.replace("\\", "/")
            if normalized.endswith((".pyc", ".pyo")) or "/__pycache__/" in normalized:
                continue
            path = Path(dist.locate_file(relative))
            if not path.is_file():
                raise RuntimeError(f"localbench installed file missing: {relative}")
            digest = hashlib.sha256(path.read_bytes()).digest()
            size = path.stat().st_size
            if recorded_hash:
                algorithm, encoded = recorded_hash.split("=", 1)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                if algorithm != "sha256" or digest != expected:
                    raise RuntimeError(f"localbench RECORD hash mismatch: {relative}")
            if recorded_size and size != int(recorded_size):
                raise RuntimeError(f"localbench RECORD size mismatch: {relative}")
            entries.append([normalized, digest.hex(), size])
    entries.sort()
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def _owner_marker() -> JsonObject:
    return _object(
        json.loads(
            Path("/etc/localbench-appliance-owner.json").read_text(encoding="utf-8")
        )
    )


def _name(flag: str) -> str:
    return subprocess.check_output(["id", flag], text=True).strip()


def _listening_sockets() -> frozenset[tuple[str, str]]:
    sockets: set[tuple[str, str]] = set()
    for filename in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in Path(filename).read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A":
                sockets.add((fields[1], fields[7]))
    return frozenset(sockets)


def _can_set_root() -> bool:
    try:
        os.setuid(0)
    except PermissionError:
        return False
    return True


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("JSON object required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
