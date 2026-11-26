"""Render a Newton run in Blender Cycles: the UsdPhysics stage for the look, the Newton trajectory for the motion.

    python -I render_newton.py STAGE.usda TRAJ.npz OUT_DIR [--fps 30] [--res 1280x720] [--samples 48] [--seconds S]
                               [--azimuth 30] [--elevation 22] [--still-only] [--title TEXT]

Needs `bpy` (PyPI bpy==5.3.0, Python 3.13), which bundles `pxr`. TRAJ.npz is newton_run's output: poses[t, body, 7]
(position xyz, quaternion xyzw, in the stage's +Z-up frame), labels (body prim paths), dt and keep_every.

Look: every gprim gets a Principled BSDF from its displayColor (the X3D Material's diffuseColor, written by
x3d2usdphysics); a large matte floor under the lowest static shape; a sun, a soft key area light, a cool sky.
Camera: three-quarter, as the Foundry's reference stills (azimuth 30 deg, elevation 20-22 deg around the bounds of
everything that moves and everything static, up +Z), so stills compare across engines. Frames are PNG; ffmpeg makes
an H.264 mp4 (preset veryfast, CRF 20) and an animated WebP for the page.
"""
import math
import os
import subprocess
import sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector

A = sys.argv[1:]
opt = lambda k, d: A[A.index(k) + 1] if k in A else d
stage_path, traj_path, out = os.path.abspath(A[0]), os.path.abspath(A[1]), os.path.abspath(A[2])
FPS, SAMPLES = int(opt("--fps", 30)), int(opt("--samples", 48))
W, Hh = (int(x) for x in opt("--res", "1280x720").split("x"))
AZ, EL = math.radians(float(opt("--azimuth", 30))), math.radians(float(opt("--elevation", 22)))
TITLE = opt("--title", "")
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.usd_import(filepath=stage_path)
scn = bpy.context.scene

# --- materials from displayColor (Blender 5.3's USD import binds none for these gprims). The bpy wheel has no pxr,
# so newton_showcase.py writes <stage>.colours.json (gprim name -> displayColor) beside the stage ---
import json  # noqa: E402

cj = os.path.splitext(stage_path)[0] + ".colours.json"
colour = {k: tuple(v) for k, v in json.load(open(cj)).items()} if os.path.exists(cj) else {}
mats = {}


def mat_for(rgb):
    key = tuple(round(c, 3) for c in rgb)
    if key not in mats:
        m = bpy.data.materials.new(f"m{len(mats)}")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*key, 1)
        b.inputs["Roughness"].default_value = 0.38
        b.inputs["Specular IOR Level"].default_value = 0.5
        mats[key] = m
    return mats[key]


for o in bpy.data.objects:
    if o.type == "MESH":
        rgb = colour.get(o.name) or colour.get(o.name.split(".")[0]) or (0.75, 0.75, 0.78)
        o.data.materials.clear()
        o.data.materials.append(mat_for(rgb))
        for poly in o.data.polygons:
            poly.use_smooth = len(o.data.polygons) > 12        # spheres and cylinders smooth, boxes flat

# --- motion ---
T = np.load(traj_path, allow_pickle=True)
poses, labels = T["poses"], [str(x) for x in T["labels"]]
dt = float(T["dt"]) * int(T["keep_every"]) if "keep_every" in T else float(T["dt"])
secs = float(opt("--seconds", (len(poses) - 1) * dt))
nframes = max(1, int(secs * FPS) + 1)
by_name = {o.name: o for o in bpy.data.objects}
bodies = []
for k, path in enumerate(labels):
    o = by_name.get(path.rsplit("/", 1)[-1])
    if o is not None:
        o.rotation_mode = "QUATERNION"
        bodies.append((k, o))
for f in range(nframes):
    i = min(len(poses) - 1, int(round(f / FPS / dt)))
    for k, o in bodies:
        px, py, pz, qx, qy, qz, qw = (float(v) for v in poses[i, k])
        o.location = (px, py, pz)
        o.rotation_quaternion = Quaternion((qw, qx, qy, qz))
        o.keyframe_insert("location", frame=f + 1)
        o.keyframe_insert("rotation_quaternion", frame=f + 1)
scn.frame_start, scn.frame_end = 1, nframes

# --- bounds (all frames of the moving bodies, plus everything static) ---
pts = [o.matrix_world @ Vector(c) for o in bpy.data.objects if o.type == "MESH" for c in o.bound_box]
mov = poses[:, [k for k, _ in bodies], :3].reshape(-1, 3) if bodies else np.zeros((1, 3))
allp = np.vstack([np.array([tuple(p) for p in pts]), mov])
lo, hi = allp.min(0), allp.max(0)
flo = lo.copy()                                           # the floor goes under everything
if opt("--frame", "all") == "moving" and bodies:          # frame what moves (a big static table would fill the shot)
    lo, hi = mov.min(0) - 0.02, mov.max(0) + 0.02
ctr, rad = (lo + hi) / 2, float(np.linalg.norm(hi - lo)) / 2

# --- floor, lights, sky ---
zfloor = float(flo[2]) - 0.002
bpy.ops.mesh.primitive_plane_add(size=rad * 40, location=(ctr[0], ctr[1], zfloor))
floor = bpy.context.object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fb = fm.node_tree.nodes["Principled BSDF"]
fb.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1)
fb.inputs["Roughness"].default_value = 0.85
floor.data.materials.append(fm)
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy, sun.data.angle = 3.2, math.radians(4)
sun.rotation_euler = (math.radians(48), 0, math.radians(-35))
scn.collection.objects.link(sun)
key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "AREA"))
key.data.energy, key.data.size = 120 * rad * rad, rad * 1.5
key.location = (ctr[0] + rad * 1.8, ctr[1] - rad * 2.2, ctr[2] + rad * 2.4)
key.rotation_euler = (Vector(ctr) - key.location).to_track_quat("-Z", "Y").to_euler()
scn.collection.objects.link(key)
world = bpy.data.worlds.new("w")
scn.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
bg.inputs["Strength"].default_value = 0.55

# --- camera: three-quarter ---
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.data.lens_unit, cam.data.angle = "FOV", math.radians(38)
dist = 1.15 * rad / math.sin(math.radians(19))
d = Vector((math.sin(AZ) * math.cos(EL), -math.cos(AZ) * math.cos(EL), math.sin(EL)))
cam.location = Vector(ctr) + d * dist
cam.rotation_euler = (Vector(ctr) - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.clip_start, cam.data.clip_end = dist / 1000, dist * 50
scn.collection.objects.link(cam)
scn.camera = cam

# --- Cycles ---
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = SAMPLES
scn.cycles.use_denoising = True
scn.cycles.denoiser = "OPENIMAGEDENOISE"
scn.render.resolution_x, scn.render.resolution_y, scn.render.resolution_percentage = W, Hh, 100
scn.render.fps = FPS
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = "AgX - Medium High Contrast"
scn.render.film_transparent = False
scn.render.image_settings.file_format = "PNG"
if TITLE:
    scn.render.use_stamp = True
    for k in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_frame", "use_stamp_scene",
              "use_stamp_camera", "use_stamp_filename", "use_stamp_memory", "use_stamp_lens", "use_stamp_marker",
              "use_stamp_frame_range", "use_stamp_hostname"):
        if hasattr(scn.render, k):
            setattr(scn.render, k, False)
    scn.render.use_stamp_note = True
    scn.render.stamp_note_text = TITLE
    scn.render.stamp_font_size = max(14, Hh // 40)
if "--still-only" in A:
    frames = [nframes]
else:
    frames = range(1, nframes + 1)
for f in frames:
    scn.frame_set(f)
    scn.render.filepath = os.path.join(out, f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
if "--still-only" not in A and nframes > 1:
    base = os.path.basename(out.rstrip("/"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(out, "f%04d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    os.path.join(out, f"{base}.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(out, "f%04d.png"),
                    "-vf", f"fps=15,scale={min(W, 720)}:-1", "-loop", "0", "-quality", "70", os.path.join(out, f"{base}.webp")],
                   check=True)
print("rendered", len(list(frames)), "frames to", out)
