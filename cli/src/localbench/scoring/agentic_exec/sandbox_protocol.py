"""Wire protocol shared by the trusted env-host and the untrusted code-runner.

This module is imported by BOTH sides of the process boundary, so it must stay tiny and
have NO AppWorld imports and NO secrets. It defines only:

  * the newline-delimited-JSON framing used over the unix socket, and
  * the small set of RPC opcodes the untrusted side may send.

Security note: the untrusted (bwrap) side can send arbitrary bytes on the socket. The env
host therefore treats every field as hostile input and dispatches ONLY on the closed opcode
set below; there is no eval/getattr-by-name passthrough. The opcode set is intentionally
narrow (call_api / api_docs / finalize / ping) — nothing here can reach ``world``,
``requester``, the evaluator, the filesystem, or raw HTTP.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Final

# RPC opcodes the untrusted runner may request. Anything else is rejected by the host.
OP_CALL_API: Final = "call_api"
OP_API_DOCS: Final = "api_docs"
OP_FINALIZE: Final = "finalize"
OP_PING: Final = "ping"

ALLOWED_OPS: Final = frozenset({OP_CALL_API, OP_API_DOCS, OP_FINALIZE, OP_PING})

# Result kinds the host sends back.
KIND_OK: Final = "ok"          # normal JSON-serializable result payload
KIND_API_ERROR: Final = "api_error"  # AppWorld API raised something the model should see
KIND_PROTOCOL_ERROR: Final = "protocol_error"  # malformed/forbidden request rejected by host

_MAX_FRAME_BYTES: Final = 8 * 1024 * 1024  # hard cap on a single framed message (both directions)


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    """Send one JSON object as a single newline-delimited frame.

    Raises ValueError if the encoded frame exceeds the size cap (prevents a hostile peer from
    forcing unbounded buffering on either side).
    """
    payload = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(payload) + 1 > _MAX_FRAME_BYTES:
        raise ValueError(f"frame too large: {len(payload)} bytes")
    sock.sendall(payload + b"\n")


class FrameReader:
    """Buffered newline-delimited-JSON reader over a blocking unix socket.

    Enforces the frame-size cap while reading so a peer cannot exhaust memory by sending an
    endless line with no newline.
    """

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()

    def read_message(self) -> dict[str, Any] | None:
        """Block until one full JSON frame is available; return it, or None on clean EOF."""
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = bytes(self._buf[:nl])
                del self._buf[: nl + 1]
                return json.loads(line.decode("utf-8"))
            if len(self._buf) > _MAX_FRAME_BYTES:
                raise ValueError("frame exceeded size cap before newline")
            chunk = self._sock.recv(65536)
            if not chunk:
                if self._buf:
                    raise ValueError("connection closed mid-frame")
                return None
            self._buf.extend(chunk)
