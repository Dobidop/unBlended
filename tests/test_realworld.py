"""
Real-world integration test: build a complete scene from scratch.

Creates a subdivided, deformed sphere with a procedural material,
places it on a textured ground plane, sets up lighting and camera,
and renders to output/.

Requires Blender to be installed and findable.

Run:  python tests/test_realworld.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unblended import BlenderSession

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_png = os.path.join(OUTPUT_DIR, "realworld_test.png")
    output_blend = os.path.join(OUTPUT_DIR, "realworld_test.blend")

    print("=== Real-world integration test ===\n")

    with BlenderSession() as b:
        print(f"Blender {b.blender_version()}\n")

        # 1. Clean slate
        b.clear_scene()
        print("[1] Scene cleared")

        # 2. Create a UV sphere and deform vertices with noise
        b.exec("""
import bpy, bmesh, math, random
random.seed(42)

bpy.ops.mesh.primitive_uv_sphere_add(
    radius=1.5, segments=32, ring_count=16, location=(0, 0, 1.5))
sphere = bpy.context.active_object
sphere.name = "DeformedSphere"

bm = bmesh.new()
bm.from_mesh(sphere.data)
for v in bm.verts:
    noise = random.uniform(-0.15, 0.15)
    v.co += v.normal * noise
bm.to_mesh(sphere.data)
bm.free()
sphere.data.update()
""")
        vert_count = b.eval("len(bpy.context.active_object.data.vertices)")
        print(f"[2] Created 'DeformedSphere' with {vert_count} vertices")

        # 3. Subdivision surface modifier
        b.exec("""
obj = bpy.data.objects["DeformedSphere"]
bpy.context.view_layer.objects.active = obj
mod = obj.modifiers.new(name="Subsurf", type='SUBSURF')
mod.levels = 2
mod.render_levels = 3
""")
        print("[3] Added subdivision surface modifier")

        # 4. Procedural rock material (noise + color ramp + bump)
        b.exec("""
import bpy

obj = bpy.data.objects["DeformedSphere"]
mat = bpy.data.materials.new(name="ProceduralRock")
mat.use_nodes = True
obj.data.materials.append(mat)

nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output     = nodes.new('ShaderNodeOutputMaterial')
principled = nodes.new('ShaderNodeBsdfPrincipled')
noise      = nodes.new('ShaderNodeTexNoise')
ramp       = nodes.new('ShaderNodeValToRGB')
bump       = nodes.new('ShaderNodeBump')
tex_coord  = nodes.new('ShaderNodeTexCoord')

output.location     = (600, 0)
principled.location = (300, 0)
ramp.location       = (0, 200)
noise.location      = (-250, 200)
bump.location       = (0, -200)
tex_coord.location  = (-500, 200)

noise.inputs['Scale'].default_value = 5.0
noise.inputs['Detail'].default_value = 8.0
noise.inputs['Roughness'].default_value = 0.7

elements = ramp.color_ramp.elements
elements[0].position = 0.3
elements[0].color = (0.15, 0.08, 0.03, 1)
elements[1].position = 0.7
elements[1].color = (0.45, 0.35, 0.25, 1)

principled.inputs['Roughness'].default_value = 0.85
principled.inputs['Specular IOR Level'].default_value = 0.3
bump.inputs['Strength'].default_value = 0.3

links.new(tex_coord.outputs['Object'], noise.inputs['Vector'])
links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
links.new(ramp.outputs['Color'], principled.inputs['Base Color'])
links.new(noise.outputs['Fac'], bump.inputs['Height'])
links.new(bump.outputs['Normal'], principled.inputs['Normal'])
links.new(principled.outputs['BSDF'], output.inputs['Surface'])
""")
        node_count = b.eval("len(bpy.data.materials['ProceduralRock'].node_tree.nodes)")
        print(f"[4] Procedural material with {node_count} shader nodes")

        # 5. Ground plane with checker texture
        b.exec("""
import bpy

bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
plane = bpy.context.active_object
plane.name = "Ground"

mat = bpy.data.materials.new(name="GroundMat")
mat.use_nodes = True
plane.data.materials.append(mat)

nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output     = nodes.new('ShaderNodeOutputMaterial')
principled = nodes.new('ShaderNodeBsdfPrincipled')
checker    = nodes.new('ShaderNodeTexChecker')
mapping    = nodes.new('ShaderNodeMapping')
tex_coord  = nodes.new('ShaderNodeTexCoord')

output.location     = (400, 0)
principled.location = (200, 0)
checker.location    = (-100, 0)
mapping.location    = (-300, 0)
tex_coord.location  = (-500, 0)

checker.inputs['Scale'].default_value = 8.0
checker.inputs['Color1'].default_value = (0.8, 0.8, 0.78, 1)
checker.inputs['Color2'].default_value = (0.3, 0.3, 0.28, 1)
principled.inputs['Roughness'].default_value = 0.6

links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
links.new(mapping.outputs['Vector'], checker.inputs['Vector'])
links.new(checker.outputs['Color'], principled.inputs['Base Color'])
links.new(principled.outputs['BSDF'], output.inputs['Surface'])
""")
        print("[5] Ground plane with checker texture")

        # 6. Three-point lighting
        b.exec("""
import bpy, math

bpy.ops.object.light_add(type='AREA', location=(4, -4, 6))
key = bpy.context.active_object
key.name = "KeyLight"
key.data.energy = 300
key.data.size = 3
key.rotation_euler = (math.radians(55), 0, math.radians(45))

bpy.ops.object.light_add(type='AREA', location=(-3, -2, 4))
fill = bpy.context.active_object
fill.name = "FillLight"
fill.data.energy = 100
fill.data.size = 5
fill.rotation_euler = (math.radians(60), 0, math.radians(-30))

bpy.ops.object.light_add(type='AREA', location=(0, 5, 3))
rim = bpy.context.active_object
rim.name = "RimLight"
rim.data.energy = 150
rim.data.size = 2
rim.rotation_euler = (math.radians(110), 0, 0)
""")
        print("[6] Three-point lighting")

        # 7. Camera
        b.exec("""
import bpy
from mathutils import Vector

bpy.ops.object.camera_add(location=(5, -5, 4))
cam = bpy.context.active_object
cam.name = "MainCamera"
direction = Vector((0, 0, 1.5)) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 50
bpy.context.scene.camera = cam
""")
        print("[7] Camera aimed at sphere")

        objects = b.list_objects()
        print(f"\n    Scene: {objects}")

        # 8. Render
        print(f"\n[8] Rendering ...")
        b.render(output_png, engine="CYCLES", samples=64, resolution=(1024, 1024), use_gpu=True)
        assert os.path.isfile(output_png), f"Render output not found: {output_png}"
        size_kb = os.path.getsize(output_png) / 1024
        print(f"[8] Rendered ({size_kb:.0f} KB)")

        # 9. Save .blend
        b.save_blend(output_blend)
        assert os.path.isfile(output_blend)
        print(f"[9] Saved .blend")

    print("\n=== Real-world test passed ===")


if __name__ == "__main__":
    main()
