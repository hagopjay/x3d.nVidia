"""Write a loom.physics-run/1 record for Newton (one per solver), for x3d.loom's physics witness.

    python newton_record.py --solver xpbd --refs REFS.json --rec DIR --replay HOST=DIR [--replay HOST=DIR ...]
                            --stage STAGE.usda --root REPO --out REPO/newton/runs/NAME.physics.json [--scene X3D]

REFS.json is x3dnv.newton_refs' output (the nine PhysX references and three controls, measured on this solver).
--rec is newton_showcase.py's output directory for the recorded run (its .json and .hashes.json); each --replay is the
same run, replayed from the same stage in a fresh process on HOST. The record's model is the stage, by path (relative
to --root) and sha256, so the witness can see the stage is the one the run used (law 17).

Nothing here judges: it copies numbers. Every reference keeps the PhysX bridge's declared limit; a reference Newton
misses stays a miss, and the witness says PHYS_REFERENCE_FAIL.
"""
import glob
import hashlib
import json
import sys
from pathlib import Path

A = sys.argv[1:]
opt = lambda k, d=None: A[A.index(k) + 1] if k in A else d
solver = opt("--solver")
refs = json.loads(Path(opt("--refs")).read_text())
root = Path(opt("--root")).resolve()
stage = Path(opt("--stage")).resolve()


def load_run(d):
    d = Path(d)
    meta = json.loads(next(iter(sorted(d.glob(f"*.{solver}.json")))).read_text())
    hashes = json.loads(next(iter(sorted(d.glob(f"*.{solver}.hashes.json")))).read_text())
    return meta, hashes


def trace(h):
    return hashlib.sha256(",".join(str(x) for x in h).encode()).hexdigest()


rec_meta, rec_h = load_run(opt("--rec"))
replays = []
for i, a in enumerate(A):
    if a == "--replay":
        host, d = A[i + 1].split("=", 1)
        m, h = load_run(d)
        mism = [k for k, (x, y) in enumerate(zip(rec_h, h)) if x != y] + ([-2] if len(h) != len(rec_h) else [])
        replays.append({"host": host, "host_version": m["host"], "steps": len(h), "mismatches": len(mism),
                        "first_mismatch": mism[0] if mism else -1, "trace_sha256": trace(h), "ms_per_step": m["ms_per_step"],
                        "engine_version": "1.8.0", "stage_sha256": m.get("stage_sha256")})
assert rec_meta["trace_sha256"] == trace(rec_h)
dropped = rec_meta.get("writer", {}).get("dropped_fields") or []
engine_build = {"xpbd": "SolverXPBD(iterations=10, enable_restitution=True)",
                "mujoco": "SolverMuJoCo(use_mujoco_cpu=True), MuJoCo 4.0.1"}[solver]
run = {
    "schema": "loom.physics-run/1",
    "id": f"x3d.nVidia/newton-{solver}/dominoes-spiral",
    "engine": {"name": "Newton", "version": "1.8.0", "build": f"warp-lang 1.19.0 (CPU); {engine_build}"},
    "project": {"name": "x3d.nVidia/newton", "contract": "x3dnv.x3d2usdphysics (X3D 4.0 RigidBodyPhysics -> UsdPhysics) + newton.ModelBuilder.add_usd"},
    "model": {"path": str(stage.relative_to(root)), "sha256": hashlib.sha256(stage.read_bytes()).hexdigest(),
              "source": opt("--scene", "dominoes-spiral.x3d"), "what": "the UsdPhysics stage the run loaded, written from the X3D by x3d2usdphysics"},
    "inputs": {"push": rec_meta.get("push"), "why": "the touch a viewer gives the first domino ('push the first domino of each row to start')"},
    "recorded": {"host": "cpython3.13", "host_version": rec_meta["host"], "steps": len(rec_h), "fixed_step_s": 1 / 240,
                 "hashes": rec_h, "trace_sha256": trace(rec_h), "ms_per_step": rec_meta["ms_per_step"]},
    "replays": replays,
    "required_hosts": sorted({r["host"] for r in replays}),
    "references": [{k: r[k] for k in ("id", "observed", "limit", "declared_limit", "rule", "status", "source")} | {"detail": r.get("detail")}
                   for r in refs["references"]],
    "controls": [{k: c[k] for k in c} for c in refs["controls"]],
    "losses": {"authored_fields_dropped": len(dropped), "reported": True, "fields": dropped,
               "source": "x3d2usdphysics loss report (ODE-only fields have no UsdPhysics or Newton counterpart)"},
    "substep_sweep": refs.get("substep_sweep"),
    "not_shown": ["a GPU (every run is Warp on the CPU; a CUDA host needs its own replay, law 42)",
                  "another machine (both hosts ran in one Linux container)",
                  "the X3D bridge's own browser hosts: Newton runs beside them, not inside X_ITE"],
    "sources": {"references": "x3dnv.newton_refs (set-ups and limits from physx-bridge evidence/p1-analytic.json)",
                "trace": "tools/newton_showcase.py", "replays": "tools/newton_showcase.py --stage (fresh process per host)"},
}
out = Path(opt("--out"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(run, indent=1))
fails = [r["id"] for r in run["references"] if r["status"] != "pass"]
print(out.name, "steps", len(rec_h), "replays", [(r["host"], r["mismatches"]) for r in replays], "reference misses", len(fails))
