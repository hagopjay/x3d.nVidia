"""Simulate an X3D RigidBodyPhysics scene in Newton for a render: X3D -> UsdPhysics -> Newton -> trajectory.

    python newton_showcase.py SCENE.x3d OUT_DIR --solver xpbd --seconds 6 [--push FIRST:NEXT:SPEED] [--keep-every 8]

Writes OUT_DIR/<name>.usda (the stage, via x3dnv.x3d2usdphysics), <name>.<solver>.npz (poses every keep_every steps
of 1/240 s: 8 gives 30 frames per second), <name>.<solver>.json (bodies, steps, ms per step, trace_sha256 of every
step's hash, the writer's loss report).

--push gives body FIRST a horizontal velocity of SPEED m/s towards body NEXT at t = 0: the touch a viewer gives the
first domino ("push the first domino of each row to start"). It is recorded in the json; nothing else is changed.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from x3dnv import newton_run as nr  # noqa: E402
from x3dnv import x3d2usdphysics as xw  # noqa: E402

A = sys.argv[1:]
opt = lambda k, d: A[A.index(k) + 1] if k in A else d
src, out = Path(A[0]), Path(A[1])
out.mkdir(parents=True, exist_ok=True)
solver_name, secs, keep = opt("--solver", "xpbd"), float(opt("--seconds", 6)), int(opt("--keep-every", 8))
name = src.stem
if "--stage" in A:                     # a replay: the recorded stage, byte for byte (no new conversion)
    stage = Path(opt("--stage", ""))
    rep = {k: None for k in ("bodies", "dynamic", "static", "shapes", "joints", "kinematic_lost", "lost", "dropped_fields")}
else:
    stage = out / f"{name}.usda"
    rep = xw.convert(src, stage)
from pxr import Usd, UsdGeom  # noqa: E402
_st = Usd.Stage.Open(str(stage))
(out / f"{name}.colours.json").write_text(json.dumps({p.GetName(): list(UsdGeom.Gprim(p).GetDisplayColorAttr().Get()[0])
                                                     for p in _st.Traverse() if p.IsA(UsdGeom.Gprim) and UsdGeom.Gprim(p).GetDisplayColorAttr().Get()}))
model, solver, info = nr.build(stage, solver_name)
labels = nr.body_labels(model)
push = None
tip = "--tip" in A                       # FIRST:NEXT:OMEGA spins FIRST about the horizontal axis that tips it towards NEXT
if "--push" in A or tip:
    a, b, v = opt("--tip" if tip else "--push", "").split(":")
    ia = next(i for i, l in enumerate(labels) if l.endswith("/" + a))
    ib = next(i for i, l in enumerate(labels) if l.endswith("/" + b))
    q = model.body_q.numpy()
    d = q[ib, :3] - q[ia, :3]
    d[2] = 0
    d = d / np.linalg.norm(d)
    if tip:
        # a tip turns about the bottom edge, not the centre of mass: spin w about the horizontal axis that moves the
        # top towards NEXT, and the centre of mass (half the height above that edge) moving at w x r = w H/2 along d
        w = np.cross([0.0, 0.0, 1.0], d) * float(v)
        H_ = float(opt("--height", 0.0516))
        d = d * float(v) * H_ / 2
        push = {"body": a, "towards": b, "angular_velocity": w.tolist(), "velocity": d.tolist(), "kind": "tip about the bottom edge",
                "height": H_}
    else:
        d = d * float(v)
        push = {"body": a, "towards": b, "velocity": d.tolist(), "kind": "push"}


steps = int(secs * 240)
if push:
    # a free body's velocity lives in its free joint's coordinates (run() rebuilds body state from them by eval_fk);
    # Newton orders a free joint's velocity linear first, then angular
    j = int(np.nonzero(model.joint_child.numpy() == ia)[0][0])
    k = int(model.joint_qd_start.numpy()[j])
    qd = model.joint_qd.numpy()
    qd[k:k + 3] = d
    if tip:
        qd[k + 3:k + 6] = w
    model.joint_qd.assign(qd)
t0 = time.time()
P, V, hashes = nr.run(model, solver, steps, 1 / 240, keep_every=keep)
ms = (time.time() - t0) / steps * 1000
np.savez_compressed(out / f"{name}.{solver_name}.npz", poses=P, vels=V, labels=np.array(labels), dt=1 / 240, keep_every=keep)
import hashlib, platform  # noqa: E401,E402
import warp as _wp  # noqa: E402
meta = {"scene": str(src.name), "stage_sha256": hashlib.sha256(Path(stage).read_bytes()).hexdigest(),
        "host": f"cpython{platform.python_version()}-{platform.machine()}-warp{_wp.__version__}-cpu", "solver": solver_name, "bodies": int(model.body_count), "shapes": int(model.shape_count),
        "steps": steps, "ms_per_step": round(ms, 2), "trace_sha256": nr.trace_sha256(hashes), "push": push,
        "filters": info.get("filter_pairs_applied"), "articulations": info.get("articulations_added"),
        "writer": {k: rep[k] for k in ("bodies", "dynamic", "static", "shapes", "joints", "kinematic_lost", "lost", "dropped_fields")}}
(out / f"{name}.{solver_name}.json").write_text(json.dumps(meta, indent=1))
(out / f"{name}.{solver_name}.hashes.json").write_text(json.dumps(hashes))
print(json.dumps({k: meta[k] for k in ("scene", "solver", "bodies", "steps", "ms_per_step", "trace_sha256")}))
