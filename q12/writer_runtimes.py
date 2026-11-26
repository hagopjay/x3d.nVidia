"""Q12 run 2, stage 4: the writer's runtime variants, measured per target composition.

    python q12/writer_runtimes.py SCENES.txt OUT_DIR X3D_MCP/tests/usd_rules.json   # Python 3.12, usd-validation-nvidia 1.23.0 + tiers
    SCENES.txt: one "name path/to/scene.x3d" per line (the 21 PhysX-bridge scenes of x3d.loom/x3d.physics/physx-bridge/scenes)

Converts each scene with `--runtimes physx,newton,mujoco`, composes four targets (default = every variant set Disabled;
PhysX, Newton, MuJoCo = that set Enabled), flattens the three runtime targets, runs q12/run_simready.py on all four and
writes OUT_DIR/summary.json: failing scenes per requirement for the neutral writer, and for each target composition.

SimReady's rules are not gated by runtime, so on the unflattened asset a MuJoCo rule fails while Newton is selected and
the reverse (MUJOCO.COL.001 asks every collider for MjcCollisionAPI; RV.011 forbids it under Newton). The honest reading
is therefore per target: read a runtime's own requirements on its own composition, and RV.001-RV.011 on the default asset.
Gotcha (FM 402): Usd.Stage.Open shares root layers across stages, and SetVariantSelection writes to the edit target, which
defaults to the root layer; select in the session layer or the targets pollute each other.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
scenes, out, rules = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
shutil.rmtree(out, ignore_errors=True)
sys.path.insert(0, str(SRC))
from pxr import Usd  # noqa: E402
from x3dnv import x3d2usdphysics as xw  # noqa: E402

TARGETS = (("default", {}), ("physx", {"PhysX": "Enabled"}), ("newton", {"Newton": "Enabled"}), ("mujoco", {"MuJoCo": "Enabled"}))
reports = {}
for line in scenes.read_text().split("\n"):
    if not line.strip():
        continue
    name, path = line.split(None, 1)
    d = out / "asset" / name
    d.mkdir(parents=True)
    reports[name] = xw.convert(path.strip(), d / f"{name}.usda", runtimes=xw.RUNTIMES)
    for tgt, sel in TARGETS:
        t = out / "sr" / tgt / name
        if tgt == "default":
            shutil.copytree(d, t)
            continue
        t.mkdir(parents=True)
        st = Usd.Stage.Open(str(d / f"{name}.usda"))
        st.SetEditTarget(st.GetSessionLayer())
        for k, v in sel.items():
            st.GetDefaultPrim().GetVariantSets().GetVariantSet(k).SetVariantSelection(v)
        st.Flatten().Export(str(t / f"{name}.usda"))
res = out / "sr.json"
subprocess.run([sys.executable, "-I", str(HERE / "run_simready.py"), str(out / "sr"), str(rules), str(res)], check=True)
R = json.loads(res.read_text())


def fails(variant):
    c = collections.Counter()
    for s in R["variants"][variant].values():
        for k, v in s["verdicts"].items():
            if v == "fail":
                c[k] += 1
    return dict(sorted(c.items()))


summary = {"pins": R["pins"], "scenes": len(reports), "target_fail": {t: fails(t) for t, _ in TARGETS},
           "articulation_roots": {n: r["runtimes"]["articulation_roots"] for n, r in reports.items()},
           "joint_graphs": {n: r["runtimes"]["joint_graphs"] for n, r in reports.items()},
           "mujoco_refused_concave": {n: r["runtimes"].get("mujoco_refused_concave", []) for n, r in reports.items() if r["runtimes"].get("mujoco_refused_concave")}}
(out / "summary.json").write_text(json.dumps(summary, indent=1))
print(len(reports), "scenes; failing codes per target:", {t: len(v) for t, v in summary["target_fail"].items()})
