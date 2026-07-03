"""TRUSTED env-host process: owns the real AppWorld ``world`` behind a narrow unix-socket RPC.

This is the ONLY process that imports/initialises AppWorld. That is mandatory for two reasons:

  1. AppWorld init has GLOBAL host side-effects (``SafetyGuard.__init__`` rebinds
     ``builtins.SystemExit = Exception`` process-wide); isolating it here keeps that pollution
     out of the harness/scorer.
  2. The real ``world`` holds the data, the live ``requester``/``TestClient``, the task DBs, the
     ground truth and the evaluator. None of those may ever reach the untrusted runner, so they
     live only on this side of the boundary and are NEVER serialised across the socket.

The runner socket surface is exactly three opcodes: ``call_api``, ``api_docs``, ``ping``.
Finalization is accepted only on the trusted stdin control channel from the orchestrator.
There is NO generic code-exec, NO ``world`` passthrough, NO ``requester`` exposure, NO filesystem
op. Every inbound field is treated as hostile and validated before use.

Run as a subprocess (in the WSL appworld venv with APPWORLD_ROOT set)::

    python -m localbench.scoring.agentic_exec.env_host <task_id> <socket_path> [experiment_name]

It writes a single line ``READY\\n`` to stdout once the world is constructed and the socket is
listening, so the parent (the sandbox orchestrator) can synchronise without polling.
"""

from __future__ import annotations

import ast
import json
import os
import queue
import socket
import sys
import threading
import warnings
from typing import Any, TextIO

from localbench.scoring.agentic_exec.sandbox_protocol import (
    KIND_API_ERROR,
    KIND_OK,
    KIND_PROTOCOL_ERROR,
    OP_API_DOCS,
    OP_CALL_API,
    OP_FINALIZE,
    OP_PING,
    FrameReader,
    send_message,
)

warnings.filterwarnings("ignore")  # silence pydantic-v1 / sqlmodel deprecation noise

# The collateral-damage requirement string AppWorld emits when the agent mutated state it
# should not have. Used by the eval-seam fix to derive collateral_damage from the failures list.
_COLLATERAL_REQUIREMENT = "assert no model changes."


class _RealEnvHost:
    """Owns a single real ``AppWorld`` task world and serves the narrow RPC over one socket."""

    def __init__(self, task_id: str, experiment_name: str) -> None:
        # Imported lazily and ONLY here so AppWorld's global monkeypatches never touch the harness.
        from appworld import AppWorld  # noqa: PLC0415 — deliberate: confine the import to the host.

        self._task_id = task_id
        self._world = AppWorld(task_id=task_id, experiment_name=experiment_name)
        self._finalized = False
        # Public app whitelist for call_api validation — the trusted-side WALL. In-process proxy
        # name-filtering is defeatable (apis._rpc slot / closures / object-graph), so app/api
        # allow-listing MUST be enforced here, not in the runner.
        self._valid_apps = self._discover_public_apps()

    def _discover_public_apps(self) -> frozenset[str]:
        """Public app namespaces on the real ``apis``, derived live (tracks the AppWorld version).

        Empty -> fall back to underscore-prefix + forbidden-name rejection only (never reject
        everything, which would break legitimate task-solving).
        """
        try:
            raw = self._world.execute(
                "print(sorted(a for a in dir(apis) if not a.startswith('_')))"
            )
            apps = ast.literal_eval(raw.strip()) if raw and raw.strip() else []
            return frozenset(a for a in apps if isinstance(a, str))
        except Exception:  # noqa: BLE001 — best effort; underscore + forbidden rejects still apply.
            return frozenset()

    # -- RPC handlers ---------------------------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one validated RPC request to its handler (closed opcode set)."""
        op = message.get("op")
        if op == OP_PING:
            return {"kind": KIND_OK, "result": "pong"}
        if op == OP_CALL_API:
            return self._handle_call_api(message)
        if op == OP_API_DOCS:
            return self._handle_api_docs(message)
        if op == OP_FINALIZE:
            return {
                "kind": KIND_PROTOCOL_ERROR,
                "message": "finalize is not available on the runner surface",
            }
        return {"kind": KIND_PROTOCOL_ERROR, "message": f"unknown op: {op!r}"}

    def _handle_call_api(self, message: dict[str, Any]) -> dict[str, Any]:
        """Execute ``apis.<app>.<api>(**kwargs)`` in the real world; return JSON-able result.

        Runs the call THROUGH ``world.execute`` (the same stateful IPython session AppWorld uses)
        so DB mutations, auth state and pagination behave exactly as in a normal run, while the
        untrusted side only ever receives the serialised return value — never an object handle.
        """
        app = message.get("app")
        api = message.get("api")
        kwargs = message.get("kwargs", {})
        # SECURITY (trusted boundary): the proxy name-filter is bypassable — a model can reach
        # apis._rpc (a __slots__ attr) / closures / the object graph and send a RAW
        # call_api(app="_requester", ...) which would run apis._requester.request() and re-open the
        # whitelist/auth bypass (confirmed by exploit probe). Enforce here: reject underscore names,
        # require a known public app, and forbid the dangerous public api names.
        if not _is_public_name(app) or not _is_public_name(api):
            return {"kind": KIND_PROTOCOL_ERROR,
                    "message": "app and api must be public (non-underscore) identifiers"}
        if self._valid_apps and app not in self._valid_apps:
            return {"kind": KIND_PROTOCOL_ERROR, "message": f"unknown app: {app!r}"}
        if api in _FORBIDDEN_API_NAMES:
            return {"kind": KIND_PROTOCOL_ERROR, "message": f"api not permitted: {api!r}"}
        if not isinstance(kwargs, dict):
            return {"kind": KIND_PROTOCOL_ERROR, "message": "kwargs must be an object"}
        # Build a literal call expression with a JSON-literal kwargs dict. Because every value is
        # emitted via json.dumps and the keys are identifier-checked, the untrusted side cannot
        # inject code here (no f-string of raw text, no attribute chains beyond app.api).
        for key in kwargs:
            if not _is_identifier(key):
                return {"kind": KIND_PROTOCOL_ERROR, "message": f"bad kwarg name: {key!r}"}
        kwargs_src = ", ".join(f"{k}=json.loads({json.dumps(json.dumps(v))})" for k, v in kwargs.items())
        expr = f"__lb_result = apis.{app}.{api}({kwargs_src})\nprint(repr(__lb_result))"
        try:
            raw = self._world.execute(expr)
        except Exception as exc:  # noqa: BLE001 — surface as a model-visible API error, never crash host.
            return {"kind": KIND_API_ERROR, "message": f"{type(exc).__name__}: {exc}"}
        return {"kind": KIND_OK, "result": raw}

    def _handle_api_docs(self, message: dict[str, Any]) -> dict[str, Any]:
        """Forward on-demand API docs so the model is not handed all ~457 APIs at once."""
        app = message.get("app")
        api = message.get("api")
        try:
            if _is_identifier(app) and _is_identifier(api):
                code = f"print(apis.api_docs.show_api_doc(app_name={app!r}, api_name={api!r}))"
            elif _is_identifier(app):
                code = f"print(apis.api_docs.show_api_descriptions(app_name={app!r}))"
            else:
                code = "print(apis.api_docs.show_app_descriptions())"
            raw = self._world.execute(code)
        except Exception as exc:  # noqa: BLE001
            return {"kind": KIND_API_ERROR, "message": f"{type(exc).__name__}: {exc}"}
        return {"kind": KIND_OK, "result": raw}

    def _handle_finalize(self, message: dict[str, Any]) -> dict[str, Any]:
        """Harness-owned finalization + evaluation (the eval-seam fix).

        Fixes the three adapter bugs from the feasibility proof:
          * no non-existent ``world.verify`` — use ``complete_task`` then ``evaluate().to_dict()``;
          * ``passed = to_dict()["success"]`` (not a non-existent ``.passed``);
          * ``collateral_damage`` derived from the ``"assert no model changes."`` requirement
            appearing among the FAILED requirements (not a non-existent ``.collateral_damage``).
        """
        if self._finalized:
            return {"kind": KIND_PROTOCOL_ERROR, "message": "task already finalized"}
        answer = message.get("answer")
        self._finalized = True
        # complete_task is harness-owned; the untrusted side can never call it itself.
        complete_src = (
            "apis.supervisor.complete_task("
            f"answer=json.loads({json.dumps(json.dumps(answer))}), status='success')"
        )
        try:
            self._world.execute(complete_src)
        except Exception as exc:  # noqa: BLE001
            return {"kind": KIND_API_ERROR, "message": f"complete_task failed: {type(exc).__name__}: {exc}"}
        verdict = self._world.evaluate().to_dict()
        passes = [_requirement_text(p) for p in verdict.get("passes", [])]
        failures = [_requirement_text(f) for f in verdict.get("failures", [])]
        success = bool(verdict.get("success", False))
        collateral_damage = any(_COLLATERAL_REQUIREMENT in f for f in failures)
        return {
            "kind": KIND_OK,
            "result": {
                "success": success,
                "passed": success,
                "collateral_damage": collateral_damage,
                "passes": passes,
                "failures": failures,
                "num_passes": len(passes),
                "num_failures": len(failures),
            },
        }

    def close(self) -> None:
        """Tear down the real world (closes the shared TestClient cleanly on the trusted side)."""
        try:
            self._world.close()
        except Exception:  # noqa: BLE001 — best-effort teardown.
            pass


_FORBIDDEN_API_NAMES = frozenset({
    # Never invokable by untrusted model code even on a valid app: harness-owned finalization,
    # eval/state internals, teardown (DoS) levers, and the raw requester call.
    "complete_task", "evaluate", "save_state", "load_state", "close", "close_all", "request",
})


def _is_identifier(value: Any) -> bool:
    return isinstance(value, str) and value.isidentifier()


def _is_public_name(value: Any) -> bool:
    """A public (non-dunder, non-underscore) identifier — safe to interpolate as apis.<app>.<api>."""
    return _is_identifier(value) and not value.startswith("_")


def _requirement_text(item: Any) -> str:
    """Pull the human-readable requirement string out of an AppWorld pass/fail entry."""
    if isinstance(item, dict):
        for key in ("requirement", "message", "name", "description"):
            val = item.get(key)
            if isinstance(val, str):
                return val
        return json.dumps(item, sort_keys=True)
    return str(item)


def _handle_control_message(host: _RealEnvHost, message: dict[str, Any], stdout: TextIO) -> None:
    finalize_id = message.get("finalize_id")
    payload: dict[str, Any] = {
        "type": "authoritative_verdict",
        "finalize_id": finalize_id if isinstance(finalize_id, str) else "",
        "task_id": host._task_id,
    }
    if message.get("op") != OP_FINALIZE:
        payload["error"] = {
            "kind": KIND_PROTOCOL_ERROR,
            "message": f"unknown control op: {message.get('op')!r}",
        }
        _emit_stdout(payload, stdout)
        return
    if not isinstance(finalize_id, str) or not finalize_id:
        payload["error"] = {
            "kind": KIND_PROTOCOL_ERROR,
            "message": "finalize_id must be a non-empty string",
        }
        _emit_stdout(payload, stdout)
        return
    response = host._handle_finalize(message)
    if response.get("kind") == KIND_OK:
        payload["result"] = response.get("result")
    else:
        payload["error"] = {
            "kind": response.get("kind", KIND_PROTOCOL_ERROR),
            "message": str(response.get("message", response)),
        }
    _emit_stdout(payload, stdout)


def _emit_control_error(host: _RealEnvHost, message: str, stdout: TextIO) -> None:
    _emit_stdout(
        {
            "type": "authoritative_verdict",
            "finalize_id": "",
            "task_id": host._task_id,
            "error": {"kind": KIND_PROTOCOL_ERROR, "message": message},
        },
        stdout,
    )


def _emit_stdout(payload: dict[str, Any], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
    stdout.flush()


def _enqueue_control_messages(
    stdin: TextIO,
    events: queue.Queue[tuple[str, Any]],
) -> None:
    for line in stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            events.put(("control_error", exc))
            continue
        if isinstance(message, dict):
            events.put(("control_message", message))
        else:
            events.put(("control_error", ValueError("control frame must be an object")))


def _enqueue_socket_messages(
    reader: FrameReader,
    events: queue.Queue[tuple[str, Any]],
) -> None:
    while True:
        try:
            message = reader.read_message()
        except (ValueError, json.JSONDecodeError) as exc:
            events.put(("socket_error", exc))
            continue
        if message is None:
            events.put(("socket_eof", None))
            return
        events.put(("socket_message", message))


def serve(task_id: str, socket_path: str, experiment_name: str) -> int:
    """Construct the world, listen on ``socket_path``, serve RPCs until the client disconnects."""
    # Create the listening socket BEFORE building the world is unnecessary, but we must bind with
    # tight permissions: the socket lives in a private dir the orchestrator created 0700.
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    os.chmod(socket_path, 0o600)
    server.listen(1)

    host = _RealEnvHost(task_id=task_id, experiment_name=experiment_name)

    # Signal readiness to the parent (world built + socket listening).
    sys.stdout.write("READY\n")
    sys.stdout.flush()

    try:
        conn, _ = server.accept()
    except Exception:  # noqa: BLE001
        host.close()
        return 1
    reader = FrameReader(conn)
    events: queue.Queue[tuple[str, Any]] = queue.Queue()
    threading.Thread(target=_enqueue_control_messages, args=(sys.stdin, events), daemon=True).start()
    threading.Thread(target=_enqueue_socket_messages, args=(reader, events), daemon=True).start()
    try:
        while True:
            source, payload = events.get()
            if source == "control_message":
                _handle_control_message(host, payload, sys.stdout)
                continue
            if source == "control_error":
                _emit_control_error(host, str(payload), sys.stdout)
                continue
            if source == "socket_error":
                send_message(conn, {"kind": KIND_PROTOCOL_ERROR, "message": str(payload)})
                continue
            if source == "socket_eof":
                break
            message = payload
            if message is None:
                break
            if not isinstance(message, dict):
                send_message(conn, {"kind": KIND_PROTOCOL_ERROR, "message": "frame must be an object"})
                continue
            response = host.handle(message)
            send_message(conn, response)
    finally:
        try:
            conn.close()
        finally:
            host.close()
            server.close()
            if os.path.exists(socket_path):
                os.unlink(socket_path)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write("usage: env_host <task_id> <socket_path> [experiment_name]\n")
        return 2
    task_id = argv[1]
    socket_path = argv[2]
    experiment_name = argv[3] if len(argv) > 3 else "lb_agentic_sandbox"
    return serve(task_id, socket_path, experiment_name)


if __name__ == "__main__":
    # AppWorld rebinds builtins.SystemExit, so use os._exit to guarantee the code escapes.
    _rc = main(sys.argv)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
