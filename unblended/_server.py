"""
Socket server that runs inside Blender's Python interpreter.

Launched via:  blender --background --python _server.py -- --port PORT

Keeps Blender alive in a blocking loop, accepting commands over a
localhost TCP socket and executing them with full access to bpy.
"""

import socket
import sys
import os
import traceback
import uuid

# Allow importing protocol.py from the same directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import send_message, recv_message

import bpy  # available because we run inside Blender

# ---------------------------------------------------------------------------
# Serialisation helpers – turn bpy / mathutils objects into JSON-safe values
# ---------------------------------------------------------------------------

def _serialize(obj):
    """Best-effort conversion of a Python/Blender object to JSON-safe form."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, set):
        return [_serialize(x) for x in obj]

    # mathutils types
    try:
        from mathutils import Vector, Euler, Quaternion, Matrix, Color
        if isinstance(obj, (Vector, Euler, Color)):
            return [round(v, 6) for v in obj]
        if isinstance(obj, Quaternion):
            return [round(v, 6) for v in obj]
        if isinstance(obj, Matrix):
            return [[round(v, 6) for v in row] for row in obj]
    except ImportError:
        pass

    # bpy data-block: return name + type so the caller can reference it
    if hasattr(obj, "bl_rna"):
        info = {"__blender_type__": type(obj).__name__, "name": getattr(obj, "name", str(obj))}
        return info

    return str(obj)


# ---------------------------------------------------------------------------
# Persistent namespace shared across all exec/eval calls
# ---------------------------------------------------------------------------

_namespace: dict = {
    "bpy": bpy,
    "__builtins__": __builtins__,
}


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------

def _handle(request: dict) -> dict:
    """Dispatch a single request and return a response dict."""
    req_id = request.get("id", str(uuid.uuid4()))
    req_type = request.get("type")

    try:
        # Inject optional data into namespace
        if "data" in request and isinstance(request["data"], dict):
            _namespace.update(request["data"])

        if req_type == "exec":
            exec(request["code"], _namespace)
            return {"id": req_id, "ok": True, "result": None}

        elif req_type == "eval":
            result = eval(request["code"], _namespace)
            return {"id": req_id, "ok": True, "result": _serialize(result)}

        elif req_type == "ping":
            return {"id": req_id, "ok": True, "result": "pong"}

        elif req_type == "shutdown":
            return {"id": req_id, "ok": True, "result": None, "_shutdown": True}

        else:
            return {"id": req_id, "ok": False, "error": f"Unknown request type: {req_type}"}

    except Exception as exc:
        return {
            "id": req_id,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


# ---------------------------------------------------------------------------
# Main server loop
# ---------------------------------------------------------------------------

def main() -> None:
    # Parse --port from Blender-style argv (everything after "--")
    argv = sys.argv
    port = 0  # 0 = OS picks a free port
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
        for i, arg in enumerate(args):
            if arg == "--port" and i + 1 < len(args):
                port = int(args[i + 1])

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    actual_port = server.getsockname()[1]
    server.listen(1)

    # Ready marker – the client reads stdout for this line.
    print(f"UNBLENDED_READY:{actual_port}", flush=True)

    conn, _addr = server.accept()
    try:
        while True:
            request = recv_message(conn)
            if request is None:
                break  # client disconnected

            response = _handle(request)
            send_message(conn, response)

            if response.get("_shutdown"):
                break
    finally:
        conn.close()
        server.close()


if __name__ == "__main__":
    main()
