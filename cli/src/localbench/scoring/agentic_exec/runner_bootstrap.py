"""UNTRUSTED runner bootstrap — executes inside the bwrap jail.

This file is copied into the jail's tmpfs and run as ``python3 /lbrun/runner_bootstrap.py``.
It has NO AppWorld import and NO knowledge of any path under the data tree. Its only window onto
AppWorld is a unix socket at a fixed in-jail path (``/rpc/rpc.sock``) that the orchestrator
bind-mounted in; everything else (the data tree, ``$APPWORLD_ROOT``, the real ``requester``, the
evaluator) is simply NOT PRESENT in this process or its filesystem.

It speaks a tiny line-protocol on its stdin/stdout to the orchestrator (the trusted parent on the
other side of the bwrap pipe):

  * orchestrator -> runner :  {"cmd":"run_block","code":"..."}        run one model code block
                              {"cmd":"finalize","answer":<json>}      finalize + evaluate
                              {"cmd":"shutdown"}                        exit cleanly
  * runner -> orchestrator :  {"event":"ready"}                        once, at startup
                              {"event":"block_result","stdout":..,"error":..}
                              {"event":"final_result","verdict":{...}}
                              {"event":"fatal","message":...}

The model's code runs via ``exec`` in a namespace whose ONLY AppWorld surface is an ``ApisProxy``
(a plain object that marshals ``apis.<app>.<api>(**kwargs)`` to the env host over the socket and
returns plain data). A secondary in-process allow-list of safe builtins/modules is installed as a
BELT — but it is explicitly NOT the security boundary. The boundary is this process having nothing
sensitive in it and no filesystem path to the data tree (proven by the canary suite running here).
"""

from __future__ import annotations

import ast
import io
import json
import socket
import sys
from contextlib import redirect_stdout
from typing import Any

# The wire protocol module is import-safe (no AppWorld, no secrets) and is copied into the jail
# next to this file, importable as a sibling. We import defensively so the file also works if it
# was concatenated; see _load_protocol below.
RPC_SOCKET_PATH = "/rpc/rpc.sock"

OP_CALL_API = "call_api"
OP_API_DOCS = "api_docs"
OP_FINALIZE = "finalize"
OP_PING = "ping"
KIND_OK = "ok"
KIND_API_ERROR = "api_error"
KIND_PROTOCOL_ERROR = "protocol_error"


# ----------------------------------------------------------------------------------------------
# Minimal socket framing (duplicated rather than imported so the jail needs only this one file).
# ----------------------------------------------------------------------------------------------
class _Rpc:
    """Newline-delimited-JSON RPC client to the env host over the in-jail unix socket."""

    def __init__(self, sock_path: str) -> None:
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(sock_path)
        self._buf = bytearray()

    def call(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self._sock.sendall(payload + b"\n")
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = bytes(self._buf[:nl])
                del self._buf[: nl + 1]
                return json.loads(line.decode("utf-8"))
            chunk = self._sock.recv(65536)
            if not chunk:
                raise RuntimeError("env host closed the RPC socket")
            self._buf.extend(chunk)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class ApiError(Exception):
    """Raised inside model code when an AppWorld API call returns an error.

    Mirrors what a normal AppWorld run would surface to the model. Carries NO object handle.
    """


# ----------------------------------------------------------------------------------------------
# The `apis` proxy handed to model code. PLAIN object: no _requester, no client, no closure that
# leads back to a Requester/TestClient/world. It can ONLY send (app, api, kwargs) over the socket.
# ----------------------------------------------------------------------------------------------
class _ApiMethod:
    """A bound ``apis.<app>.<api>`` callable that RPCs to the env host."""

    # __slots__ keeps the object minimal and prevents stashing extra state on it.
    __slots__ = ("_rpc", "_app", "_api")

    def __init__(self, rpc: _Rpc, app: str, api: str) -> None:
        self._rpc = rpc
        self._app = app
        self._api = api

    def __call__(self, **kwargs: Any) -> Any:
        resp = self._rpc.call(
            {"op": OP_CALL_API, "app": self._app, "api": self._api, "kwargs": kwargs}
        )
        return _interpret_api_response(resp)


# Attribute names that must never resolve on the proxy or an app namespace — these are the
# whitelist-bypass / DoS handles the attack-surface doc calls out (H1/H3/H5). The proxy carries
# none of them structurally (it has no requester/client), but we also refuse them by name so the
# contract is explicit and ``hasattr(apis, 'close')`` is False.
_FORBIDDEN_PROXY_ATTRS = frozenset({
    "close", "close_all", "_requester", "requester", "client", "_client", "world", "task",
    "evaluate", "save_state", "load_state", "ground_truth", "complete_task",
})


class _ApiApp:
    """An ``apis.<app>`` namespace; attribute access yields RPC-backed methods."""

    __slots__ = ("_rpc", "_app")

    def __init__(self, rpc: _Rpc, app: str) -> None:
        self._rpc = rpc
        self._app = app

    def __getattr__(self, api: str) -> _ApiMethod:
        if api.startswith("_") or api in _FORBIDDEN_PROXY_ATTRS:
            raise AttributeError(api)
        return _ApiMethod(self._rpc, self._app, api)


class _ApiDocs:
    """Thin ``apis.api_docs`` shim so the agent can request on-demand docs over the socket."""

    __slots__ = ("_rpc",)

    def __init__(self, rpc: _Rpc) -> None:
        self._rpc = rpc

    def show_app_descriptions(self) -> Any:
        return _interpret_api_response(self._rpc.call({"op": OP_API_DOCS}))

    def show_api_descriptions(self, app_name: str) -> Any:
        return _interpret_api_response(self._rpc.call({"op": OP_API_DOCS, "app": app_name}))

    def show_api_doc(self, app_name: str, api_name: str) -> Any:
        return _interpret_api_response(
            self._rpc.call({"op": OP_API_DOCS, "app": app_name, "api": api_name})
        )


class ApisProxy:
    """The single AppWorld object visible to model code. Carries no requester/world/client.

    ``apis.spotify.show_song_library(access_token=..., page_index=0)`` -> RPC -> plain data.
    Attribute access for any app name returns an ``_ApiApp``; ``apis.api_docs`` is the docs shim.
    There is deliberately NO ``_requester``, NO ``close``/``close_all``, NO ``complete_task``
    (finalization is harness-owned via the separate finalize command).
    """

    __slots__ = ("_rpc", "api_docs")

    def __init__(self, rpc: _Rpc) -> None:
        self._rpc = rpc
        self.api_docs = _ApiDocs(rpc)

    def __getattr__(self, app: str) -> _ApiApp:
        # __getattr__ only fires for names not in __slots__, so api_docs/_rpc are unaffected.
        if app.startswith("_") or app in _FORBIDDEN_PROXY_ATTRS:
            raise AttributeError(app)
        return _ApiApp(self._rpc, app)


def _interpret_api_response(resp: dict[str, Any]) -> Any:
    """Turn an env-host RPC response into a return value or a model-visible error."""
    kind = resp.get("kind")
    if kind == KIND_OK:
        raw = resp.get("result")
        # call_api/api_docs return the env host's captured ``print(repr(...))`` stdout (a str).
        # finalize returns a structured dict. Parse strings back to Python values for ergonomics
        # (json -> literal_eval -> raw str), matching the observation-parse contract.
        if isinstance(raw, str):
            return _parse_observation(raw)
        return raw
    if kind == KIND_API_ERROR:
        raise ApiError(str(resp.get("message", "API error")))
    raise ApiError("protocol error: " + str(resp.get("message", resp)))


def _parse_observation(text: str) -> Any:
    """Observation parse contract: try ``json.loads`` -> ``ast.literal_eval`` -> raw str."""
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except (ValueError, TypeError):
        pass
    try:
        return ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        pass
    return text


# ----------------------------------------------------------------------------------------------
# Restricted execution namespace (secondary belt).
# ----------------------------------------------------------------------------------------------
_SAFE_MODULES = ("re", "json", "math", "datetime", "itertools", "collections", "functools",
                 "string", "statistics", "decimal", "fractions")
_SAFE_MODULE_SET = frozenset(_SAFE_MODULES)


def _make_guarded_import(preimported: dict[str, Any]) -> Any:
    """A restricted ``__import__`` that allows ONLY the safe-module allow-list.

    Legitimate task code (``import re``, ``import json``, ``from collections import Counter``) works;
    every escape module the canary suite probes (``os``, ``pathlib``, ``io``, ``socket``,
    ``subprocess``, ``importlib``, ``ctypes``, ``pickle``, ``inspect``, ``sys`` …) raises
    ImportError. The top-level package name is checked against the allow-list, so dotted/aliased
    forms cannot smuggle a denied module. Submodules of allowed packages are NOT auto-granted
    (none of the allow-listed pure-data modules need them), keeping the surface tight.
    """
    import builtins as _b

    real_import = _b.__import__

    def _guarded(name: str, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        root = name.split(".", 1)[0]
        if level != 0:
            raise ImportError("relative imports are not allowed in the sandbox")
        if root not in _SAFE_MODULE_SET:
            raise ImportError(f"import of {name!r} is not allowed in the sandbox")
        module = real_import(name, globals, locals, fromlist, level)
        preimported.setdefault(root, module)
        return module

    return _guarded

# Builtins the model legitimately needs to write task-solving code. Deliberately omits
# open/__import__/eval/exec/compile/input/breakpoint/globals/locals/vars/help/exit/quit.
_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable", "chr",
    "complex", "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset",
    "getattr", "hasattr", "hash", "hex", "int", "isinstance", "issubclass", "iter", "len",
    "list", "map", "max", "min", "next", "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "setattr", "slice", "sorted", "str", "sum", "tuple",
    "type", "zip", "True", "False", "None", "Exception", "ValueError", "KeyError", "IndexError",
    "TypeError", "StopIteration", "RuntimeError", "AttributeError", "ZeroDivisionError",
)


def _build_namespace(apis: ApisProxy) -> dict[str, Any]:
    import builtins as _b

    safe_builtins: dict[str, Any] = {}
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(_b, name):
            safe_builtins[name] = getattr(_b, name)

    namespace: dict[str, Any] = {
        "apis": apis,
        "ApiError": ApiError,
    }
    for mod_name in _SAFE_MODULES:
        try:
            namespace[mod_name] = __import__(mod_name)
        except ImportError:
            pass
    # Install a guarded __import__ that allows ONLY the safe-module allow-list, so legitimate
    # `import re`/`from collections import Counter` works while every canary escape module is denied.
    safe_builtins["__import__"] = _make_guarded_import(namespace)
    namespace["__builtins__"] = safe_builtins
    return namespace


# ----------------------------------------------------------------------------------------------
# Block execution
# ----------------------------------------------------------------------------------------------
def _run_block(namespace: dict[str, Any], code: str) -> dict[str, Any]:
    """Exec one model code block in the persistent namespace; capture stdout; report errors."""
    buf = io.StringIO()
    error: str | None = None
    try:
        compiled = compile(code, "<model_block>", "exec")
    except SyntaxError as exc:
        return {"event": "block_result", "stdout": "", "error": f"SyntaxError: {exc}"}
    try:
        with redirect_stdout(buf):
            exec(compiled, namespace, namespace)  # noqa: S102 — sandboxed exec is the whole point.
    except Exception as exc:  # noqa: BLE001 — any runtime error is reported as an observation.
        error = f"{type(exc).__name__}: {exc}"
    return {"event": "block_result", "stdout": buf.getvalue(), "error": error}


# ----------------------------------------------------------------------------------------------
# Main control loop: read commands from stdin, act, write events to stdout.
# ----------------------------------------------------------------------------------------------
def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        rpc = _Rpc(RPC_SOCKET_PATH)
    except OSError as exc:
        _emit({"event": "fatal", "message": f"cannot connect RPC socket: {exc}"})
        return 1

    apis = ApisProxy(rpc)
    namespace = _build_namespace(apis)
    _emit({"event": "ready"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit({"event": "fatal", "message": f"bad command json: {exc}"})
            continue
        kind = cmd.get("cmd")
        if kind == "run_block":
            _emit(_run_block(namespace, cmd.get("code", "")))
        elif kind == "finalize":
            resp = rpc.call({"op": OP_FINALIZE, "answer": cmd.get("answer")})
            if resp.get("kind") == KIND_OK:
                _emit({"event": "final_result", "verdict": resp.get("result")})
            else:
                _emit({"event": "final_result", "verdict": None,
                       "error": str(resp.get("message", resp))})
        elif kind == "shutdown":
            break
        else:
            _emit({"event": "fatal", "message": f"unknown cmd: {kind!r}"})

    rpc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
