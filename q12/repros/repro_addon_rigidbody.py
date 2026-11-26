"""x3d-blender-io: two RigidBodyPhysics import defects, measured on Blender 5.3.0 (PyPI bpy) with the add-on checked out
at the commit passed as ADDON_SOURCE_DIR (x3d-blender-io `source/`).

    python repro_addon_rigidbody.py ADDON_SOURCE_DIR

(1) A RigidBody's CollidableShape sits at the origin: RigidBody.position is ignored.
(2) A RigidBody that a joint reaches through USE is imported twice.
"""
import importlib
import os
import sys
import tempfile

import bpy

addon = os.path.abspath(sys.argv[1])
pkg = tempfile.mkdtemp()
os.symlink(addon, os.path.join(pkg, "io_scene_x3d"))
sys.path.insert(0, pkg)
importlib.import_module("io_scene_x3d").register()

X3D = """<?xml version="1.0" encoding="UTF-8"?><X3D profile="Full" version="4.0"><Scene>
<RigidBodyCollection gravity="0 -9.8 0">
 <RigidBody DEF="Pivot" containerField="bodies" position="0 5 0" fixed="true">
  <CollidableShape containerField="geometry"><Shape containerField="shape"><Box size="0.2 0.2 0.2"/></Shape></CollidableShape></RigidBody>
 <RigidBody DEF="Bob" containerField="bodies" position="3 5 0" mass="1">
  <CollidableShape containerField="geometry"><Shape containerField="shape"><Sphere radius="0.3"/></Shape></CollidableShape></RigidBody>
 <BallJoint containerField="joints" anchorPoint="0 5 0"><RigidBody USE="Bob" containerField="body1"/><RigidBody USE="Pivot" containerField="body2"/></BallJoint>
</RigidBodyCollection></Scene></X3D>"""
p = os.path.join(tempfile.mkdtemp(), "rb.x3d")
open(p, "w").write(X3D)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.x3d(filepath=p)
print("Blender", bpy.app.version_string)
print("objects:", [(o.name, o.type, tuple(round(v, 3) for v in o.matrix_world.translation)) for o in bpy.data.objects])
print("expected: two objects, a Box near Blender (0, -0, 5) and a Sphere near (3, -0, 5) (X3D +Y up becomes Blender +Z up)")
print("found:    four objects, every one at (0, 0, 0): position ignored, and each USE'd body imported twice")
