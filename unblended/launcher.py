"""
Find the Blender executable and launch it in background mode
with the unblended socket server.
"""

import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Where the server script lives (same package directory).
_SERVER_SCRIPT = str(Path(__file__).with_name("_server.py"))

# How long to wait for the UNBLENDED_READY marker (seconds).
_STARTUP_TIMEOUT = 30


class BlenderNotFoundError(FileNotFoundError):
    """Raised when no Blender executable can be located."""


def find_blender(hint: str | None = None) -> str:
    """
    Locate the Blender executable.

    Resolution order:
      1. *hint* argument (explicit path)
      2. BLENDER_PATH environment variable
      3. ``blender`` on PATH
      4. Common install locations (Windows / Linux / macOS)

    Returns the absolute path to the executable.
    Raises BlenderNotFoundError if nothing is found.
    """
    # 1. Explicit hint
    if hint and os.path.isfile(hint):
        return os.path.abspath(hint)

    # 2. Environment variable
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.isfile(env):
        return os.path.abspath(env)

    # 3. On PATH
    on_path = shutil.which("blender")
    if on_path:
        return os.path.abspath(on_path)

    # 4. Common install locations
    candidates: list[str] = []

    if sys.platform == "win32":
        for drive in ("C", "D", "E", "K"):
            candidates.extend(
                glob.glob(
                    f"{drive}:/Program Files/Blender Foundation/Blender*/blender.exe"
                )
            )
            candidates.extend(
                glob.glob(
                    f"{drive}:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe"
                )
            )
        # Also try the user's Steam library folders on other drives
        for drive in ("C", "D", "E", "F", "G", "K"):
            candidates.extend(
                glob.glob(
                    f"{drive}:/SteamLibrary/steamapps/common/Blender/blender.exe"
                )
            )
    elif sys.platform == "darwin":
        candidates.append("/Applications/Blender.app/Contents/MacOS/Blender")
    else:
        candidates.extend(glob.glob("/usr/bin/blender"))
        candidates.extend(glob.glob("/usr/local/bin/blender"))
        candidates.extend(glob.glob("/snap/bin/blender"))

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    raise BlenderNotFoundError(
        "Could not find Blender. Either:\n"
        "  - Pass blender_path= to BlenderSession()\n"
        "  - Set the BLENDER_PATH environment variable\n"
        "  - Add blender to your PATH"
    )


def launch_blender(
    blender_path: str,
    port: int = 0,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, int]:
    """
    Start Blender in background mode running the unblended server.

    Args:
        blender_path: Absolute path to the Blender executable.
        port: TCP port for the server (0 = let the OS pick one).
        extra_args: Additional CLI args passed to Blender (before ``--``).

    Returns:
        (process, actual_port) — the Popen handle and the port the
        server is listening on.

    Raises:
        RuntimeError: if Blender exits or fails to emit the ready marker
                      within the timeout.
    """
    cmd = [blender_path, "--background"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(["--python", _SERVER_SCRIPT, "--", "--port", str(port)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    actual_port = _wait_for_ready(proc)
    return proc, actual_port


def _wait_for_ready(proc: subprocess.Popen) -> int:
    """
    Block until the server prints ``UNBLENDED_READY:<port>`` on stdout,
    then return the port number.
    """
    deadline = time.monotonic() + _STARTUP_TIMEOUT

    while time.monotonic() < deadline:
        # Check if process died
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(
                f"Blender exited during startup (code {proc.returncode}).\n"
                f"stderr:\n{stderr[-2000:]}"
            )

        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue

        line = line.strip()
        if line.startswith("UNBLENDED_READY:"):
            return int(line.split(":", 1)[1])

    # Timed out
    proc.kill()
    raise RuntimeError(
        f"Blender did not become ready within {_STARTUP_TIMEOUT}s. "
        "Check that the Blender path is correct and that Blender can "
        "run in --background mode."
    )
