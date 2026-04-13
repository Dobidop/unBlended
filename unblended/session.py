"""
Client-side BlenderSession — the main public API of unblended.

Usage::

    from unblended import BlenderSession

    with BlenderSession() as b:
        b.exec("bpy.ops.mesh.primitive_cube_add()")
        name = b.eval("bpy.context.active_object.name")
        b.render("output.png", samples=128)
"""

import socket
import uuid
from pathlib import Path

from .launcher import find_blender, launch_blender
from .protocol import send_message, recv_message


class BlenderError(RuntimeError):
    """An exception that occurred inside the Blender process."""

    def __init__(self, message: str, remote_traceback: str | None = None):
        self.remote_traceback = remote_traceback
        if remote_traceback:
            super().__init__(f"{message}\n\nBlender traceback:\n{remote_traceback}")
        else:
            super().__init__(message)


class BlenderSession:
    """
    A persistent connection to a headless Blender process.

    The session launches ``blender --background`` with a socket server,
    then provides :meth:`exec` and :meth:`eval` to run arbitrary Python
    inside Blender's interpreter, plus convenience methods for common
    operations.

    Use as a context manager for automatic cleanup::

        with BlenderSession() as b:
            b.exec("bpy.ops.mesh.primitive_cube_add()")

    Args:
        blender_path: Explicit path to the Blender executable.
                      Falls back to auto-detection if omitted.
        startup_blend: Optional ``.blend`` file to open on startup
                       (passed as ``--open`` to Blender).
    """

    def __init__(
        self,
        blender_path: str | None = None,
        startup_blend: str | None = None,
    ):
        self._blender_path = find_blender(blender_path)
        self._startup_blend = startup_blend
        self._process = None
        self._sock: socket.socket | None = None
        self._port: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "BlenderSession":
        """Launch Blender and connect. Called automatically by __enter__."""
        extra_args = []
        if self._startup_blend:
            extra_args.append(str(self._startup_blend))

        self._process, self._port = launch_blender(
            self._blender_path,
            port=0,
            extra_args=extra_args,
        )

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect(("127.0.0.1", self._port))
        return self

    def close(self) -> None:
        """Shut down the Blender process and release resources."""
        if self._sock:
            try:
                self._request({"type": "shutdown"})
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()
            self._process = None

    def __enter__(self) -> "BlenderSession":
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Low-level API
    # ------------------------------------------------------------------

    def exec(self, code: str, **data) -> None:
        """
        Execute arbitrary Python *code* inside Blender.

        Optional keyword arguments are injected into the server's
        persistent namespace before execution, so you can safely pass
        data without string-formatting it into the code::

            b.exec("bpy.ops.wm.open_mainfile(filepath=path)", path="C:/scene.blend")
        """
        resp = self._request({"type": "exec", "code": code, "data": data or None})
        self._check(resp)

    def eval(self, code: str, **data):
        """
        Evaluate a Python expression inside Blender and return the result.

        The result is JSON-serialised on the Blender side; mathutils types
        (Vector, Matrix, etc.) are converted to plain lists.

        ::

            name = b.eval("bpy.context.active_object.name")
        """
        resp = self._request({"type": "eval", "code": code, "data": data or None})
        self._check(resp)
        return resp["result"]

    def ping(self) -> bool:
        """Return True if the Blender process is alive and responding."""
        try:
            resp = self._request({"type": "ping"})
            return resp.get("ok", False)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # High-level convenience methods
    # ------------------------------------------------------------------

    def run(self, script_path: str, **data) -> None:
        """
        Execute a Python script file inside Blender.

        The script has access to the full ``bpy`` module and the
        persistent namespace (including any **data kwargs injected).
        """
        code = Path(script_path).read_text(encoding="utf-8")
        self.exec(code, **data)

    def render(
        self,
        output: str,
        *,
        engine: str | None = None,
        samples: int | None = None,
        resolution: tuple[int, int] | None = None,
        use_gpu: bool = True,
    ) -> None:
        """
        Render the current scene to *output*.

        Args:
            output:     File path for the rendered image.
            engine:     ``'CYCLES'`` or ``'BLENDER_EEVEE_NEXT'``.
            samples:    Number of render samples (Cycles).
            resolution: ``(width, height)`` in pixels.
            use_gpu:    Attempt GPU rendering (Cycles + CUDA/OptiX).
        """
        lines = ["import bpy, os", f"output = r'{output}'"]
        lines.append("os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)")

        if engine:
            lines.append(f"bpy.context.scene.render.engine = '{engine}'")
        if samples is not None:
            lines.append(f"bpy.context.scene.cycles.samples = {samples}")
        if resolution:
            lines.append(f"bpy.context.scene.render.resolution_x = {resolution[0]}")
            lines.append(f"bpy.context.scene.render.resolution_y = {resolution[1]}")
        if use_gpu:
            lines.append(
                "try:\n"
                "    prefs = bpy.context.preferences.addons['cycles'].preferences\n"
                "    prefs.compute_device_type = 'CUDA'\n"
                "    prefs.get_devices()\n"
                "    for d in prefs.devices: d.use = True\n"
                "    bpy.context.scene.cycles.device = 'GPU'\n"
                "except Exception:\n"
                "    pass"
            )

        lines.append(f"bpy.context.scene.render.filepath = output")
        lines.append("bpy.ops.render.render(write_still=True)")
        self.exec("\n".join(lines))

    def open_blend(self, path: str) -> None:
        """Open a ``.blend`` file, replacing the current scene."""
        self.exec("bpy.ops.wm.open_mainfile(filepath=path)", path=str(path))

    def save_blend(self, path: str) -> None:
        """Save the current scene to a ``.blend`` file."""
        self.exec(
            "import os; os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True); "
            "bpy.ops.wm.save_as_mainfile(filepath=path)",
            path=str(path),
        )

    def clear_scene(self) -> None:
        """Delete every object in the scene."""
        self.exec(
            "bpy.ops.object.select_all(action='SELECT')\n"
            "bpy.ops.object.delete()\n"
            "for m in list(bpy.data.materials): bpy.data.materials.remove(m)\n"
            "for i in list(bpy.data.images): bpy.data.images.remove(i)"
        )

    def import_obj(self, path: str) -> str:
        """Import an OBJ file and return the name of the active object."""
        self.exec("bpy.ops.wm.obj_import(filepath=path)", path=str(path))
        return self.eval("bpy.context.active_object.name if bpy.context.active_object else None")

    def import_fbx(self, path: str) -> str:
        """Import an FBX file and return the name of the active object."""
        self.exec("bpy.ops.import_scene.fbx(filepath=path)", path=str(path))
        return self.eval("bpy.context.active_object.name if bpy.context.active_object else None")

    def import_stl(self, path: str) -> str:
        """Import an STL file and return the name of the active object."""
        self.exec("bpy.ops.wm.stl_import(filepath=path)", path=str(path))
        return self.eval("bpy.context.active_object.name if bpy.context.active_object else None")

    def list_objects(self) -> list[str]:
        """Return names of all objects in the scene."""
        return self.eval("[o.name for o in bpy.data.objects]")

    def blender_version(self) -> str:
        """Return the Blender version string."""
        return self.eval("'.'.join(str(x) for x in bpy.app.version)")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(self, msg: dict) -> dict:
        if self._sock is None:
            raise RuntimeError("Session is not connected. Call .start() first.")
        msg.setdefault("id", str(uuid.uuid4()))
        send_message(self._sock, msg)
        resp = recv_message(self._sock)
        if resp is None:
            raise ConnectionError("Blender process closed the connection.")
        return resp

    @staticmethod
    def _check(resp: dict) -> None:
        if not resp.get("ok"):
            raise BlenderError(
                resp.get("error", "Unknown error"),
                resp.get("traceback"),
            )
