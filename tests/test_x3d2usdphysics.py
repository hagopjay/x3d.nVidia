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


# ----------------------------------------------------------------------------- runtime variants (SimReady RV.*)
def applied(prim):
    """apiSchemas as authored: Usd.Prim.GetAppliedSchemas() drops names that no plugin registers (Newton*, Mjc*)."""
    lo = prim.GetMetadata("apiSchemas")
    return list(lo.GetAddedOrExplicitItems()) if lo else []


@pytest.fixture()
def asset(tmp_path):
    src = tmp_path / "p.x3d"
    src.write_text(SCENE.replace("<meta name='creator'", "<meta name='simready:qcode' content='Q111'/><meta name='simready:category' content='Toys'/><meta name='creator'"))
    d = tmp_path / "asset"
    d.mkdir()
    rep = xw.convert(src, d / "p.usda", runtimes=xw.RUNTIMES)

    def compose(**sel):
        st = Usd.Stage.Open(str(d / "p.usda"))
        st.SetEditTarget(st.GetSessionLayer())      # the root layer is shared by every stage in the process: never select there
        for k, v in sel.items():
            st.GetDefaultPrim().GetVariantSets().GetVariantSet(k).SetVariantSelection(v)
        return st
    return d, rep, compose


def test_default_composition_is_engine_neutral(asset):
    d, rep, compose = asset
    st = compose()
    root = st.GetDefaultPrim()
    assert [root.GetVariantSets().GetVariantSet(n).GetVariantSelection() for n in ("PhysX", "Newton", "MuJoCo")] == ["Disabled"] * 3
    schemas = {s for p in st.Traverse() for s in applied(p)}
    assert not [s for s in schemas if s.startswith(("Newton", "Mjc", "Physx"))]          # RV.011: nothing foreign in Standard
    assert not [p for p in st.Traverse() if p.HasAPI(UsdPhysics.DriveAPI, "angular")]    # a drive would owe MuJoCo an actuator
    assert (d / "runnables/physics/newton.usda").exists() and (d / "runnables/physics/mujoco.usda").exists()
    phys = st.GetRootLayer().customLayerData["SimReady_Metadata"]["Variants"]["Physics"]
    assert phys["Newton"] == {"prim": "/World", "variantSetName": "Newton", "activateOption": "Enabled"}
    assert set(phys) == {"PhysX", "Newton", "MuJoCo"}


def test_each_runtime_carries_only_its_own_schemas(asset):
    _, rep, compose = asset
    for sel, own, foreign in (("Newton", "Newton", ("Mjc", "Physx")), ("MuJoCo", "Mjc", ("Newton",)), ("PhysX", "Physx", ("Newton", "Mjc"))):
        st = compose(**{sel: "Enabled"})
        schemas = {s for p in st.Traverse() for s in applied(p)}
        assert not [s for s in schemas if s.startswith(foreign)], (sel, schemas)
    n, m = compose(Newton="Enabled"), compose(MuJoCo="Enabled")
    assert "NewtonCollisionAPI" in applied(n.GetPrimAtPath("/World/Bob/Sphere"))
    assert "MjcCollisionAPI" in applied(m.GetPrimAtPath("/World/Bob/Sphere"))
    assert "MjcJointAPI" in applied(m.GetPrimAtPath("/World/Joints/SingleAxisHingeJoint"))
    assert "MjcJointAPI" not in applied(n.GetPrimAtPath("/World/Joints/SingleAxisHingeJoint"))


def test_articulation_root_once_per_joint_graph_and_passive_drives(asset):
    _, rep, compose = asset
    st = compose()
    roots = [str(p.GetPath()) for p in st.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    assert roots == ["/World/Bob"] == rep["runtimes"]["articulation_roots"] and rep["runtimes"]["joint_graphs"] == 1
    hinge = "/World/Joints/SingleAxisHingeJoint"
    for sel in ("Newton", "PhysX"):                                     # DJ.004 and NEWTON.DJ.001 want a drive: declared passive
        s2 = compose(**{sel: "Enabled"})
        d = UsdPhysics.DriveAPI(s2.GetPrimAtPath(hinge), "angular")
        assert d.GetStiffnessAttr().Get() == 0 and d.GetDampingAttr().Get() == 0 and d.GetMaxForceAttr().Get() > 1e30
    sm, sp, sn = compose(MuJoCo="Enabled"), compose(PhysX="Enabled"), compose(Newton="Enabled")
    assert not sm.GetPrimAtPath(hinge).HasAPI(UsdPhysics.DriveAPI, "angular")
    assert "PhysicsJointStateAPI:angular" in applied(sp.GetPrimAtPath(hinge))
    assert sn.GetPrimAtPath("/World/Bob").GetAttribute("newton:selfCollisionEnabled").Get() is False


def test_neutral_layer_authors_no_approximation_none(tmp_path):
    """A local opinion outranks every payload, so a neutral 'none' would pin the approximation for every runtime."""
    src = tmp_path / "m.x3d"
    src.write_text("""<X3D profile='Full' version='4.0'><Scene><RigidBodyCollection>
 <RigidBody DEF='F' containerField='bodies' fixed='true'><CollidableShape DEF='FC' containerField='geometry'><Shape containerField='shape'>
  <IndexedFaceSet coordIndex='0 1 2 -1 0 2 3 -1'><Coordinate point='0 0 0 1 0 0 1 0 1 0 0 1'/></IndexedFaceSet></Shape></CollidableShape></RigidBody>
 <CollisionCollection containerField='collider'><CollidableShape USE='FC' containerField='collidables'/></CollisionCollection>
</RigidBodyCollection></Scene></X3D>""")
    (tmp_path / "a").mkdir()
    rep = xw.convert(src, tmp_path / "a" / "m.usda", runtimes=("newton", "mujoco"))
    st = Usd.Stage.Open(str(tmp_path / "a" / "m.usda"))
    mesh = next(p for p in st.Traverse() if p.IsA(UsdGeom.Mesh))
    assert not mesh.GetAttribute("physics:approximation").HasAuthoredValue()
    st.SetEditTarget(st.GetSessionLayer())
    st.GetDefaultPrim().GetVariantSets().GetVariantSet("Newton").SetVariantSelection("Enabled")
    assert "NewtonSDFCollisionAPI" in applied(st.GetPrimAtPath(mesh.GetPath())) and rep["runtimes"]["sdf_meshes"] == 1
    assert rep["runtimes"]["mujoco_refused_concave"]              # a convex hull would fill a bowl: refused, reported


def test_simready_metadata_profile_round_trip(asset):
    _, rep, compose = asset
    st = compose()
    md = st.GetRootLayer().customLayerData["SimReady_Metadata"]
    assert md["qcode"] == "Q111" and md["category"] == "Toys" and md["author"] == "tests" and md["asset_license"] == "Apache-2.0"
    assert rep["meta_missing"] == []


# ---------------------------------------------------------------- the X3D SimReady profile, draft 2
PROFILE = """<?xml version='1.0' encoding='UTF-8'?><X3D profile='Full' version='4.0'><head>
<unit category='length' name='centimetre' conversionFactor='0.01'/>
<meta name='title' content='labelled'/><meta name='Image' content='pic.png'/></head><Scene>
<RigidBodyCollection>
 <RigidBody DEF='Crate' containerField='bodies'>
  <MetadataSet containerField='metadata' name='semantics:labels'><MetadataString containerField='value' name='coco' value='"chair" "bench"'/></MetadataSet>
  <CollidableShape containerField='geometry'><Shape containerField='shape'>
   <MetadataSet containerField='metadata' name='semantics:labels'><MetadataString containerField='value' name='wikidata_qcode' value='"Q15026"'/>
    <MetadataString containerField='value' name='affordance'/></MetadataSet>
   <Appearance><Material diffuseColor='0 1 0'><MetadataSet containerField='metadata' name='semantics:labels'>
    <MetadataString containerField='value' name='material' value='"wood"'/></MetadataSet></Material></Appearance>
   <IndexedFaceSet coordIndex='0 2 1 -1 0 1 3 -1 0 3 2 -1 1 2 3 -1'><Coordinate point='0 0 0 100 0 0 0 100 0 0 0 100'/></IndexedFaceSet>
  </Shape></CollidableShape></RigidBody>
 <RigidBody DEF='Plain' containerField='bodies' position='300 0 0'>
  <CollidableShape containerField='geometry'><Shape containerField='shape'>
   <Appearance><Material diffuseColor='0 1 0'/></Appearance><Sphere radius='50'/></Shape></CollidableShape></RigidBody>
</RigidBodyCollection></Scene></X3D>"""
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (256).to_bytes(4, "big") + (256).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")


@pytest.fixture()
def profile(tmp_path):
    src = tmp_path / "in" / "crate.x3d"
    src.parent.mkdir()
    src.write_text(PROFILE)
    (src.parent / "pic.png").write_bytes(PNG)
    out = tmp_path / "out" / "crate.usda"
    out.parent.mkdir()
    rep = xw.convert(src, out)
    return Usd.Stage.Open(str(out)), rep, out


def labels(prim, tax):
    assert f"SemanticsLabelsAPI:{tax}" in prim.GetAppliedSchemas()
    return list(prim.GetAttribute(f"semantics:labels:{tax}").Get())


def test_labels_ride_on_the_prim_their_x3d_node_becomes(profile):
    st, rep, _ = profile
    assert labels(st.GetPrimAtPath("/World/Crate"), "coco") == ["chair", "bench"]
    mesh = st.GetPrimAtPath("/World/Crate/IndexedFaceSet")
    assert labels(mesh, "wikidata_qcode") == ["Q15026"]
    assert labels(mesh, "affordance") == []                    # written with no value in the X3D: applied and empty, not dropped
    assert not [s for s in st.GetPrimAtPath("/World/Plain/Sphere").GetAppliedSchemas() if s.startswith("Semantics")]
    assert rep["labels"] == 4


def test_a_labelled_material_is_not_merged_with_an_unlabelled_one_of_the_same_colour(profile):
    st, _, _ = profile
    mats = [p for p in st.GetPrimAtPath("/World/Looks").GetChildren()]
    assert len(mats) == 2
    assert sorted(len([s for s in m.GetAppliedSchemas() if s == "SemanticsLabelsAPI:material"]) for m in mats) == [0, 1]


def test_the_stage_unit_is_the_x3d_unit_and_points_are_not_rescaled(profile):
    st, rep, _ = profile
    assert UsdGeom.GetStageMetersPerUnit(st) == pytest.approx(0.01) and rep["meters_per_unit"] == pytest.approx(0.01)
    pts = UsdGeom.Mesh(st.GetPrimAtPath("/World/Crate/IndexedFaceSet")).GetPointsAttr().Get()
    assert max(max(p) for p in pts) == 100
    ext = st.GetRootLayer().customLayerData["SimReady_Metadata"]["asset_extents"]
    assert max(ext) < 10                                        # extents are reported in metres whatever the unit


def test_the_named_picture_becomes_the_simready_thumbnail(profile, tmp_path):
    _, rep, out = profile
    thumb = out.parent / ".thumbs" / "256x256" / "crate.usda.png"
    assert thumb.read_bytes() == PNG and rep["thumbnail"].startswith("pic.png copied")
    src = tmp_path / "in" / "crate.x3d"
    src.write_text(PROFILE.replace("pic.png", "../elsewhere.png"))
    rep2 = xw.convert(src, tmp_path / "out2.usda")
    assert "not copied" in rep2["thumbnail"] and not (tmp_path / ".thumbs" / "256x256" / "out2.usda.png").exists()
