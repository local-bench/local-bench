"""Host-agnostic unit tests for the AppWorld-C sandbox internals (no bwrap / no appworld needed).

These lock in the security-critical invariants of the pieces that run on the UNTRUSTED side
(the ``apis`` proxy shape, the guarded import allow-list, the observation parser) and the wire
protocol framing, independently of the live two-process gates in
``test_appworld_sandbox_acceptance.py``. They run anywhere (Linux/WSL/Windows).
"""

from __future__ import annotations

import io
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench.scoring.agentic_exec import runner_bootstrap as rb  # noqa: E402
from localbench.scoring.agentic_exec import sandbox_protocol as sp  # noqa: E402


class _FakeRpc:
    """Records the last RPC and returns a scripted env-host response."""

    def __init__(self, response: dict | None = None) -> None:
        self.last: dict | None = None
        self.response = response or {"kind": rb.KIND_OK, "result": "42"}

    def call(self, message: dict) -> dict:
        self.last = message
        return self.response


# ----------------------------------------------------------------------------------------------
# apis proxy: shape + no-leak invariants
# ----------------------------------------------------------------------------------------------
def test_apis_proxy_carries_no_sensitive_handles() -> None:
    proxy = rb.ApisProxy(_FakeRpc())
    # The whole point: the proxy holds the socket client + the docs shim and NOTHING else.
    assert set(proxy.__slots__) == {"_rpc", "api_docs"}
    for forbidden in ("_requester", "requester", "client", "close", "close_all", "world",
                      "task", "evaluate", "complete_task", "ground_truth"):
        assert not hasattr(proxy, forbidden), f"proxy must not expose {forbidden}"


def test_apis_proxy_app_namespace_refuses_dangerous_attrs() -> None:
    proxy = rb.ApisProxy(_FakeRpc())
    app = proxy.spotify  # a normal app namespace
    for forbidden in ("close", "close_all", "_requester", "requester", "client"):
        assert not hasattr(app, forbidden)


def test_apis_proxy_routes_calls_as_app_api_kwargs() -> None:
    rpc = _FakeRpc({"kind": rb.KIND_OK, "result": json.dumps({"access_token": "tok"})})
    proxy = rb.ApisProxy(rpc)
    result = proxy.spotify.login(username="u@e", password="pw")
    assert rpc.last == {
        "op": rb.OP_CALL_API,
        "app": "spotify",
        "api": "login",
        "kwargs": {"username": "u@e", "password": "pw"},
    }
    # OK string results are parsed back to Python data for the agent.
    assert result == {"access_token": "tok"}


def test_apis_proxy_surfaces_api_error_without_object_handle() -> None:
    rpc = _FakeRpc({"kind": rb.KIND_API_ERROR, "message": "BadRequest: no such song"})
    proxy = rb.ApisProxy(rpc)
    with pytest.raises(rb.ApiError) as exc:
        proxy.spotify.show_song(song_id="nope")
    assert "BadRequest" in str(exc.value)


# ----------------------------------------------------------------------------------------------
# guarded __import__: allow-list only
# ----------------------------------------------------------------------------------------------
def test_guarded_import_allows_only_safe_modules() -> None:
    ns = rb._build_namespace(rb.ApisProxy(_FakeRpc()))
    guarded = ns["__builtins__"]["__import__"]
    # allow-listed pure-data modules import fine.
    for mod in ("re", "json", "math", "collections", "itertools"):
        assert guarded(mod).__name__ == mod
    # every escape module the canary suite probes is denied.
    for mod in ("os", "pathlib", "io", "sys", "socket", "subprocess", "importlib",
                "ctypes", "pickle", "inspect", "pydoc", "glob", "shutil", "tempfile",
                "marshal", "pkgutil", "sqlite3", "requests", "httpx"):
        with pytest.raises(ImportError):
            guarded(mod)


def test_guarded_import_blocks_relative_and_dotted_escapes() -> None:
    ns = rb._build_namespace(rb.ApisProxy(_FakeRpc()))
    guarded = ns["__builtins__"]["__import__"]
    with pytest.raises(ImportError):
        guarded("os.path")          # dotted form of a denied root
    with pytest.raises(ImportError):
        guarded("re", level=1)      # relative import


def test_safe_builtins_exclude_dangerous_names() -> None:
    ns = rb._build_namespace(rb.ApisProxy(_FakeRpc()))
    builtins_ns = ns["__builtins__"]
    for dangerous in ("open", "eval", "exec", "compile", "input", "breakpoint",
                      "globals", "locals", "vars", "help", "exit", "quit"):
        assert dangerous not in builtins_ns, f"{dangerous} must not be a safe builtin"
    # but the everyday ones the agent needs ARE present.
    for ok in ("len", "range", "sorted", "set", "dict", "print", "sum", "enumerate"):
        assert ok in builtins_ns


# ----------------------------------------------------------------------------------------------
# block execution in the restricted namespace
# ----------------------------------------------------------------------------------------------
def test_run_block_executes_legit_code_and_persists_state() -> None:
    ns = rb._build_namespace(rb.ApisProxy(_FakeRpc()))
    r1 = rb._run_block(ns, "import re\nx = len(re.findall(r'a', 'banana'))\nprint('x', x)")
    assert r1["error"] is None
    assert r1["stdout"].strip() == "x 3"
    # state persists across blocks (x reused).
    r2 = rb._run_block(ns, "print('again', x + 1)")
    assert r2["stdout"].strip() == "again 4"


def test_run_block_reports_blocked_open_as_error() -> None:
    ns = rb._build_namespace(rb.ApisProxy(_FakeRpc()))
    # open is not a safe builtin -> NameError; pathlib import -> ImportError. Either is an error.
    r = rb._run_block(ns, "print(open('/etc/passwd').read())")
    assert r["error"] is not None
    assert "open" in r["error"] or "NameError" in r["error"]


def test_observation_parse_contract_json_then_literal_then_str() -> None:
    assert rb._parse_observation('{"a": 1}') == {"a": 1}      # json
    assert rb._parse_observation("{'a': 1}") == {"a": 1}      # python literal
    assert rb._parse_observation("[1, 2, 3]") == [1, 2, 3]
    assert rb._parse_observation("just text") == "just text"  # raw str fallback
    assert rb._parse_observation("") == ""


# ----------------------------------------------------------------------------------------------
# wire protocol framing
# ----------------------------------------------------------------------------------------------
def test_frame_reader_roundtrips_newline_delimited_json() -> None:
    a, b = socket.socketpair()
    try:
        reader = sp.FrameReader(a)
        sp.send_message(b, {"op": "ping"})
        sp.send_message(b, {"op": "call_api", "app": "spotify", "api": "login", "kwargs": {}})
        assert reader.read_message() == {"op": "ping"}
        assert reader.read_message() == {"op": "call_api", "app": "spotify",
                                         "api": "login", "kwargs": {}}
    finally:
        a.close()
        b.close()


def test_frame_reader_returns_none_on_clean_eof() -> None:
    a, b = socket.socketpair()
    reader = sp.FrameReader(a)
    b.close()
    assert reader.read_message() is None
    a.close()


def test_send_message_rejects_oversized_frame() -> None:
    a, b = socket.socketpair()
    try:
        huge = {"x": "y" * (9 * 1024 * 1024)}
        with pytest.raises(ValueError):
            sp.send_message(a, huge)
    finally:
        a.close()
        b.close()
