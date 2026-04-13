# unblended

Headless Blender as a Python API.

Launches Blender in the background and talks to it over a local socket. You get full `bpy` access from ordinary Python — no `bpy` pip package, no subprocess-per-call overhead, no lost state between operations.

## How it works

```
Your Python code  ──socket──>  blender --background (persistent process)
                                  │
                                  ├── full bpy access
                                  ├── GPU rendering (Cycles/EEVEE)
                                  └── state persists across calls
```

unblended launches `blender --background` once with a socket server inside it. Your code sends Python snippets over the socket; Blender executes them and returns results. The process stays alive — scene state, materials, imported models all persist between calls.

## Requirements

- Python 3.10+
- [Blender](https://www.blender.org/download/) installed (any version with Python 3.10+ — Blender 3.6+)
- No pip dependencies

## Installation

```bash
pip install unblended
```

Or from source:

```bash
git clone https://github.com/Dobidop/unblended.git
cd unblended
pip install -e .
```

## Quick start

```python
from unblended import BlenderSession

with BlenderSession() as b:
    b.exec("bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1))")
    name = b.eval("bpy.context.active_object.name")  # "Suzanne"
    b.render("output.png", engine="CYCLES", samples=128)
```

## Finding Blender

unblended searches for the Blender executable in this order:

1. `blender_path` argument: `BlenderSession(blender_path="/path/to/blender")`
2. `BLENDER_PATH` environment variable
3. `blender` on your system PATH
4. Common install locations (Program Files, Steam, /usr/bin, /Applications, etc.)

## API

### Low-level (full bpy power)

```python
# Execute code — full access to bpy, persistent namespace
b.exec("bpy.ops.mesh.primitive_cube_add(size=2)")

# Evaluate expression — returns JSON-safe result
name = b.eval("bpy.context.active_object.name")

# Inject data without string formatting
b.exec("bpy.ops.wm.open_mainfile(filepath=path)", path="C:/scene.blend")

# Run a script file
b.run("setup_scene.py")
```

### High-level convenience

```python
# Rendering
b.render("out.png", engine="CYCLES", samples=64, resolution=(1920, 1080), use_gpu=True)

# Scene management
b.clear_scene()
b.open_blend("scene.blend")
b.save_blend("output.blend")

# Import models
b.import_obj("model.obj")
b.import_fbx("character.fbx")
b.import_stl("part.stl")

# Query
b.list_objects()       # ["Cube", "Camera", "Light"]
b.blender_version()    # "4.2.0"
b.ping()               # True
```

### Persistent namespace

Variables and functions defined in `exec()` persist across calls:

```python
b.exec("import math")
b.exec("def place_ring(n, r):\n"
       "    for i in range(n):\n"
       "        a = 2 * math.pi * i / n\n"
       "        bpy.ops.mesh.primitive_cube_add(location=(r*math.cos(a), r*math.sin(a), 0))")
b.exec("place_ring(12, 5)")
```

### Error handling

Errors in Blender propagate with full tracebacks:

```python
from unblended import BlenderError

try:
    b.exec("bpy.data.objects['NonExistent']")
except BlenderError as e:
    print(e)  # includes the Blender-side traceback
```

## Architecture

```
unblended/
    __init__.py      # BlenderSession, BlenderError, find_blender
    session.py       # Client: manages connection + high-level API
    launcher.py      # Finds Blender, spawns process, waits for ready
    protocol.py      # Length-prefixed JSON over TCP socket
    _server.py       # Runs inside Blender: socket loop + request handler
```

~300 lines of actual code. Zero dependencies beyond Python's standard library.

## vs. alternatives

| Approach | Startup per call | Persistent state | Full bpy | No extra deps |
|----------|:---:|:---:|:---:|:---:|
| `subprocess` + `blender -b -P` | ~2s | No | Yes | Yes |
| `bpy` pip package | None | Yes | Partial | No |
| BlenderProc | ~2s | No | Partial | No |
| **unblended** | **Once** | **Yes** | **Yes** | **Yes** |

## License

MIT
