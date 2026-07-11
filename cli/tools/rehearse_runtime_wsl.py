"""Two-phase real-WSL C1 staging rehearsal with raw byte evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform
import subprocess
from pathlib import Path

from localbench.submissions.canon import write_json_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("register", "recover"), required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--appworld-wheel", required=True, type=Path)
    parser.add_argument("--dependency-lock", required=True, type=Path)
    parser.add_argument("--data-bundle", required=True, type=Path)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if not args.name.startswith("LocalBench-Staging-"):
        raise ValueError("rehearsal distro must use LocalBench-Staging-* name")
    transcript = _read(args.out) if args.out.exists() else {
        "schema": "localbench.wsl_runtime_rehearsal.v1",
        "machine": {"windows_version": platform.version(), "architecture": platform.machine()},
        "commands": [],
    }
    recorder = Recorder(transcript, workspace=Path(__file__).parents[2])
    recorder.run(["wsl.exe", "--version"])
    if args.phase == "register":
        listed = recorder.run(["wsl.exe", "--list", "--quiet"])
        if args.name in _decode_wsl(listed.stdout).splitlines():
            raise RuntimeError("staging name already registered")
        args.install_dir.mkdir(parents=True, exist_ok=False)
        recorder.run([
            "wsl.exe", "--import", args.name, str(args.install_dir),
            str(args.archive), "--version", "2",
        ], timeout=900)
        recorder.run(["wsl.exe", "--list", "--verbose"])
        transcript["interruption_checkpoint"] = (
            "process intentionally exited immediately after successful registration"
        )
        transcript["phase"] = "registered-interrupted"
        write_json_file(args.out, transcript)
        return 0
    if transcript.get("phase") != "registered-interrupted":
        raise RuntimeError("recover requires a completed register phase")
    manifest = _read(args.manifest)["payload"]
    runtime_id = str(manifest["runtime_id"])
    marker = recorder.run(_wsl(args.name, ["/bin/cat", "/etc/localbench-appliance-owner.json"], user="root"))
    expected_marker = {"owner": "localbench", "runtime_id": runtime_id, "schema": "localbench.appliance_owner.v1"}
    if json.loads(marker.stdout.decode("utf-8")) != expected_marker:
        raise RuntimeError("ownership marker mismatch; refusing rehearsal continuation")
    recorder.run(["wsl.exe", "--list", "--verbose"])
    appworld_wheel_target = f"/tmp/{args.appworld_wheel.name}"
    for source, target in (
        (args.appworld_wheel, appworld_wheel_target),
        (args.dependency_lock, "/tmp/appworld.lock"),
        (args.data_bundle, "/tmp/appworld-data.bundle"),
    ):
        recorder.run(
            _wsl(args.name, ["/bin/sh", "-c", f"cat > {target}; chown lbworker:lbworker {target}; chmod 0600 {target}"], user="root"),
            stdin=source.read_bytes(), timeout=300,
        )
    clean = [
        "/usr/bin/env", "-i", "HOME=/home/lbworker",
        "PATH=/opt/localbench/venv/bin:/usr/bin:/bin", "PYTHONHASHSEED=0",
        "TZ=UTC", "LC_ALL=C.UTF-8", "APPWORLD_ROOT=/home/lbworker/appworld",
    ]
    recorder.run(_wsl(args.name, [*clean, "/opt/localbench/venv/bin/pip", "install", "--require-hashes", "-r", "/tmp/appworld.lock"]), timeout=1800)
    recorder.run(_wsl(args.name, [*clean, "/opt/localbench/venv/bin/pip", "install", "--no-deps", appworld_wheel_target]), timeout=300)
    recorder.run(_wsl(args.name, [*clean, "/opt/localbench/venv/bin/appworld", "install"]), timeout=600)
    recorder.run(_wsl(args.name, [*clean, "/opt/localbench/venv/bin/python", "-c", "from pathlib import Path;from localbench.appliance.worker import _unpack_official_data;_unpack_official_data(Path('/tmp/appworld-data.bundle'))"]), timeout=600)
    recorder.run(_wsl(args.name, ["/bin/sh", "-c", "mkdir -p /run/localbench-fstab-probe; printf '%s\\n' 'tmpfs /run/localbench-fstab-probe tmpfs defaults 0 0' >> /etc/fstab"], user="root"))
    recorder.run(["wsl.exe", "--terminate", args.name])
    proof = recorder.run(_wsl(args.name, ["/bin/sh", "-c", "printf '%s\\n' \"$(id -un)\" \"$(id -gn)\"; test ! -e /mnt/c; ! command -v cmd.exe >/dev/null 2>&1; ! cmd.exe /c exit 0 >/dev/null 2>&1; ! printf '%s' \"$PATH\" | grep -Eq '(^|:)/mnt/[A-Za-z]/'; ! grep -F ' /run/localbench-fstab-probe ' /proc/self/mountinfo >/dev/null"]))
    if proof.stdout.decode().splitlines()[:2] != ["lbworker", "lbworker"]:
        raise RuntimeError("post-restart hardening identity proof failed")
    recorder.run(_wsl(args.name, ["/usr/bin/env", "-i", "HOME=/home/lbworker", "APPWORLD_ROOT=/home/lbworker/appworld", "PATH=/opt/localbench/venv/bin:/usr/bin:/bin", "PYTHONHASHSEED=0", "TZ=UTC", "LC_ALL=C.UTF-8", "/opt/localbench/bin/localbench-worker", "canary", "--full"]), timeout=900)
    handshake = recorder.run(_wsl(args.name, ["/usr/bin/env", "-i", "HOME=/home/lbworker", "PATH=/opt/localbench/venv/bin:/usr/bin:/bin", "PYTHONHASHSEED=0", "TZ=UTC", "LC_ALL=C.UTF-8", "/opt/localbench/bin/localbench-worker", "handshake", "--json"]), timeout=300)
    identity = json.loads(handshake.stdout.decode("utf-8"))
    if identity.get("critical_hashes") != manifest.get("critical_hashes"):
        raise RuntimeError("rehearsal handshake critical hashes differ from manifest")
    marker = recorder.run(_wsl(args.name, ["/bin/cat", "/etc/localbench-appliance-owner.json"], user="root"))
    if json.loads(marker.stdout.decode("utf-8")) != expected_marker:
        raise RuntimeError("ownership marker changed; refusing unregister")
    recorder.run(["wsl.exe", "--unregister", args.name], timeout=300)
    remaining = recorder.run(["wsl.exe", "--list", "--quiet"])
    if args.name in _decode_wsl(remaining.stdout).splitlines() or args.install_dir.exists():
        raise RuntimeError("staging cleanup verification failed")
    transcript["phase"] = "complete"
    transcript["result"] = "passed"
    transcript["runtime_id"] = runtime_id
    transcript["artifact_sha256"] = _sha(args.archive)
    transcript["complete_canary_after_restart"] = True
    transcript["marker_verified_before_unregister"] = True
    write_json_file(args.out, transcript)
    return 0


class Recorder:
    def __init__(self, transcript: dict[str, object], *, workspace: Path) -> None:
        self.transcript = transcript
        self.workspace = str(workspace.resolve())

    def run(self, argv: list[str], *, stdin: bytes | None = None, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(argv, input=stdin, capture_output=True, check=False, timeout=timeout)
        display = [item.replace(self.workspace, "<WORKSPACE>") for item in argv]
        entry: dict[str, object] = {
            "arguments": display, "exit_code": completed.returncode,
            "stdout_encoding": _encoding(completed.stdout),
            "stdout_base64": base64.b64encode(completed.stdout).decode("ascii"),
            "stderr_encoding": _encoding(completed.stderr),
            "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
        }
        if stdin is not None:
            entry.update(stdin_size_bytes=len(stdin), stdin_sha256=hashlib.sha256(stdin).hexdigest())
        commands = self.transcript.setdefault("commands", [])
        assert isinstance(commands, list)
        commands.append(entry)
        if completed.returncode != 0:
            raise RuntimeError(f"command failed ({completed.returncode}): {display!r}")
        return completed


def _wsl(name: str, command: list[str], *, user: str | None = None) -> list[str]:
    argv = ["wsl.exe", "--distribution", name]
    if user is not None:
        argv.extend(["--user", user])
    return [*argv, "--exec", *command]


def _encoding(raw: bytes) -> str:
    return "utf-16-le" if b"\x00" in raw[:8] else "utf-8"


def _decode_wsl(raw: bytes) -> str:
    return raw.decode(_encoding(raw), errors="strict").lstrip("\ufeff")


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("JSON object required")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
