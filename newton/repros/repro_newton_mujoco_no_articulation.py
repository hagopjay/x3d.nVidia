"""Newton 1.8.0 + MuJoCo 4.0.1 (CPU): a revolute joint with no UsdPhysics.ArticulationRootAPI belongs to no articulation
(joint_articulation == -1). SolverMuJoCo integrates the joint angle (joint_q) but no body pose (body_q) follows.
The same stage with ArticulationRootAPI on the bob moves the body.

Needs: newton[importers]==1.8.0 (newton-usd-schemas 0.8.0, Warp 1.19.0), mujoco==4.0.1. CPU only.
"""
import tempfile
from pathlib import Path

import newton
import numpy as np
import warp as wp
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics


def stage(path, root_on):
    st = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(st, "Z")
    UsdGeom.SetStageMetersPerUnit(st, 1.0)
    UsdGeom.Xform.Define(st, "/World")
    st.SetDefaultPrim(st.GetPrimAtPath("/World"))
    UsdPhysics.Scene.Define(st, "/World/PhysicsScene")
    pivot = UsdGeom.Xform.Define(st, "/World/Pivot")
    UsdGeom.Xformable(pivot).AddTranslateOp().Set(Gf.Vec3d(0, 0, 1))
    bob = UsdGeom.Xform.Define(st, "/World/Bob")
    UsdGeom.Xformable(bob).AddTranslateOp().Set(Gf.Vec3d(0.5, 0, 1))             # 0.5 m out from the pivot, level with it
    UsdPhysics.RigidBodyAPI.Apply(bob.GetPrim())
    UsdPhysics.MassAPI.Apply(bob.GetPrim()).CreateMassAttr(1.0)
    sph = UsdGeom.Sphere.Define(st, "/World/Bob/Sphere")
    sph.CreateRadiusAttr(0.05)
    UsdPhysics.CollisionAPI.Apply(sph.GetPrim())
    j = UsdPhysics.RevoluteJoint.Define(st, "/World/Joint")
    j.CreateBody0Rel().SetTargets([Sdf.Path("/World/Pivot")])
    j.CreateBody1Rel().SetTargets([Sdf.Path("/World/Bob")])
    j.CreateLocalPos0Attr(Gf.Vec3f(0, 0, 0))
    j.CreateLocalPos1Attr(Gf.Vec3f(-0.5, 0, 0))
    j.CreateAxisAttr("Y")
    j.CreateCollisionEnabledAttr(False)
    if root_on:
        UsdPhysics.ArticulationRootAPI.Apply(st.GetPrimAtPath(root_on))
    st.GetRootLayer().Save()


d = Path(tempfile.mkdtemp())
for k, (name, root_on) in enumerate((("no ArticulationRootAPI", None), ("ArticulationRootAPI on /World/Bob", "/World/Bob"),
                                     ("ArticulationRootAPI on /World/Joint", "/World/Joint"),
                                     ("ArticulationRootAPI on /World/Pivot", "/World/Pivot"))):
    p = str(d / f"s{k}.usda")
    stage(p, root_on)
    b = newton.ModelBuilder(up_axis=newton.Axis.Z)
    b.add_usd(p, apply_up_axis_from_stage=True)
    articulation = list(b.joint_articulation)
    model = b.finalize(device="cpu")
    solver = newton.solvers.SolverMuJoCo(model, use_mujoco_cpu=True)
    s0, s1, ctrl = model.state(), model.state(), model.control()
    newton.eval_fk(model, model.joint_q, model.joint_qd, s0)
    p0 = s0.body_q.numpy()[0][:3].copy()
    for _ in range(120):                                                         # 0.5 s at 1/240 s
        s0.clear_forces()
        solver.step(s0, s1, ctrl, None, 1.0 / 240.0)
        s0, s1 = s1, s0
    q = s0.joint_q.numpy()[0]
    newton.eval_fk(model, s0.joint_q, s0.joint_qd, s0)       # a pose follows joint_q only through forward kinematics
    p1 = s0.body_q.numpy()[0][:3]
    print(f"{name}: joint_articulation={articulation}  joint_q={q:.4f} rad  body displacement after eval_fk={np.linalg.norm(p1 - p0):.4f} m")
