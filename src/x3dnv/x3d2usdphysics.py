"""X3D RigidBodyPhysics -> OpenUSD UsdPhysics, written directly (no Blender).

    python -I -m x3dnv.x3d2usdphysics SCENE.x3d OUT.usda [--runtimes physx,newton,mujoco] [--report REPORT.json] [--meta key=value ...]

Why: Blender's X3D import keeps no physics, so a Blender USD export of an X3D physics scene has no rigid body at all
(SimReady RB.001 fails on all 225 Blender exports of Q12 run 2), and Newton, Isaac Sim and every SimReady physics
requirement see nothing. This writer carries the physics itself.

Mapping, following the PhysX bridge's SPEC.md (x3d.loom/x3d.physics/physx-bridge) wherever X3D leaves a choice:
    frame        X3D is +Y up; USD is written +Z up (SimReady UN.006, Newton's default): every point, vector, quaternion and
                 inertia tensor is rotated by +90 deg about X, (x, y, z) -> (x, -z, y). The root prim carries no rotation
                 (SimReady VG.025). metersPerUnit 1, kilogramsPerUnit 1.
    RigidBodyCollection.gravity        PhysicsScene gravityDirection / gravityMagnitude
    RigidBody (fixed FALSE)            Xform + RigidBodyAPI + MassAPI; position, orientation, linear velocity, angular
                                       velocity (USD wants degrees per second); mass; centerOfMass; inertia, diagonalised
                                       into principal axes (MassAPI diagonalInertia + principalAxes), unless it is the
                                       default identity, which is computed from the shapes (as the PhysX bridge and X_ITE)
    RigidBody (fixed TRUE)             Xform with colliders and no RigidBodyAPI: a static collider. A fixed body moved by
                                       a ROUTE (a kinematic path) is reported as lost
    CollidableShape / CollidableOffset Sphere, Box (Cube + scale), Cylinder, Cone (axis Z), IndexedFaceSet and
                                       IndexedTriangleSet (Mesh + MeshCollisionAPI: none when static, convexHull when
                                       dynamic), with their translation and rotation; their Shape's appearance becomes a
                                       UsdPreviewSurface material, so the same prim is drawn and collides
    CollisionCollection (the collider) its collidables collide (CollisionAPI); the others do not (collisionEnabled 0).
                                       bounce -> restitution, frictionCoefficients[0] -> static and dynamic friction
    BallJoint                          PhysicsSphericalJoint at the world anchorPoint
    SingleAxisHingeJoint               PhysicsRevoluteJoint about the world axis, limits from minAngle/maxAngle (none when
                                       the range is the full -pi..pi)
    SliderJoint                        PhysicsPrismaticJoint along the world axis, limits min/maxSeparation relative to the
                                       start (none when min > max, as X3D says)
    DoubleAxisHingeJoint, UniversalJoint, MotorJoint, CollisionSensor, and ODE-only fields   reported as lost
The X3D SimReady profile (docs/SIMREADY-X3D-PROFILE.md, draft 2) is carried as written, never repaired:
    <unit category='length'>           metersPerUnit is the X3D conversionFactor (points are not rescaled), so a file in
                                       centimetres is a USD stage in centimetres and SimReady UN.007 sees it
    MetadataSet "semantics:labels"     each MetadataString in it becomes SemanticsLabelsAPI:<name> with token[]
                                       semantics:labels:<name>: on a RigidBody (its Xform), a CollidableShape or Shape (the
                                       gprim), an Appearance or its material (the UsdShade Material). A label with no value
                                       is written applied and empty, as the X3D says
    <meta name='Image'>                a PNG beside the scene is copied to .thumbs/256x256/<out file>.png (SR.002); it is
                                       not resized, and its size is reported when it is not 256 x 256
X3D <head> meta and the physics become SimReady provenance (customLayerData SimReady_Metadata, SR.001/003/004):
asset_name (title), author (creator or author), asset_license (license or rights), category, qcode (a Wikidata Q
code), asset_type, source_file, usd_date_generated, rigid_body_count, asset_extents, mass. A field X3D does not carry
stays absent and is listed in the report; it is never invented. --meta adds or overrides fields.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from lxml import etree
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt

# +90 deg about X: X3D (+Y up) to USD (+Z up)
C = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
QC = np.array([math.cos(math.pi / 4), math.sin(math.pi / 4), 0.0, 0.0])           # w x y z
GEOMS = ("Sphere", "Box", "Cylinder", "Cone", "IndexedFaceSet", "IndexedTriangleSet")
ODE_ONLY = {"RigidBody": ("finiteRotationAxis", "useFiniteRotation", "autoDisable", "disableAngularSpeed", "disableLinearSpeed",
                          "disableTime", "autoDamp", "angularDampingFactor", "linearDampingFactor", "forces", "torques"),
            "RigidBodyCollection": ("constantForceMix", "contactSurfaceThickness", "errorCorrection", "maxCorrectionSpeed",
                                    "autoDisable", "disableAngularSpeed", "disableLinearSpeed", "disableTime"),
            "CollisionCollection": ("minBounceSpeed", "slipFactors", "softnessConstantForceMix", "softnessErrorCorrection",
                                    "surfaceSpeed"),
            "SingleAxisHingeJoint": ("stopBounce", "stopErrorCorrection")}


# X3D's default containerField per node type (X3D 4.0 XML encoding), for children that do not say theirs
DEFAULT_FIELD = {"Coordinate": "coord", "CoordinateDouble": "coord", "Normal": "normal", "Color": "color", "ColorRGBA": "color",
                 "TextureCoordinate": "texCoord", "Appearance": "appearance", "Material": "material",
                 "PhysicalMaterial": "material", "UnlitMaterial": "material", "TwoSidedMaterial": "material",
                 "RigidBody": "bodies", "BallJoint": "joints", "SingleAxisHingeJoint": "joints", "SliderJoint": "joints",
                 "DoubleAxisHingeJoint": "joints", "UniversalJoint": "joints", "MotorJoint": "joints",
                 "CollisionCollection": "collider", **{g: "geometry" for g in ("Sphere", "Box", "Cylinder", "Cone",
                 "IndexedFaceSet", "IndexedTriangleSet")}}


def v3(s, d=(0.0, 0.0, 0.0)):
    if s is None:
        return np.array(d, float)
    a = [float(x) for x in s.replace(",", " ").split()]
    return np.array((a + list(d))[:3], float)


def nums(s):
    return [float(x) for x in (s or "").replace(",", " ").split()]


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def axis_angle(s):
    """X3D SFRotation 'x y z a' -> quaternion w x y z (identity for a zero axis)."""
    a = nums(s) or [0, 0, 1, 0]
    ax, ang = np.array(a[:3], float), a[3] if len(a) > 3 else 0.0
    n = np.linalg.norm(ax)
    if n < 1e-12 or abs(ang) < 1e-15:
        return np.array([1.0, 0, 0, 0])
    ax = ax / n
    return np.array([math.cos(ang / 2), *(math.sin(ang / 2) * ax)])


def qrot(q, v):
    return qmul(qmul(q, np.array([0.0, *v])), qconj(q))[1:]


def to_usd_q(q):
    return qmul(qmul(QC, q), qconj(QC))


def quat_from_x_to(n):
    """Rotation taking +X to the unit vector n (w x y z)."""
    x = np.array([1.0, 0, 0])
    n = n / np.linalg.norm(n)
    d = float(np.dot(x, n))
    if d > 1 - 1e-12:
        return np.array([1.0, 0, 0, 0])
    if d < -1 + 1e-12:
        return np.array([0.0, 0, 0, 1.0])
    ax = np.cross(x, n)
    q = np.array([1 + d, *ax])
    return q / np.linalg.norm(q)


def gfq(q):
    return Gf.Quatf(float(q[0]), Gf.Vec3f(*map(float, q[1:])))


def gfv(v):
    return Gf.Vec3f(*map(float, v))


class Scene:
    def __init__(self, path):
        self.path = Path(path)
        root = etree.parse(str(path), etree.XMLParser(remove_comments=True, huge_tree=True)).getroot()
        self.root = root
        self.defs = {e.get("DEF"): e for e in root.iter() if isinstance(e.tag, str) and e.get("DEF")}
        self.lost = []

    def res(self, e):
        """Follow USE to the DEF'd node."""
        if e is not None and e.get("USE"):
            return self.defs.get(e.get("USE"))
        return e

    def kids(self, e, field=None, tag=None):
        out = []
        for c in e:
            if not isinstance(c.tag, str):
                continue
            if field and c.get("containerField", DEFAULT_FIELD.get(c.tag)) != field:
                continue
            r = self.res(c)
            if r is None or (tag and r.tag not in (tag if isinstance(tag, tuple) else (tag,))):
                continue
            out.append(r)
        return out

    def note_lost(self, e, what):
        self.lost.append({"node": e.tag, "DEF": e.get("DEF"), "what": what})


LABEL_SET = "semantics:labels"


def labels_of(*nodes):
    """{taxonomy: [values]} from the semantics:labels MetadataSets written directly on the given X3D nodes, in order."""
    out = {}
    for n in nodes:
        if n is None:
            continue
        for ms in n:
            if not isinstance(ms.tag, str) or ms.tag != "MetadataSet" or (ms.get("name") or "").strip() != LABEL_SET:
                continue
            for c in ms:
                if isinstance(c.tag, str) and c.tag == "MetadataString" and (c.get("name") or "").strip():
                    raw = c.get("value") or ""
                    vals = re.findall(r'"((?:[^"\\]|\\.)*)"', raw) or ([raw.strip()] if raw.strip() else [])
                    out.setdefault(c.get("name").strip(), []).extend(v for v in vals if v.strip())
    return out


def apply_labels(prim, labels):
    """SemanticsLabelsAPI:<taxonomy> by name (as SimReady's rules read it) with token[] semantics:labels:<taxonomy>."""
    for tax, vals in labels.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tax):
            continue
        prim.AddAppliedSchema(f"SemanticsLabelsAPI:{tax}")
        prim.CreateAttribute(f"semantics:labels:{tax}", Sdf.ValueTypeNames.TokenArray).Set(Vt.TokenArray(list(vals)))
    return len(labels)


def appearance_nodes(sc, shape):
    """The Shape's Appearance and its material node, USE followed (None where absent)."""
    app = next((sc.res(c) for c in shape if isinstance(c.tag, str) and c.tag == "Appearance"), None)
    mat = None
    if app is not None:
        mat = next((sc.res(m) for m in app if isinstance(m.tag, str) and m.tag in
                    ("Material", "PhysicalMaterial", "UnlitMaterial", "TwoSidedMaterial")), None)
    return app, mat


def png_size(path):
    with open(path, "rb") as fh:
        d = fh.read(24)
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(d[16:20], "big"), int.from_bytes(d[20:24], "big")


def appearance_colour(shape):
    for app in shape.iter("Appearance"):
        for m in app:
            if not isinstance(m.tag, str):
                continue
            if m.tag in ("Material", "TwoSidedMaterial"):
                return v3(m.get("diffuseColor"), (0.8, 0.8, 0.8)), 1 - float(m.get("transparency", 0) or 0), 0.5
            if m.tag == "PhysicalMaterial":
                return v3(m.get("baseColor"), (1, 1, 1)), 1 - float(m.get("transparency", 0) or 0), float(m.get("roughness", 1))
            if m.tag == "UnlitMaterial":
                return v3(m.get("emissiveColor"), (1, 1, 1)), 1 - float(m.get("transparency", 0) or 0), 1.0
    return np.array([0.8, 0.8, 0.8]), 1.0, 0.5


class Writer:
    def __init__(self, sc: Scene, out: Path, meta: dict):
        self.sc, self.out, self.meta = sc, Path(out), meta
        if self.out.exists():
            self.out.unlink()
        self.stage = Usd.Stage.CreateNew(str(self.out))
        UsdGeom.SetStageUpAxis(self.stage, UsdGeom.Tokens.z)
        self.unit = 1.0
        for u in sc.root.iter("unit"):
            if u.get("category") == "length":
                f = nums(u.get("conversionFactor"))
                if f and f[0] > 0:
                    self.unit = float(f[0])
        UsdGeom.SetStageMetersPerUnit(self.stage, self.unit)
        UsdPhysics.SetStageKilogramsPerUnit(self.stage, 1.0)
        self.root = UsdGeom.Xform.Define(self.stage, "/World")
        self.stage.SetDefaultPrim(self.root.GetPrim())
        Usd.ModelAPI(self.root.GetPrim()).SetKind("component")
        self.mats, self.phys_mats, self.names = {}, {}, set()
        self.body_prims, self.body_pose = {}, {}
        self.report = {"bodies": 0, "dynamic": 0, "static": 0, "kinematic_lost": 0, "shapes": 0, "joints": {},
                       "lost": sc.lost, "dropped_fields": [], "meta_missing": [], "labels": 0, "meters_per_unit": self.unit}
        self.total_mass, self.lo, self.hi = 0.0, np.full(3, np.inf), np.full(3, -np.inf)

    # ------------------------------------------------------------------ names
    def name(self, base):
        n = re.sub(r"[^A-Za-z0-9_]", "_", base or "node") or "node"
        if n[0].isdigit():
            n = "_" + n
        k, cand = 1, n
        while cand in self.names:
            k += 1
            cand = f"{n}_{k}"
        self.names.add(cand)
        return cand

    # -------------------------------------------------------------- materials
    def material(self, shape):
        col, opa, rough = appearance_colour(shape)
        lab = labels_of(*appearance_nodes(self.sc, shape))
        key = (tuple(np.round(col, 4)), round(opa, 4), round(rough, 3), json.dumps(lab, sort_keys=True))
        if key not in self.mats:
            UsdGeom.Scope.Define(self.stage, "/World/Looks")
            p = f"/World/Looks/{self.name('Mat')}"
            m = UsdShade.Material.Define(self.stage, p)
            s = UsdShade.Shader.Define(self.stage, p + "/Surface")
            s.CreateIdAttr("UsdPreviewSurface")
            s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(gfv(col))
            s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(rough))
            s.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opa))
            m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface")
            self.report["labels"] += apply_labels(m.GetPrim(), lab)
            self.mats[key] = m
        return self.mats[key], col

    def physics_material(self, cc):
        if cc is None:
            return None
        key = id(cc)
        if key not in self.phys_mats:
            UsdGeom.Scope.Define(self.stage, "/World/PhysicsMaterials")
            p = f"/World/PhysicsMaterials/{self.name(cc.get('DEF') or 'Surface')}"
            m = UsdShade.Material.Define(self.stage, p)
            api = UsdPhysics.MaterialAPI.Apply(m.GetPrim())
            params = cc.get("appliedParameters", '"BOUNCE"')
            fr = nums(cc.get("frictionCoefficients")) or [0.0, 0.0]
            e = float(cc.get("bounce", 0) or 0)
            api.CreateRestitutionAttr(e if "BOUNCE" in params else 0.0)
            mu = fr[0] if "FRICTION_COEFFICIENT-2" in params or "FRICTION" in params else 0.0
            api.CreateStaticFrictionAttr(float(mu))
            api.CreateDynamicFrictionAttr(float(mu))
            self.phys_mats[key] = m
        return self.phys_mats[key]

    # ----------------------------------------------------------------- shapes
    def geom(self, parent_path, shape, collide, phys_mat, static, pose_t, pose_q, owner=None):
        """One X3D Shape (inside a collidable) as a USD gprim under parent_path, at local pose (t, q) in X3D frame."""
        sc = self.sc
        g = next(iter(sc.kids(shape, "geometry", GEOMS) or [c for c in (sc.res(x) for x in shape) if c is not None and c.tag in GEOMS]), None)
        if g is None:
            return None
        nm = self.name(g.tag)
        p = f"{parent_path}/{nm}"
        t, q = C @ pose_t, to_usd_q(pose_q)
        if g.tag == "Sphere":
            gp = UsdGeom.Sphere.Define(self.stage, p)
            r = float(g.get("radius", 1))
            gp.CreateRadiusAttr(r)
            gp.CreateExtentAttr([(-r, -r, -r), (r, r, r)])
            ext = np.array([r, r, r])
        elif g.tag == "Box":
            gp = UsdGeom.Cube.Define(self.stage, p)
            gp.CreateSizeAttr(1.0)
            sz = v3(g.get("size"), (2, 2, 2))
            ext = np.abs(C @ sz) / 2
        elif g.tag in ("Cylinder", "Cone"):
            gp = (UsdGeom.Cylinder if g.tag == "Cylinder" else UsdGeom.Cone).Define(self.stage, p)
            r = float(g.get("radius" if g.tag == "Cylinder" else "bottomRadius", 1))
            h = float(g.get("height", 2))
            gp.CreateRadiusAttr(r)
            gp.CreateHeightAttr(h)
            gp.CreateAxisAttr("Z")
            gp.CreateExtentAttr([(-r, -r, -h / 2), (r, r, h / 2)])
            ext = np.array([r, r, h / 2])
        else:
            coord = next(iter(sc.kids(g, "coord", "Coordinate")), None)
            pts = np.array(nums(coord.get("point") if coord is not None else ""), float).reshape(-1, 3)
            if g.tag == "IndexedFaceSet":
                idx = [int(x) for x in nums(g.get("coordIndex"))]
                faces, cur = [], []
                for i in idx + [-1]:
                    if i < 0:
                        if len(cur) >= 3:
                            faces.append(cur)
                        cur = []
                    else:
                        cur.append(i)
            else:
                idx = [int(x) for x in nums(g.get("index"))]
                faces = [idx[i:i + 3] for i in range(0, len(idx) - 2, 3)]
            ccw = g.get("ccw", "true").lower() != "false"
            if not ccw:
                faces = [f[::-1] for f in faces]
            gp = UsdGeom.Mesh.Define(self.stage, p)
            up = (C @ pts.T).T
            gp.CreatePointsAttr([gfv(x) for x in up])
            gp.CreateFaceVertexCountsAttr([len(f) for f in faces])
            gp.CreateFaceVertexIndicesAttr([i for f in faces for i in f])
            gp.CreateSubdivisionSchemeAttr("none")
            nrm = []
            for f in faces:                               # flat per-face normals (Newell), faceVarying
                a = np.zeros(3)
                for i in range(len(f)):
                    p0, p1 = up[f[i]], up[f[(i + 1) % len(f)]]
                    a += np.cross(p0, p1)
                ln = np.linalg.norm(a)
                nrm += [gfv(a / ln if ln > 0 else np.array([0, 0, 1.0]))] * len(f)
            if nrm:
                gp.CreateNormalsAttr(nrm)
                gp.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
            if len(up):
                gp.CreateExtentAttr([gfv(up.min(0)), gfv(up.max(0))])
                ext = np.abs(up).max(0)
            else:
                ext = np.zeros(3)
        xf = UsdGeom.Xformable(gp)
        xf.AddTranslateOp().Set(Gf.Vec3d(*map(float, t)))
        xf.AddOrientOp().Set(gfq(q))
        if g.tag == "Box":
            xf.AddScaleOp().Set(gfv(np.abs(np.array([sz[0], sz[2], sz[1]]))))   # Box size in the rotated frame
        mat, col = self.material(shape)
        UsdShade.MaterialBindingAPI.Apply(gp.GetPrim()).Bind(mat)
        gp.CreateDisplayColorAttr([gfv(col)])
        api = UsdPhysics.CollisionAPI.Apply(gp.GetPrim())
        api.CreateCollisionEnabledAttr(bool(collide))
        if g.tag in ("IndexedFaceSet", "IndexedTriangleSet"):
            UsdPhysics.MeshCollisionAPI.Apply(gp.GetPrim()).CreateApproximationAttr("none" if static else "convexHull")
        if phys_mat is not None:
            UsdShade.MaterialBindingAPI.Apply(gp.GetPrim()).Bind(phys_mat, UsdShade.Tokens.weakerThanDescendants, "physics")
        self.report["labels"] += apply_labels(gp.GetPrim(), labels_of(owner, shape))
        self.report["shapes"] += 1
        return gp, ext

    def collidables(self, body_path, node, colliding, phys_mat_of, static, base_t, base_q):
        """Walk a RigidBody's geometry field: CollidableShape and CollidableOffset (nested), composing their poses."""
        sc = self.sc
        for c in sc.kids(node, "geometry") + sc.kids(node, "collidable"):
            t = base_t + qrot(base_q, v3(c.get("translation")))
            q = qmul(base_q, axis_angle(c.get("rotation")))
            if c.tag == "CollidableOffset":
                yield from self.collidables(body_path, c, colliding, phys_mat_of, static, t, q)
            elif c.tag == "CollidableShape":
                shapes = sc.kids(c, "shape", "Shape")
                if not shapes:
                    # a Shape child without containerField='shape' is, strictly, in the 'children' field CollidableShape
                    # does not have; X_ITE takes it as the shape anyway. Taken, and reported as an inference
                    shapes = [s for s in sc.kids(c, None, "Shape") if s.get("containerField") in (None, "children")]
                    if shapes:
                        self.report.setdefault("inferred", []).append(f"CollidableShape {c.get('DEF')}: Shape without containerField='shape'")
                for sh in shapes:
                    r = self.geom(body_path, sh, c in colliding, phys_mat_of.get(c), static, t, q, owner=c)
                    if r:
                        yield r, t

    # ----------------------------------------------------------------- bodies
    def write(self):
        sc = self.sc
        rbcs = [e for e in sc.root.iter("RigidBodyCollection") if not e.get("USE")]
        routed_to = {(r.get("toNode"), r.get("toField")) for r in sc.root.iter("ROUTE")}
        self.jointed = set()
        for rbc in rbcs:
            for j in sc.kids(rbc, "joints"):
                for f in ("body1", "body2"):
                    for bb in sc.kids(j, f, "RigidBody"):
                        self.jointed.add(bb.get("DEF"))
        scene_prim = UsdPhysics.Scene.Define(self.stage, "/World/PhysicsScene")
        g = v3(rbcs[0].get("gravity"), (0, -9.8, 0)) if rbcs else np.array([0, -9.8, 0])
        gu = C @ g
        gm = float(np.linalg.norm(gu))
        scene_prim.CreateGravityDirectionAttr(gfv(gu / gm if gm > 0 else np.array([0, 0, -1.0])))
        scene_prim.CreateGravityMagnitudeAttr(gm)
        for rbc in rbcs:
            for f in ODE_ONLY["RigidBodyCollection"]:
                if rbc.get(f) is not None:
                    self.report["dropped_fields"].append(f"RigidBodyCollection.{f}")
            colliding, phys_mat_of = set(), {}
            for cc in sc.kids(rbc, "collider", "CollisionCollection"):
                for f in ODE_ONLY["CollisionCollection"]:
                    if cc.get(f) is not None:
                        self.report["dropped_fields"].append(f"CollisionCollection.{f}")
                pm = self.physics_material(cc)

                def walk(x):
                    if x.tag == "CollidableShape":
                        colliding.add(x)
                        phys_mat_of[x] = pm
                    for k in sc.kids(x, "collidable"):
                        walk(k)
                for x in sc.kids(cc, "collidables"):
                    walk(x)
                    if x.tag == "CollidableOffset":
                        for k in sc.kids(x, "collidable"):
                            walk(k)
            for body in sc.kids(rbc, "bodies", "RigidBody"):
                self.body(body, colliding, phys_mat_of, routed_to)
            for j in sc.kids(rbc, "joints"):
                self.joint(j)
        for e in sc.root.iter("CollisionSensor"):            # joints of these kinds are reported by joint()
            if not e.get("USE"):
                sc.note_lost(e, "no UsdPhysics counterpart (contact reports are a runtime feature)")
        self.metadata()
        self.stage.GetRootLayer().Save()
        return self.report

    def body(self, b, colliding, phys_mat_of, routed_to):
        fixed = b.get("fixed", "false").lower() == "true"
        name = self.name(b.get("DEF") or "Body")
        p = f"/World/{name}"
        x = UsdGeom.Xform.Define(self.stage, p)
        pos, q = v3(b.get("position")), axis_angle(b.get("orientation"))
        xf = UsdGeom.Xformable(x)
        xf.AddTranslateOp().Set(Gf.Vec3d(*map(float, C @ pos)))
        xf.AddOrientOp().Set(gfq(to_usd_q(q)))
        self.body_prims[id(b)] = x.GetPrim()
        self.body_pose[id(b)] = (pos, q)
        self.report["labels"] += apply_labels(x.GetPrim(), labels_of(b))
        self.report["bodies"] += 1
        for f in ODE_ONLY["RigidBody"]:
            if b.get(f) is not None:
                self.report["dropped_fields"].append(f"RigidBody.{f}")
        shapes = list(self.collidables(p, b, colliding, phys_mat_of, fixed, np.zeros(3), np.array([1.0, 0, 0, 0])))
        for (gp, ext), t in shapes:
            c = C @ (pos + qrot(q, t))
            self.lo, self.hi = np.minimum(self.lo, c - ext), np.maximum(self.hi, c + ext)
        if fixed:
            self.report["static"] += 1
            if b.get("DEF") and ((b.get("DEF"), "set_position") in routed_to or (b.get("DEF"), "position") in routed_to
                                 or (b.get("DEF"), "set_orientation") in routed_to or (b.get("DEF"), "orientation") in routed_to):
                self.report["kinematic_lost"] += 1
                self.sc.note_lost(b, "a fixed body moved by ROUTE (kinematic path): written static, the path is not carried")
            return
        self.report["dynamic"] += 1
        rb = UsdPhysics.RigidBodyAPI.Apply(x.GetPrim())
        rb.CreateVelocityAttr(gfv(C @ v3(b.get("linearVelocity"))))
        rb.CreateAngularVelocityAttr(gfv(np.degrees(C @ v3(b.get("angularVelocity")))))
        ma = UsdPhysics.MassAPI.Apply(x.GetPrim())
        m = float(b.get("mass", 1) or 1)
        ma.CreateMassAttr(m)
        self.total_mass += m
        if b.get("centerOfMass"):
            ma.CreateCenterOfMassAttr(gfv(C @ v3(b.get("centerOfMass"))))
        I = np.array(nums(b.get("inertia")) or [1, 0, 0, 0, 1, 0, 0, 0, 1], float).reshape(3, 3)
        if not np.allclose(I, np.eye(3)):
            Iu = C @ I @ C.T
            w, V = np.linalg.eigh((Iu + Iu.T) / 2)
            if np.linalg.det(V) < 0:
                V[:, 0] = -V[:, 0]
            ma.CreateDiagonalInertiaAttr(gfv(w))
            # columns of V are the principal axes; Gf matrices are row-vector, so the rotation matrix is V transposed
            qv = Gf.Matrix3d(*V.T.flatten().tolist()).ExtractRotation().GetQuat()
            ma.CreatePrincipalAxesAttr(Gf.Quatf(qv))

    # ----------------------------------------------------------------- joints
    def joint(self, j):
        sc = self.sc
        kind = j.tag
        self.report["joints"][kind] = self.report["joints"].get(kind, 0) + 1
        for f in ODE_ONLY.get(kind, ()):
            if j.get(f) is not None:
                self.report["dropped_fields"].append(f"{kind}.{f}")
        if kind not in ("BallJoint", "SingleAxisHingeJoint", "SliderJoint"):
            sc.note_lost(j, f"{kind}: no UsdPhysics joint with X3D's semantics; not written")
            return
        b1 = next(iter(sc.kids(j, "body1", "RigidBody")), None)
        b2 = next(iter(sc.kids(j, "body2", "RigidBody")), None)
        name = self.name(j.get("DEF") or kind)
        UsdGeom.Scope.Define(self.stage, "/World/Joints")
        p = f"/World/Joints/{name}"
        jt = {"BallJoint": UsdPhysics.SphericalJoint, "SingleAxisHingeJoint": UsdPhysics.RevoluteJoint,
              "SliderJoint": UsdPhysics.PrismaticJoint}[kind].Define(self.stage, p)
        anchor = v3(j.get("anchorPoint"))
        axis = v3(j.get("axis"), (0, 1, 0) if kind == "SliderJoint" else (0, 0, 1))
        if np.linalg.norm(axis) < 1e-12:
            axis = np.array([0, 0, 1.0])
        qj_world = quat_from_x_to(C @ axis)                          # joint frame in USD world: +X along the axis
        a_world = C @ anchor
        # USD body0 = X3D body2 (often the fixed pivot), body1 = X3D body1; a missing body is the world
        for k, b in ((0, b2), (1, b1)):
            rel = jt.CreateBody0Rel() if k == 0 else jt.CreateBody1Rel()
            if b is not None and id(b) in self.body_prims:
                rel.SetTargets([self.body_prims[id(b)].GetPath()])
                pos, q = self.body_pose[id(b)]
                pu, qu = C @ pos, to_usd_q(q)
                lp = qrot(qconj(qu), a_world - pu)
                lq = qmul(qconj(qu), qj_world)
            else:
                lp, lq = a_world, qj_world
            (jt.CreateLocalPos0Attr if k == 0 else jt.CreateLocalPos1Attr)(gfv(lp))
            (jt.CreateLocalRot0Attr if k == 0 else jt.CreateLocalRot1Attr)(gfq(lq))
        # jointed bodies do not collide with each other (UsdPhysics' joint default, PhysX's joint default, and the
        # x3d_mcp collider-overlap check's reading); said explicitly, and as a filtered pair, because a static body is
        # not a rigid body in USD and a solver may then attach its shapes to the world, where the joint filter is lost
        jt.CreateCollisionEnabledAttr(False)
        pair = [self.body_prims[id(b)] for b in (b1, b2) if b is not None and id(b) in self.body_prims]
        if len(pair) == 2:
            api = UsdPhysics.FilteredPairsAPI.Apply(pair[0])
            api.CreateFilteredPairsRel().AddTarget(pair[1].GetPath())
        if kind == "SingleAxisHingeJoint":
            jt.CreateAxisAttr("X")
            lo, hi = float(j.get("minAngle", -math.pi)), float(j.get("maxAngle", math.pi))
            if not (lo <= -math.pi + 1e-6 and hi >= math.pi - 1e-6) and lo <= hi:
                jt.CreateLowerLimitAttr(math.degrees(lo))
                jt.CreateUpperLimitAttr(math.degrees(hi))
        elif kind == "SliderJoint":
            jt.CreateAxisAttr("X")
            lo, hi = float(j.get("minSeparation", 0)), float(j.get("maxSeparation", 1))
            if lo <= hi:
                jt.CreateLowerLimitAttr(lo)
                jt.CreateUpperLimitAttr(hi)

    # --------------------------------------------------------------- metadata
    def metadata(self):
        heads = {m.get("name", "").lower(): m.get("content", "") for m in self.sc.root.iter("meta")}
        wi = next(iter(self.sc.root.iter("WorldInfo")), None)
        pick = lambda *ks: next((heads[k] for k in ks if heads.get(k)), None)
        md = {"asset_name": pick("title") or (wi.get("title") if wi is not None else None) or self.sc.path.stem,
              "author": pick("creator", "author", "dc.creator"),
              "asset_license": pick("license", "rights", "dc.rights"),
              "category": pick("simready:category", "category"),
              "qcode": pick("simready:qcode", "wikidata", "qcode"),
              "asset_type": pick("simready:asset_type", "asset_type") or ("articulated" if self.report["joints"] else "prop"),
              "source_file": self.sc.path.name,
              "usd_date_generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "rigid_body_count": int(self.report["dynamic"]),
              "mass": float(self.total_mass)}
        if np.all(np.isfinite(self.lo)):
            md["asset_extents"] = [float(x) * self.unit for x in (self.hi - self.lo)]      # metres, whatever the stage unit
        md.update(self.meta)
        if md.get("qcode") and not re.match(r"^Q[0-9]+$", str(md["qcode"])):
            md.pop("qcode")
        present = {k: v for k, v in md.items() if v not in (None, "")}
        self.report["meta_missing"] = sorted(set(md) - set(present) | ({"asset_extents"} - set(present)))
        self.report["meta"] = present
        layer = self.stage.GetRootLayer()
        cld = dict(layer.customLayerData)
        nested = {k: (Vt.FloatArray(v) if isinstance(v, list) else v) for k, v in present.items()}
        cld["SimReady_Metadata"] = nested
        for k in ("asset_name", "asset_type", "source_file", "usd_date_generated"):
            if k in present:
                cld[k] = present[k]
        layer.customLayerData = cld
        layer.comment = f"Written from {self.sc.path.name} by x3dnv.x3d2usdphysics (X3D RigidBodyPhysics to UsdPhysics)"
        self.thumbnail(heads.get("image"))

    def thumbnail(self, url):
        """<meta name='Image'> names the scene's picture; SimReady SR.002 looks for .thumbs/256x256/<file>.png."""
        if not url:
            self.report["thumbnail"] = "none named (<meta name='Image'>)"
            return
        src = (self.sc.path.parent / url).resolve()
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or not src.is_file() or not src.is_relative_to(self.sc.path.parent.resolve()):
            self.report["thumbnail"] = f"{url}: not a file beside the scene, not copied"
            return
        size = png_size(src)
        if size is None:
            self.report["thumbnail"] = f"{url}: not a PNG, not copied"
            return
        dest = self.out.parent / ".thumbs" / "256x256" / (self.out.name + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        self.report["thumbnail"] = f"{url} copied to .thumbs/256x256/{dest.name}" + (
            "" if size == (256, 256) else f" ({size[0]} x {size[1]}, not resized)")


# ---------------------------------------------------------------- runtime variants (SimReady RV.*)
# Newton and MuJoCo schemas are written by name (Usd.Prim.AddAppliedSchema), as SimReady's own adapters do: neither is
# registered in every runtime, and the validators read apiSchemas by name. Each engine's schemas live only in that
# engine's payload, behind a variant set (default Disabled) on the default prim, because SimReady's isolation matrix
# (RV.010, RV.011) forbids engine schemas in the neutral stage and Mjc* in a Newton stage (and the reverse).
RUNTIMES = ("physx", "newton", "mujoco")
_VSET = {"physx": "PhysX", "newton": "Newton", "mujoco": "MuJoCo"}


def _components(stage):
    """Joint-connected groups of bodies: [(bodies, joints)], world and static anchors join nothing."""
    joints = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Joint)]
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    ends = {}
    for j in joints:
        jj = UsdPhysics.Joint(j)
        e = [str(t) for r in (jj.GetBody0Rel(), jj.GetBody1Rel()) for t in r.GetTargets()]
        ends[str(j.GetPath())] = e
        for t in e:
            find(t)
        for a, b in zip(e, e[1:]):
            parent[find(a)] = find(b)
    groups = {}
    for jp, e in ends.items():
        if e:
            groups.setdefault(find(e[0]), []).append(jp)
    comps = []
    for _, js in sorted(groups.items()):
        bodies = sorted({t for jp in js for t in ends[jp]})
        comps.append((bodies, sorted(js)))
    return comps


def add_runtimes(out, runtimes, report):
    """Neutral articulation roots and passive drives, then one payload and one variant set per runtime."""
    out = Path(out)
    stage = Usd.Stage.Open(str(out))
    root = stage.GetDefaultPrim()
    rt = {"articulation_roots": [], "drives": 0, "variants": {}}
    comps = _components(stage)
    for bodies, js in comps:
        dyn = [b for b in bodies if stage.GetPrimAtPath(b).HasAPI(UsdPhysics.RigidBodyAPI)]
        if dyn:
            UsdPhysics.ArticulationRootAPI.Apply(stage.GetPrimAtPath(dyn[0]))
            rt["articulation_roots"].append(dyn[0])
    rt["joint_graphs"] = len(comps)
    colliders = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)]
    # A local opinion outranks every variant and payload (LIVRPS), so a neutral physics:approximation = "none" would
    # beat a runtime's own choice. "none" is the schema fallback: left unauthored, it reads the same and a runtime may set it.
    for c in colliders:
        a = c.GetAttribute("physics:approximation")
        if c.IsA(UsdGeom.Mesh) and a.IsValid() and a.HasAuthoredValue() and a.Get() == "none":
            c.RemoveProperty("physics:approximation")
    joints = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Joint) and not p.IsA(UsdPhysics.FixedJoint)]
    mats = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.MaterialAPI)]
    meta = dict(stage.GetRootLayer().customLayerData)
    sm = dict(meta.get("SimReady_Metadata", {}))
    var = dict(sm.get("Variants", {}))
    phys = dict(var.get("Physics", {}))
    for r in runtimes:
        name = _VSET[r]
        pdir = out.parent / "runnables" / "physics"
        pdir.mkdir(parents=True, exist_ok=True)
        pay = Usd.Stage.CreateNew(str(pdir / f"{r}.usda"))
        pay.SetDefaultPrim(pay.OverridePrim(root.GetPath()).GetPrim())
        def passive_drive(j):
            # A joint no one drives is declared passive: zero gains, the largest force limit, no target. Without a drive
            # a joint reads as unfinished to the rules that ask for one (PhysX DJ.004, Newton DJ.001). A ball joint
            # gets one per rotational axis.
            axes = ["rotX", "rotY", "rotZ"] if j.IsA(UsdPhysics.SphericalJoint) else \
                ["linear" if j.IsA(UsdPhysics.PrismaticJoint) else "angular"]
            for kind in axes:
                d = UsdPhysics.DriveAPI.Apply(pay.OverridePrim(j.GetPath()), kind)
                d.CreateStiffnessAttr(0.0)
                d.CreateDampingAttr(0.0)
                d.CreateMaxForceAttr(3.4028235e38)
            return axes
        for c in colliders:
            o = pay.OverridePrim(c.GetPath())
            mesh = c.IsA(UsdGeom.Mesh)
            approx = c.GetAttribute("physics:approximation").Get() if mesh else None
            if r == "newton":
                o.AddAppliedSchema("NewtonCollisionAPI")
                if mesh and approx == "none":              # a static, concave triangle mesh: Newton's concave collider is the SDF. Its approximation token stays unauthored: 'sdf' there is PhysX's, and RV.011 calls it a leak
                    o.AddAppliedSchema("NewtonSDFCollisionAPI")
                    rt["sdf_meshes"] = rt.get("sdf_meshes", 0) + 1
                elif mesh:
                    o.AddAppliedSchema("NewtonMeshCollisionAPI")
            elif r == "mujoco":
                o.AddAppliedSchema("MjcCollisionAPI")
                if mesh and approx != "none":
                    o.AddAppliedSchema("MjcMeshCollisionAPI")
                elif mesh:                                  # MuJoCo collides convex meshes only; a hull would fill a bowl
                    rt.setdefault("mujoco_refused_concave", []).append(str(c.GetPath()))
            else:
                o.AddAppliedSchema("PhysxCollisionAPI")
        if r == "newton":
            for m in mats:
                o = pay.OverridePrim(m.GetPath())
                o.AddAppliedSchema("NewtonMaterialAPI")
                o.CreateAttribute("newton:torsionalFriction", Sdf.ValueTypeNames.Float).Set(0.005)
                o.CreateAttribute("newton:rollingFriction", Sdf.ValueTypeNames.Float).Set(0.0001)
            for a in rt["articulation_roots"]:
                o = pay.OverridePrim(a)
                o.AddAppliedSchema("NewtonArticulationRootAPI")
                o.CreateAttribute("newton:selfCollisionEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            for j in joints:
                passive_drive(j)
        elif r == "mujoco":
            for j in joints:
                pay.OverridePrim(j.GetPath()).AddAppliedSchema("MjcJointAPI")
        else:
            for j in joints:
                o = pay.OverridePrim(j.GetPath())
                for kind in passive_drive(j):
                    o.AddAppliedSchema(f"PhysicsJointStateAPI:{kind}")
                    o.CreateAttribute(f"state:{kind}:physics:position", Sdf.ValueTypeNames.Float).Set(0.0)
                    o.CreateAttribute(f"state:{kind}:physics:velocity", Sdf.ValueTypeNames.Float).Set(0.0)
        pay.GetRootLayer().Save()
        vs = root.GetVariantSets().AddVariantSet(name)
        vs.AddVariant("Disabled")
        vs.AddVariant("Enabled")
        vs.SetVariantSelection("Enabled")
        with vs.GetVariantEditContext():
            root.GetPayloads().AddPayload(Sdf.Payload(f"./runnables/physics/{r}.usda"), Usd.ListPositionFrontOfPrependList)
        vs.SetVariantSelection("Disabled")
        phys[name] = {"prim": str(root.GetPath()), "variantSetName": name, "activateOption": "Enabled"}
        rt["variants"][name] = {"payload": f"runnables/physics/{r}.usda", "colliders": len(colliders),
                                "joints": len(joints) if r != "newton" or joints else 0}
    var["Physics"] = phys
    sm["Variants"] = var
    meta["SimReady_Metadata"] = sm
    stage.GetRootLayer().customLayerData = meta
    stage.GetRootLayer().Save()
    report["runtimes"] = rt


def convert(src, out, meta=None, runtimes=()):
    sc = Scene(src)
    w = Writer(sc, out, meta or {})
    rep = w.write()
    rep["dropped_fields"] = sorted(set(rep["dropped_fields"]))
    if runtimes:
        add_runtimes(out, runtimes, rep)
    return rep


if __name__ == "__main__":
    a = sys.argv[1:]
    meta = {}
    if "--meta" in a:
        i = a.index("--meta")
        for kv in a[i + 1:]:
            if kv.startswith("--"):
                break
            k, _, v = kv.partition("=")
            meta[k] = v
    rep_path = a[a.index("--report") + 1] if "--report" in a else None
    rts = tuple(a[a.index("--runtimes") + 1].split(",")) if "--runtimes" in a else ()
    assert all(r in RUNTIMES for r in rts), f"--runtimes takes {','.join(RUNTIMES)}"
    rep = convert(a[0], a[1], meta, rts)
    if rep_path:
        Path(rep_path).write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: rep[k] for k in ("bodies", "dynamic", "static", "shapes", "joints", "kinematic_lost")}),
          len(rep["lost"]), "lost nodes,", len(rep["dropped_fields"]), "dropped field kinds")
