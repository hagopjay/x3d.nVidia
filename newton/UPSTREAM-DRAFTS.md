# Draft upstream reports for Newton's USD importer (NOT SENT: nothing goes to an outside repo until HagopJay says "send")

Both reproduce on **Newton 1.8.0, newton-usd-schemas 0.8.0, Warp 1.19.0 (CPU), usd-core 26.8, mujoco-warp 3.17.0 / mujoco-core 4.0.1, Python 3.12**
(`pip install "newton[importers,sim]==1.8.0"`). Each script prints its result and has a control. Grade: **Confirmed** (re-run 26 Nov 2026
in a clean venv, independently of the session that found them). Unverified: later Newton releases, GPU.

## Report 1: `add_usd` makes no collision filter pair when one body of the joint is a static collider

**Script:** `repros/repro_newton_filter_pairs.py`. A bob starts overlapping a pivot; a revolute joint joins them with
`physics:collisionEnabled = false`, and the bob also carries `FilteredPairsAPI` targeting the pivot.

```
static pivot (a prim without RigidBodyAPI), joint collisionEnabled=false + FilteredPairsAPI
  shapes: ['/World/Bob/Sphere', '/World/Pivot/Box']
  filter pairs: []                                                   <- expected one pair
dynamic pivot, same stage (control)
  filter pairs: [('/World/Bob/Sphere', '/World/Pivot/Box')]
```

**Why it matters:** the pendulum bob collides with its own pivot. In the X3D PhysX-bridge scenes this made a pendulum gain
energy every swing (XPBD blew up; MuJoCo's bob rose 66 mm). Workaround: `x3d.nVidia src/x3dnv/newton_run.py` adds the pairs itself.
**Ask:** honour `FilteredPairsAPI` and `collisionEnabled=false` joints when a side is a static collider (shapes that go to the world body).

## Report 2: a joint to a static Xform is never part of an articulation, even with `ArticulationRootAPI`

**Script:** `repros/repro_newton_mujoco_no_articulation.py` (stage: revolute joint, body0 a plain Xform `/World/Pivot`, body1 a rigid bob;
`ArticulationRootAPI` tried on the bob, the joint and the pivot), and `repros/probe_newton_articulation_grid.py` (the grid of body0 kinds x root placements):

```
no ArticulationRootAPI              joint_articulation=[-1]  joint_q=2.0764 rad  body displacement after eval_fk=0.0000 m
ArticulationRootAPI on /World/Bob   joint_articulation=[-1]  ...                 body displacement ... 0.0000 m
ArticulationRootAPI on /World/Joint joint_articulation=[-1]  ...                 body displacement ... 0.0000 m
ArticulationRootAPI on /World/Pivot joint_articulation=[-1]  ...                 body displacement ... 0.0000 m
```

Probe grid output: with the pivot made a kinematic rigid body, `ArticulationRootAPI` on the bob or the pivot
gives `joint_articulation=[0, 0]` and joint types `[FREE, REVOLUTE]`, i.e. an articulation, but with an extra free joint on the pivot;
a joint with no body0 at all stays at `-1`. SolverMuJoCo logs that it converts such joints into "standalone world roots", yet the body pose
does not follow `joint_q` (`body_q` unchanged after 120 steps, with or without `eval_fk`).
**Ask:** treat a non-rigid Xform (or an absent body0) as the world when finding the articulation of an authored `ArticulationRootAPI`, or say in the
docs that body0 must be a rigid body; and make the MuJoCo fallback move the body.

## Not filed here
Both add-on defects (RigidBody `position` ignored; a USE'd body imported twice) are filed as issues #99 and #100 in `hagopjay/x3d-blender-io` (HagopJay's own repo); the script is `q12/repros/repro_addon_rigidbody.py`.
