"""Newton 1.8.0: add_usd makes no collision filter pair from FilteredPairsAPI, or from a joint with
physics:collisionEnabled = false, when one side is a static collider (a prim without RigidBodyAPI).

Needs: newton==1.8.0 (Warp 1.19.0), usd-core. CPU only. Prints the filter pairs add_usd produced.
"""
import tempfile
from pathlib import Path

import newton
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics


def stage(path, filtered_pairs_api, static_pivot):
    st = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(st, "Z")
    UsdGeom.SetStageMetersPerUnit(st, 1.0)
    UsdGeom.Xform.Define(st, "/World")
    st.SetDefaultPrim(st.GetPrimAtPath("/World"))
    UsdPhysics.Scene.Define(st, "/World/PhysicsScene")
    pivot = UsdGeom.Xform.Define(st, "/World/Pivot")
    UsdGeom.Xformable(pivot).AddTranslateOp().Set(Gf.Vec3d(0, 0, 1))
    if not static_pivot:
        UsdPhysics.RigidBodyAPI.Apply(pivot.GetPrim())
    box = UsdGeom.Cube.Define(st, "/World/Pivot/Box")
    box.CreateSizeAttr(0.05)
    UsdPhysics.CollisionAPI.Apply(box.GetPrim())
    bob = UsdGeom.Xform.Define(st, "/World/Bob")
    UsdGeom.Xformable(bob).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 1.0))      # the bob starts on the pivot
    UsdPhysics.RigidBodyAPI.Apply(bob.GetPrim())
    UsdPhysics.MassAPI.Apply(bob.GetPrim()).CreateMassAttr(1.0)
    sph = UsdGeom.Sphere.Define(st, "/World/Bob/Sphere")
    sph.CreateRadiusAttr(0.05)
    UsdPhysics.CollisionAPI.Apply(sph.GetPrim())
    j = UsdPhysics.RevoluteJoint.Define(st, "/World/Joint")
    j.CreateBody0Rel().SetTargets([Sdf.Path("/World/Pivot")])
    j.CreateBody1Rel().SetTargets([Sdf.Path("/World/Bob")])
    j.CreateAxisAttr("Y")
    j.CreateCollisionEnabledAttr(False)
    if filtered_pairs_api:
        api = UsdPhysics.FilteredPairsAPI.Apply(bob.GetPrim())
        api.CreateFilteredPairsRel().AddTarget(Sdf.Path("/World/Pivot"))
    st.GetRootLayer().Save()


d = Path(tempfile.mkdtemp())
for name, fp, static in (("static pivot, joint collisionEnabled=false + FilteredPairsAPI", True, True),
                         ("dynamic pivot, joint collisionEnabled=false + FilteredPairsAPI (control)", True, False)):
    p = str(d / f"s{int(static)}.usda")
    stage(p, fp, static)
    b = newton.ModelBuilder(up_axis=newton.Axis.Z)
    b.add_usd(p, apply_up_axis_from_stage=True)
    labels = {i: str(l) for i, l in enumerate(b.shape_label)}
    pairs = sorted((labels[a], labels[c]) for a, c in b.shape_collision_filter_pairs)
    print(f"{name}\n  shapes: {list(labels.values())}\n  filter pairs: {pairs}")
