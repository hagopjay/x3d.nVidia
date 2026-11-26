"""Q12 run 2, stage 1: X3D -> Blender 5.3 -> USD, in two orientations.

    python -I export_blender.py SCENES_DIR OUT_DIR ADDON_SOURCE_DIR RESULT.json [--only NAME ...]

Needs `bpy` (PyPI `bpy==5.3.0`, Python 3.13). ADDON_SOURCE_DIR is x3d-blender-io's `source/`.

Each scene is imported once with the add-on (X3D is +Y up; the add-on turns it into Blender's +Z up) and exported twice:
    z   Blender's own orientation, as the Foundry's convert writes it (x3d.lab blender_worker._export_usd):
        upAxis "Z", metersPerUnit 1, materials as UsdPreviewSurface, lights, cameras, instancing
    y   the same with convert_orientation on and up = +Y: what an X3D-minded exporter would write. SimReady's
        up-axis requirement wants Z, so this file is the negative control for that requirement.
A scene the add-on cannot import, or Blender cannot export, is recorded as an error, never skipped.
"""
import glob
import importlib
import json
import os
import sys
import tempfile
import time

args = [a for a in sys.argv[1:]]
only = set()
if "--only" in args:
    i = args.index("--only")
    only, args = set(args[i + 1:]), args[:i]
scenes, out, addon, dest = (os.path.abspath(a) for a in args[:4])
pkg = tempfile.mkdtemp()
os.symlink(addon, os.path.join(pkg, "io_scene_x3d"))
sys.path.insert(0, pkg)
import bpy  # noqa: E402

mod = importlib.import_module("io_scene_x3d")
mod.register()
os.makedirs(out, exist_ok=True)

LAB = dict(export_materials=True, generate_preview_surface=True, export_lights=True, export_cameras=True, use_instancing=True)
VARIANTS = {"z": dict(LAB), "y": dict(LAB, convert_orientation=True, export_global_up_selection="Y",
                                       export_global_forward_selection="NEGATIVE_Z")}


def counts():
    me = [o for o in bpy.data.objects if o.type == "MESH"]
    return {"objects": len(bpy.data.objects), "meshes": len(me),
            "faces": sum(len(o.data.polygons) for o in me), "verts": sum(len(o.data.vertices) for o in me),
            "materials": len(bpy.data.materials), "lights": sum(1 for o in bpy.data.objects if o.type == "LIGHT"),
            "cameras": sum(1 for o in bpy.data.objects if o.type == "CAMERA"),
            "images": len(bpy.data.images)}


ver = getattr(mod, "bl_info", {}).get("version")
res = {"blender": bpy.app.version_string, "addon_version": ".".join(map(str, ver)) if ver else None,
       "settings": VARIANTS, "scenes": {}}
if scenes.endswith(".json"):
    # a corpus list (select_real.py): {"root": ..., "scenes": {name: {"path": relative path}}}; real files are imported
    # where they are, so their textures and Inlines resolve
    corpus = json.load(open(scenes))
    pairs = [(n, os.path.join(corpus["root"], s["path"])) for n, s in sorted(corpus["scenes"].items())]
else:
    pairs = [(os.path.basename(f)[:-4], f) for f in sorted(glob.glob(os.path.join(scenes, "*.x3d")))]
files = pairs
for k, (n, f) in enumerate(pairs):
    if only and n not in only:
        continue
    row = {}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        mod.register()
    except Exception:
        pass
    try:
        t0 = time.time()
        r = bpy.ops.import_scene.x3d(filepath=f)
        row.update(import_=sorted(r), import_s=round(time.time() - t0, 3), counts=counts())
        for v, kw in VARIANTS.items():
            d = os.path.join(out, v, n)          # one asset per folder: SimReady NP.005 allows one USD file there
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"{n}.usdc")
            t0 = time.time()
            r2 = bpy.ops.wm.usd_export(filepath=p, **kw)
            row[v] = {"export": sorted(r2), "s": round(time.time() - t0, 3), "bytes": os.path.getsize(p) if os.path.exists(p) else 0}
            if "FINISHED" not in r2 or not row[v]["bytes"]:
                row.setdefault("error", f"{v}: export returned {sorted(r2)}")
    except Exception as e:
        row["error"] = str(e)[:300]
    res["scenes"][n] = row
    if k % 25 == 0:
        print(k, "/", len(files), n, "error" in row, flush=True)
json.dump(res, open(dest, "w"), indent=1)
bad = sum(1 for v in res["scenes"].values() if "error" in v)
print(bad, "errors of", len(res["scenes"]), "scenes; Blender", res["blender"], "add-on", res["addon_version"])
