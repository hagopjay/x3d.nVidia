"""Newton 1.8.0: which stages get an articulation from add_usd? A grid of body0 (static Xform, kinematic rigid body, none) x ArticulationRootAPI placement; prints joint_articulation."""
import tempfile,warnings; warnings.filterwarnings('ignore')
from pathlib import Path
import newton
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
def mk(path, body0_mode, root_on):
    st=Usd.Stage.CreateNew(path); UsdGeom.SetStageUpAxis(st,'Z'); UsdGeom.SetStageMetersPerUnit(st,1.0)
    UsdGeom.Xform.Define(st,'/World'); st.SetDefaultPrim(st.GetPrimAtPath('/World')); UsdPhysics.Scene.Define(st,'/World/PhysicsScene')
    pv=UsdGeom.Xform.Define(st,'/World/Pivot'); UsdGeom.Xformable(pv).AddTranslateOp().Set(Gf.Vec3d(0,0,1))
    if body0_mode=='rigid-kinematic':
        UsdPhysics.RigidBodyAPI.Apply(pv.GetPrim()).CreateKinematicEnabledAttr(True)
    bob=UsdGeom.Xform.Define(st,'/World/Bob'); UsdGeom.Xformable(bob).AddTranslateOp().Set(Gf.Vec3d(0.5,0,1))
    UsdPhysics.RigidBodyAPI.Apply(bob.GetPrim()); UsdPhysics.MassAPI.Apply(bob.GetPrim()).CreateMassAttr(1.0)
    sp=UsdGeom.Sphere.Define(st,'/World/Bob/S'); sp.CreateRadiusAttr(0.05); UsdPhysics.CollisionAPI.Apply(sp.GetPrim())
    j=UsdPhysics.RevoluteJoint.Define(st,'/World/Joint')
    if body0_mode!='world': j.CreateBody0Rel().SetTargets([Sdf.Path('/World/Pivot')])
    j.CreateBody1Rel().SetTargets([Sdf.Path('/World/Bob')])
    j.CreateLocalPos0Attr(Gf.Vec3f(0,0,0) if body0_mode!='world' else Gf.Vec3f(0,0,1)); j.CreateLocalPos1Attr(Gf.Vec3f(-0.5,0,0)); j.CreateAxisAttr('Y')
    if root_on: UsdPhysics.ArticulationRootAPI.Apply(st.GetPrimAtPath(root_on))
    st.GetRootLayer().Save()
d=Path(tempfile.mkdtemp()); k=0
for m in ('static-xform','rigid-kinematic','world'):
    for r in (None,'/World/Bob','/World/Joint','/World/Pivot'):
        if m=='world' and r=='/World/Pivot': continue
        k+=1; p=str(d/f's{k}.usda'); mk(p,m,r)
        b=newton.ModelBuilder(up_axis=newton.Axis.Z); b.add_usd(p,apply_up_axis_from_stage=True)
        print(f'{m:16} root on {str(r):14} joint_articulation={list(b.joint_articulation)} joint types={[int(t) for t in b.joint_type]}')
