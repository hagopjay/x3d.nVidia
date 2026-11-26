"""x3d2usdphysics: X3D RigidBodyPhysics written as UsdPhysics (needs usd-core and lxml; skipped without them)."""
import math

import pytest

pytest.importorskip("pxr")
pytest.importorskip("lxml")

from pxr import Usd, UsdGeom, UsdPhysics  # noqa: E402

from x3dnv import x3d2usdphysics as xw  # noqa: E402

SCENE = """<?xml version='1.0' encoding='UTF-8'?><X3D profile='Full' version='4.0'><head>
<meta name='title' content='pendulum test'/><meta name='creator' content='tests'/><meta name='license' content='Apache-2.0'/></head><Scene>
<RigidBodyCollection gravity='0 -9.81 0'>
 <RigidBody DEF='Pivot' containerField='bodies' position='0 1 0' fixed='true'>
  <CollidableShape DEF='PivotC' containerField='geometry'><Shape containerField='shape'><Box size='0.02 0.02 0.02'/></Shape></CollidableShape></RigidBody>
 <RigidBody DEF='Bob' containerField='bodies' position='0.5 1 0' mass='2' linearVelocity='0 0 1'>
  <CollidableOffset containerField='geometry' translation='0 0.1 0'>
   <CollidableShape DEF='BobC' containerField='collidable'><Shape containerField='shape'>
    <Appearance><Material diffuseColor='1 0 0'/></Appearance><Sphere radius='0.05'/></Shape></CollidableShape></CollidableOffset></RigidBody>
 <SingleAxisHingeJoint containerField='joints' anchorPoint='0 1 0' axis='0 0 1' minAngle='-1' maxAngle='1'>
  <RigidBody USE='Bob' containerField='body1'/><RigidBody USE='Pivot' containerField='body2'/></SingleAxisHingeJoint>
 <MotorJoint containerField='joints'><RigidBody USE='Bob' containerField='body1'/></MotorJoint>
 <CollisionCollection containerField='collider' appliedParameters='"BOUNCE" "FRICTION_COEFFICIENT-2"' bounce='0.6' minBounceSpeed='0.01' frictionCoefficients='0.3 0.3'>
  <CollidableShape USE='PivotC' containerField='collidables'/><CollidableShape USE='BobC' containerField='collidables'/></CollisionCollection>
</RigidBodyCollection></Scene></X3D>"""


@pytest.fixture()
def stage(tmp_path):
    src = tmp_path / "p.x3d"
    src.write_text(SCENE)
    rep = xw.convert(src, tmp_path / "p.usda")
    return Usd.Stage.Open(str(tmp_path / "p.usda")), rep


def test_frame_is_z_up_with_no_root_rotation(stage):
    st, _ = stage
    assert UsdGeom.GetStageUpAxis(st) == "Z"
    assert UsdGeom.GetStageMetersPerUnit(st) == 1.0
    bob = UsdGeom.Xformable(st.GetPrimAtPath("/World/Bob")).ComputeLocalToWorldTransform(0).ExtractTranslation()
    assert tuple(round(v, 6) for v in bob) == (0.5, 0.0, 1.0)          # X3D (x, y, z) -> USD (x, -z, y)
    assert not UsdGeom.Xformable(st.GetPrimAtPath("/World")).GetOrderedXformOps()


def test_bodies_shapes_and_offsets(stage):
    st, rep = stage
    assert st.GetPrimAtPath("/World/Bob").HasAPI(UsdPhysics.RigidBodyAPI)
    assert not st.GetPrimAtPath("/World/Pivot").HasAPI(UsdPhysics.RigidBodyAPI)     # fixed: a static collider
    assert UsdPhysics.MassAPI(st.GetPrimAtPath("/World/Bob")).GetMassAttr().Get() == 2
    v = UsdPhysics.RigidBodyAPI(st.GetPrimAtPath("/World/Bob")).GetVelocityAttr().Get()
    assert tuple(round(x, 6) for x in v) == (0.0, -1.0, 0.0)
    sph = st.GetPrimAtPath("/World/Bob/Sphere")
    assert sph and sph.HasAPI(UsdPhysics.CollisionAPI)
    t = UsdGeom.Xformable(sph).ComputeLocalToWorldTransform(0).ExtractTranslation()
    assert tuple(round(x, 6) for x in t) == (0.5, 0.0, 1.1)             # the CollidableOffset's +0.1 in X3D y
    assert rep["shapes"] == 2 and rep["dynamic"] == 1 and rep["static"] == 1


def test_joint_axis_limits_and_filter(stage):
    st, rep = stage
    j = UsdPhysics.RevoluteJoint(st.GetPrimAtPath("/World/Joints/SingleAxisHingeJoint"))
    assert j.GetAxisAttr().Get() == "X"
    assert math.isclose(j.GetLowerLimitAttr().Get(), math.degrees(-1), rel_tol=1e-6)
    assert j.GetCollisionEnabledAttr().Get() is False
    bob = st.GetPrimAtPath("/World/Bob")
    assert [str(p) for p in UsdPhysics.FilteredPairsAPI(bob).GetFilteredPairsRel().GetTargets()] == ["/World/Pivot"]
    assert any(l["node"] == "MotorJoint" for l in rep["lost"])          # reported, never dropped in silence
    assert "CollisionCollection.minBounceSpeed" in rep["dropped_fields"]


def test_material_and_simready_provenance(stage):
    st, rep = stage
    mats = [p for p in st.Traverse() if p.HasAPI(UsdPhysics.MaterialAPI)]
    assert len(mats) == 1
    m = UsdPhysics.MaterialAPI(mats[0])
    assert math.isclose(m.GetRestitutionAttr().Get(), 0.6, rel_tol=1e-6)
    assert math.isclose(m.GetStaticFrictionAttr().Get(), 0.3, rel_tol=1e-6)
    cld = st.GetRootLayer().customLayerData
    md = cld["SimReady_Metadata"]
    assert md["asset_name"] == "pendulum test" and md["author"] == "tests" and md["asset_license"] == "Apache-2.0"
    assert md["rigid_body_count"] == 1 and math.isclose(md["mass"], 2.0)
    assert cld["asset_type"] == "articulated"
    assert "qcode" in rep["meta_missing"] and "category" in rep["meta_missing"]   # absent in X3D: never invented
