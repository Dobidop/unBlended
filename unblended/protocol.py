"""
Wire protocol for unblended client/server communication.

Messages are length-prefixed JSON over a TCP socket:
  [4 bytes: big-endian uint32 payload length][N bytes: JSON payload]

This module is imported by both the client (normal Python) and
the server (running inside Blender's Python), so it must have
zero dependencies beyond the standard library.
"""

import json
import struct
import socket

HEADER_FORMAT = "!I"  # big-endian uint32
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_SIZE = 64 * 1024 * 1024  # 64 MB safety limit


def send_message(sock: socket.socket, obj: dict) -> None:
    """Serialize *obj* as JSON and send it length-prefixed."""
    payload = json.dumps(obj, default=str).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header + payload)


def recv_message(sock: socket.socket) -> dict | None:
    """Read one length-prefixed JSON message. Returns None on EOF."""
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack(HEADER_FORMAT, header)
    if length > MAX_MESSAGE_SIZE:
        raise RuntimeError(f"Message too large: {length} bytes")
    payload = _recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Read exactly *n* bytes from *sock*. Returns None on clean EOF."""
    parts = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            if parts:
                raise ConnectionError("Connection lost mid-message")
            return None
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)
