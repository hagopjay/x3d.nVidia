"""Run a UsdPhysics stage (from x3d2usdphysics) in Newton, step by step, with a hash of every step's state.

    python -m x3dnv.newton_run STAGE.usda OUT.npz --solver xpbd|mujoco|semi --steps N [--dt 1/240] [--iterations K]

Newton 1.8 (Linux Foundation; Warp and OpenUSD). Solvers used here:
    xpbd     newton.solvers.SolverXPBD (Newton's own position-based solver)
    mujoco   newton.solvers.SolverMuJoCo(use_mujoco_cpu=True): MuJoCo 4.0.1's C engine behind Newton's model
    semi     newton.solvers.SolverSemiImplicit (penalty contacts)
Everything runs on the CPU (Warp device "cpu"): this workspace has no GPU. A GPU run is a separate host.

The per-step hash is the first 8 bytes of sha256 over the bodies' poses and velocities (float32, little-endian), as a
decimal integer, so a loom.physics-run/1 record can carry it (kit/loomkit/physics.py hashes the decimal list).
"""
from __future__ import annotations

import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import warp as wp

wp.config.quiet = True
import newton  # noqa: E402

SOLVERS = ("xpbd", "mujoco", "semi")


def build(stage_path, solver="xpbd", iterations=None, ground=False):
    b = newton.ModelBuilder(up_axis=newton.Axis.Z)
    info = b.add_usd(str(stage_path), apply_up_axis_from_stage=True, enable_self_collisions=False)
    info["filter_pairs_applied"] = apply_declared_filters(b, stage_path)
    info["articulations_added"] = articulate_orphans(b)
    if ground:
        b.add_ground_plane()
    model = b.finalize(device="cpu")
    if solver == "xpbd":
        # X3D's CollisionCollection.bounce is restitution; XPBD applies it only when asked (enable_restitution)
        s = newton.solvers.SolverXPBD(model, iterations=iterations or 10, enable_restitution=True)
    elif solver == "mujoco":
        s = newton.solvers.SolverMuJoCo(model, use_mujoco_cpu=True, iterations=iterations or 100)
    elif solver == "semi":
        s = newton.solvers.SolverSemiImplicit(model)
    else:
        raise ValueError(solver)
    return model, s, info


def apply_declared_filters(builder, stage_path):
    """Measured 26 Nov 2026 on Newton 1.8.0 / newton-usd-schemas 0.8.0: add_usd makes no shape filter pair from a
    UsdPhysics FilteredPairsAPI, nor from a joint whose collisionEnabled is false, when one side is a static collider
    (a prim without RigidBodyAPI, whose shapes go to the world body). A pendulum bob then collides with its own pivot
    and gains energy every swing. The stage declares the pairs; this applies them, by prim path prefix."""
    from pxr import Usd, UsdPhysics
    st = Usd.Stage.Open(str(stage_path))
    pairs = set()
    for prim in st.Traverse():
        if prim.HasAPI(UsdPhysics.FilteredPairsAPI):
            for t in UsdPhysics.FilteredPairsAPI(prim).GetFilteredPairsRel().GetTargets():
                pairs.add((str(prim.GetPath()), str(t)))
        if prim.IsA(UsdPhysics.Joint):
            j = UsdPhysics.Joint(prim)
            if not j.GetCollisionEnabledAttr().Get():
                a, b_ = j.GetBody0Rel().GetTargets(), j.GetBody1Rel().GetTargets()
                if a and b_:
                    pairs.add((str(a[0]), str(b_[0])))
    labels = [str(x) for x in builder.shape_label]
    under = lambda root: [i for i, l in enumerate(labels) if l == root or l.startswith(root + "/")]
    n = 0
    for a, b_ in sorted(pairs):
        for i in under(a):
            for k in under(b_):
                if i != k:
                    builder.add_shape_collision_filter_pair(i, k)
                    n += 1
    return n


def articulate_orphans(builder):
    """X3D has no articulations: its joints join bodies, and that is all. Newton's reduced-coordinate solvers (MuJoCo,
    Featherstone) and eval_fk work per articulation, and add_usd leaves a joint with no ArticulationRootAPI outside any
    (joint_articulation -1): MuJoCo then integrates its angle but no body pose follows. Each connected group of such
    joints (sharing a body) becomes one articulation, parents before children. A group that closes a loop cannot be a
    tree; it is reported, not forced (x3d_mcp's physics-joint-loop check says the same of the X3D scene)."""
    orphan = [j for j, a in enumerate(builder.joint_articulation) if a == -1]
    if not orphan:
        return {"added": 0, "loops": 0}
    parent, child = builder.joint_parent, builder.joint_child
    groups, seen = [], set()
    for j in orphan:
        if j in seen:
            continue
        comp, stack = [], [j]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(k)
            for m in orphan:
                if m not in seen and ({parent[m], child[m]} - {-1}) & ({parent[k], child[k]} - {-1}):
                    stack.append(m)
        groups.append(comp)
    added, loops = 0, 0
    for comp in groups:
        bodies = {b for k in comp for b in (parent[k], child[k]) if b != -1}
        if len(comp) > len(bodies) or len({child[k] for k in comp}) < len(comp):
            loops += 1
            continue
        order, placed = [], {-1}
        rest = list(comp)
        while rest:
            nxt = [k for k in rest if parent[k] in placed or parent[k] not in {child[m] for m in rest}]
            if not nxt:
                loops += 1
                order = []
                break
            for k in sorted(nxt):
                order.append(k)
                placed.add(child[k])
                rest.remove(k)
        if order:
            builder.add_articulation(order, label=f"x3d_joints_{added}")
            added += 1
    return {"added": added, "loops": loops}


def state_hash(state):
    a = np.concatenate([state.body_q.numpy().astype("<f4").ravel(), state.body_qd.numpy().astype("<f4").ravel()])
    return int.from_bytes(hashlib.sha256(a.tobytes()).digest()[:8], "big")


def run(model, solver, steps, dt, keep_every=1, on_step=None, substeps=1):
    """Step; return (poses[t, body, 7] every keep_every steps, velocities likewise, hashes per step).
    substeps > 1 splits each step (the X3D bridges' fixed step stays the recorded unit)."""
    s0, s1, ctl = model.state(), model.state(), model.control()
    newton.eval_fk(model, model.joint_q, model.joint_qd, s0)
    fk = isinstance(solver, newton.solvers.SolverMuJoCo)
    pipe = newton.CollisionPipeline(model)
    contacts = pipe.contacts()
    poses, vels, hashes = [s0.body_q.numpy().copy()], [s0.body_qd.numpy().copy()], []
    for i in range(steps):
        for _ in range(substeps):
            s0.clear_forces()
            pipe.collide(s0, contacts)
            solver.step(s0, s1, ctl, contacts, dt / substeps)
            s0, s1 = s1, s0
            if fk:                               # MuJoCo integrates joint coordinates; body poses follow from them
                newton.eval_fk(model, s0.joint_q, s0.joint_qd, s0)
        hashes.append(state_hash(s0))
        if (i + 1) % keep_every == 0:
            poses.append(s0.body_q.numpy().copy())
            vels.append(s0.body_qd.numpy().copy())
        if on_step:
            on_step(i, s0)
    return np.array(poses), np.array(vels), hashes


def body_labels(model):
    lab = getattr(model, "body_label", None) or getattr(model, "body_key", None) or []
    return [str(x) for x in lab]


def trace_sha256(hashes):
    return hashlib.sha256(",".join(str(h) for h in hashes).encode()).hexdigest()


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    dt = float(Fraction(opt("--dt", "1/240")))
    model, solver, _ = build(a[0], opt("--solver", "xpbd"), int(opt("--iterations", 0)) or None)
    poses, vels, hashes = run(model, solver, int(opt("--steps", 240)), dt, int(opt("--keep-every", 1)))
    np.savez_compressed(a[1], poses=poses, vels=vels, labels=np.array(body_labels(model)), dt=dt)
    print(json.dumps({"bodies": model.body_count, "steps": len(hashes), "trace_sha256": trace_sha256(hashes),
                      "versions": {"newton": newton.__version__, "warp": wp.__version__}}))
