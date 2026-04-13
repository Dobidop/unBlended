"""
unblended — headless Blender as a Python API.

    from unblended import BlenderSession

    with BlenderSession() as b:
        b.exec("bpy.ops.mesh.primitive_cube_add()")
        name = b.eval("bpy.context.active_object.name")
        b.render("output.png", samples=64)
"""

from .session import BlenderSession, BlenderError
from .launcher import find_blender, BlenderNotFoundError

__all__ = [
    "BlenderSession",
    "BlenderError",
    "BlenderNotFoundError",
    "find_blender",
]
