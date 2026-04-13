"""
Smoke test: launch a BlenderSession, run basic operations, verify results.

Requires Blender to be installed and findable (BLENDER_PATH env var,
on PATH, or in a standard install location).

Run:  python -m pytest tests/test_smoke.py -v
  or: python tests/test_smoke.py
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unblended import BlenderSession


@pytest.fixture(scope="module")
def session():
    """A single BlenderSession shared across all tests in this module."""
    with BlenderSession() as b:
        yield b


def test_ping(session):
    assert session.ping()


def test_version(session):
    ver = session.blender_version()
    assert ver, "Version string should not be empty"
    parts = ver.split(".")
    assert len(parts) >= 2, f"Unexpected version format: {ver}"


def test_exec_eval_cube(session):
    session.exec("bpy.ops.mesh.primitive_cube_add(location=(1, 2, 3))")
    name = session.eval("bpy.context.active_object.name")
    assert name is not None

    loc = session.eval("list(bpy.context.active_object.location)")
    assert loc == [1.0, 2.0, 3.0]


def test_list_objects(session):
    objects = session.list_objects()
    assert isinstance(objects, list)
    assert len(objects) > 0


def test_persistent_namespace(session):
    session.exec("def double(x): return x * 2")
    result = session.eval("double(21)")
    assert result == 42


def test_data_injection(session):
    session.exec("bpy.context.active_object.name = new_name", new_name="TestCube")
    name = session.eval("bpy.context.active_object.name")
    assert name == "TestCube"


def test_error_handling(session):
    from unblended import BlenderError

    with pytest.raises(BlenderError, match="ZeroDivisionError"):
        session.exec("1 / 0")


def test_clear_scene(session):
    session.clear_scene()
    objects = session.list_objects()
    assert objects == []


# Allow running directly: python tests/test_smoke.py
if __name__ == "__main__":
    print("=== unblended smoke test ===")
    with BlenderSession() as b:
        ver = b.blender_version()
        print(f"Blender {ver}")

        assert b.ping()
        print("[OK] ping")

        b.exec("bpy.ops.mesh.primitive_cube_add(location=(1, 2, 3))")
        loc = b.eval("list(bpy.context.active_object.location)")
        assert loc == [1.0, 2.0, 3.0]
        print(f"[OK] cube at {loc}")

        b.exec("def double(x): return x * 2")
        assert b.eval("double(21)") == 42
        print("[OK] persistent namespace")

        b.exec("bpy.context.active_object.name = new_name", new_name="MyCube")
        assert b.eval("bpy.context.active_object.name") == "MyCube"
        print("[OK] data injection")

        try:
            b.exec("1 / 0")
            assert False, "Should have raised"
        except Exception as e:
            assert "ZeroDivisionError" in str(e)
            print("[OK] error handling")

        b.clear_scene()
        assert b.list_objects() == []
        print("[OK] clear scene")

    print("\n=== All tests passed ===")
