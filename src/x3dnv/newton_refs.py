"""Newton answers the PhysX bridge's nine exact references, through X3D.

    python -m x3dnv.newton_refs OUT.json --solver xpbd|mujoco [--work DIR]

Each reference is an X3D 4.0 RigidBodyPhysics scene written here, converted by x3dnv.x3d2usdphysics, loaded by
Newton's USD importer and stepped at 1/240 s on the CPU. The set-ups, ids and limits are the PhysX bridge's
(x3d.loom/x3d.physics/physx-bridge/evidence/p1-analytic.json and runs/physx-grand-cascade-*.physics.json), declared
there before its run, so the numbers compare engine against engine on one standard scene:

    free fall from 10 m, 1 s: height against the discrete semi-implicit Euler solution; velocity against -g t;
        the continuum gap against the integrator's 1/2 g h t
    pendulum, L 0.5 m, bob radius 1 cm, 0.05 rad, 8 periods, ball joint and hinge: period against 2 pi sqrt(I/(m g L))
    restitution e 0.6 from 0.5 m: rebound speed against e (v + g h), PhysX's law (worst of 5 bounces); the
        continuum law e v is reported beside it
    incline 30 deg: mu 0.3 slides at g (sin - mu cos); mu 0.7 holds
    tunnelling: a 5 m/s marble (radius 8 mm) against a 5 mm wall, 40 start phases

Plus three negative controls, each of which must fail:
    gravity off: the free-fall reference must miss
    a marble at 60 m/s must tunnel (the tunnelling test can see tunnelling)
    the pendulum without the declared collision filter pairs gains energy (Newton 1.8's importer gap)
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import newton_run as nr
from . import x3d2usdphysics as xw

G, H = 9.81, 1.0 / 240.0
PHYSX_LIMITS = {  # declared by the PhysX bridge before its run (runs/physx-grand-cascade-chromium.physics.json)
    "ff_h": 1e-4, "ff_v": 1e-4, "ff_gap": 1e-4, "pend_ball": 5e-3, "pend_hinge": 5e-3, "rest": 1e-3,
    "inc03": 2e-2, "inc07": 1e-3, "tunnel": 0.0}
IDS = {
    "ff_h": "free fall: height against the discrete semi-implicit Euler solution, 1 s (m)",
    "ff_v": "free fall: velocity against -g t, 1 s (m/s)",
    "ff_gap": "free fall: the continuum gap equals the integrator's 1/2 g h t (m)",
    "pend_ball": "pendulum, ball joint: period against 2 pi sqrt(I/(m g L)) (relative)",
    "pend_hinge": "pendulum, hinge joint: period against 2 pi sqrt(I/(m g L)) (relative)",
    "rest": "restitution: rebound speed against e (v + g h), worst of 5 bounces",
    "inc03": "incline 30 deg, mu 0.3: sliding acceleration against g (sin t - mu cos t) (relative)",
    "inc07": "incline 30 deg, mu 0.7: a body that must hold moved (m)",
    "tunnel": "tunnelling with CCD on: phases (of 40) in which a 5 m/s marble crossed a 5 mm wall",
}


def shape(geo, rgb="0.8 0.3 0.2"):
    return f"<Shape containerField='shape'><Appearance><Material diffuseColor='{rgb}'/></Appearance>{geo}</Shape>"


def body(name, geo, pos="0 0 0", rot="0 0 1 0", mass=1, fixed=False, vel=None, rgb="0.8 0.3 0.2", collide=True):
    v = f" linearVelocity='{vel}'" if vel else ""
    col = (f"<CollidableShape DEF='{name}C' containerField='geometry'>{shape(geo, rgb)}</CollidableShape>" if geo else "")
    return (f"<RigidBody DEF='{name}' containerField='bodies' position='{pos}' orientation='{rot}' mass='{mass}'"
            f" fixed='{'true' if fixed else 'false'}'{v}>{col}</RigidBody>"), (f"{name}C" if geo and collide else None)


def scene(bodies, joints="", gravity=f"0 -{G} 0", bounce=0.0, mu=0.0, min_bounce=0.01, title="reference"):
    xs, cs = zip(*bodies)
    colls = "".join(f"<CollidableShape USE='{c}' containerField='collidables'/>" for c in cs if c)
    cc = (f"<CollisionCollection DEF='Surfaces' containerField='collider' appliedParameters='\"BOUNCE\" \"FRICTION_COEFFICIENT-2\"'"
          f" bounce='{bounce}' minBounceSpeed='{min_bounce}' frictionCoefficients='{mu} {mu}'>{colls}</CollisionCollection>")
    return (f"<?xml version='1.0' encoding='UTF-8'?><X3D profile='Full' version='4.0'><head><meta name='title' content='{title}'/>"
            f"<meta name='creator' content='x3d.nVidia newton_refs'/><meta name='license' content='Apache-2.0'/></head><Scene>"
            f"<RigidBodyCollection gravity='{gravity}'>{''.join(xs)}{joints}{cc}</RigidBodyCollection></Scene></X3D>")


class Bench:
    def __init__(self, solver, work):
        self.solver, self.work = solver, Path(work)
        self.work.mkdir(parents=True, exist_ok=True)

    def sim(self, name, x3d, steps, filters=True):
        src, usd = self.work / f"{name}.x3d", self.work / f"{name}.usda"
        src.write_text(x3d)
        rep = xw.convert(src, usd)
        if filters:
            model, solver, info = nr.build(usd, self.solver)
        else:
            orig = nr.apply_declared_filters
            nr.apply_declared_filters = lambda b, p: 0
            try:
                model, solver, info = nr.build(usd, self.solver)
            finally:
                nr.apply_declared_filters = orig
        P, V, hashes = nr.run(model, solver, steps, H)
        return P, V, nr.body_labels(model), rep

    @staticmethod
    def idx(labels, name):
        return next(i for i, l in enumerate(labels) if l.endswith("/" + name))


def free_fall(b, gravity=True):
    n = 240
    P, V, lab, _ = b.sim("free_fall" + ("" if gravity else "_g0"), scene([body("Ball", "<Sphere radius='0.1'/>", pos="0 10 0")],
                         gravity=f"0 -{G} 0" if gravity else "0 0 0", title="free fall"), n)
    i = Bench.idx(lab, "Ball")
    z, vz = float(P[-1, i, 2]), float(V[-1, i, 2])        # USD +Z is X3D +Y; body_qd linear part first (Newton 1.x)
    disc = 10 - G * H * H * n * (n + 1) / 2
    cont = 10 - G * 1.0 / 2
    return {"ff_h": abs(z - disc), "ff_v": abs(vz + G * 1.0), "ff_gap": abs((cont - z) - G * H * 1.0 / 2),
            "_detail": {"y": z, "vy": vz, "discrete": disc, "continuum": cont}}


def pendulum(b, kind):
    L, r, th0 = 0.5, 0.01, 0.05
    piv = "0 1 0"
    bob_pos = f"{L * math.sin(th0)} {1 - L * math.cos(th0)} 0"
    jt = ("<BallJoint DEF='J' containerField='joints' anchorPoint='0 1 0'>" if kind == "ball" else
          "<SingleAxisHingeJoint DEF='J' containerField='joints' anchorPoint='0 1 0' axis='0 0 1'>")
    jt += ("<RigidBody USE='Bob' containerField='body1'/><RigidBody USE='Pivot' containerField='body2'/>"
           + ("</BallJoint>" if kind == "ball" else "</SingleAxisHingeJoint>"))
    I = 2 / 5 * r * r + L * L
    T = 2 * math.pi * math.sqrt(I / (G * L))
    steps = int(8.6 * T / H)
    P, V, lab, _ = b.sim(f"pendulum_{kind}", scene([body("Pivot", "<Box size='0.02 0.02 0.02'/>", pos=piv, fixed=True, collide=False),
                                                    body("Bob", f"<Sphere radius='{r}'/>", pos=bob_pos)], jt, title=f"pendulum {kind}"), steps)
    x = P[:, Bench.idx(lab, "Bob"), 0]
    t = np.arange(len(x)) * H
    up = [t[k] - x[k] * (t[k + 1] - t[k]) / (x[k + 1] - x[k]) for k in range(len(x) - 1) if x[k] < 0 <= x[k + 1]]
    periods = np.diff(up)
    Tm = float(periods.mean()) if len(periods) else float("nan")
    return {f"pend_{kind}": abs(Tm - T) / T if len(periods) else 1.0,
            "_detail": {"T": Tm, "expected": T, "periods": int(len(periods)), "spread": float(np.ptp(periods)) if len(periods) else None}}


def restitution(b):
    e, h0, r = 0.6, 0.5, 0.05
    steps = int(4.0 / H)
    P, V, lab, _ = b.sim("restitution", scene([body("Ground", "<Box size='4 0.2 4'/>", pos="0 -0.1 0", fixed=True, rgb="0.4 0.4 0.45"),
                                               body("Ball", f"<Sphere radius='{r}'/>", pos=f"0 {h0 + r} 0")], bounce=e, title="restitution"), steps)
    vz = V[:, Bench.idx(lab, "Ball"), 2]
    # engine-neutral bounce events: an impulsive engine (PhysX) turns the velocity round in one step, a soft-contact
    # engine (MuJoCo) over several. Each turn-around (vz from < 0 to > 0) is one bounce: the impact speed is the fastest
    # descent since the previous turn-around, the rebound the fastest ascent before the next descent
    turns = [k for k in range(len(vz) - 1) if vz[k] < 0 <= vz[k + 1]]
    ev, prev = [], 0
    for n_, k in enumerate(turns):
        nxt = turns[n_ + 1] if n_ + 1 < len(turns) else len(vz) - 1
        vi = float(-vz[prev:k + 1].min())
        seg = vz[k + 1:nxt + 1]
        down = np.nonzero(seg < 0)[0]
        vr = float(seg[:down[0]].max() if len(down) and down[0] > 0 else seg.max())
        if vi > 0.05:
            ev.append((k, vi, vr))
        prev = k + 1
    worst_physx, worst_cont, rows = 0.0, 0.0, []
    for k, vi, vr in ev[:5]:
        px, ct = e * (vi + G * H), e * vi
        worst_physx = max(worst_physx, abs(vr - px) / px)
        worst_cont = max(worst_cont, abs(vr - ct) / ct)
        rows.append({"impact": float(vi), "rebound": float(vr), "physx_law": float(px), "continuum_law": float(ct)})
    return {"rest": worst_physx if len(ev) >= 5 else 1.0,
            "_detail": {"bounces": rows, "found": len(ev), "worst_vs_continuum_e_v": worst_cont}}


def incline(b, mu):
    th = math.radians(30)
    n = np.array([-math.sin(th), math.cos(th), 0.0])              # surface normal, plane rotated +30 deg about z
    d = np.array([-math.cos(th), -math.sin(th), 0.0])             # down-slope direction
    c = n * (0.05 + 0.0005)
    rot = f"0 0 1 {th}"
    slab = n * -0.05
    steps = int(0.6 / H)
    P, V, lab, _ = b.sim(f"incline_{mu}", scene([body("Slope", "<Box size='4 0.1 1'/>", pos=" ".join(map(str, slab)), rot=rot, fixed=True, rgb="0.4 0.4 0.45"),
                                                 body("Block", "<Box size='0.1 0.1 0.1'/>", pos=" ".join(map(str, c)), rot=rot)], mu=mu, title=f"incline mu {mu}"), steps)
    p = P[:, Bench.idx(lab, "Block"), :3]
    du = xw.C @ d
    s = (p - p[0]) @ du
    t = np.arange(len(s)) * H
    a_exp = G * (math.sin(th) - mu * math.cos(th))
    if mu < math.tan(th):
        m = (t >= 0.1)
        a = float(np.polyfit(t[m], s[m], 2)[0] * 2)
        return {"inc03": abs(a - a_exp) / a_exp, "_detail": {"a": a, "expected": a_exp, "travelled": float(s[-1])}}
    k0 = int(0.05 / H)                                  # after the block has settled its 0.5 mm onto the slope
    moved = float(abs(s[int(0.55 / H)] - s[k0]))         # along the slope, as the PhysX evidence's "travelled"
    return {"inc07": moved, "_detail": {"travelled_along_slope_0.05_to_0.55s": moved, "expected": 0.0,
                                        "settle_drop": float(np.linalg.norm(p[k0] - p[0]))}}


def tunnelling(b, speed=5.0, tag="tunnel"):
    crossed = 0
    for ph in range(40):
        x0 = -0.05 - (ph / 40) * speed * H
        P, V, lab, _ = b.sim(f"{tag}_{ph:02d}", scene([body("Wall", "<Box size='0.005 0.5 0.5'/>", pos="0 0 0", fixed=True, rgb="0.4 0.4 0.45"),
                                                     body("Marble", "<Sphere radius='0.008'/>", pos=f"{x0} 0 0", vel=f"{speed} 0 0", mass=0.002)],
                                                    gravity="0 0 0", title="tunnelling"), int(0.08 / H))
        if float(P[-1, Bench.idx(lab, "Marble"), 0]) > 0.0:
            crossed += 1
    return {tag: float(crossed), "_detail": {"speed": speed, "phases": 40, "crossed": crossed}}


def pendulum_energy(b, filters):
    """The importer-gap control: the wrecking ball whose bob overlaps its pivot (physx-bridge pieces/pendulum.x3d)."""
    src = Path(__file__).resolve().parents[3] / "x3d.loom/x3d.physics/physx-bridge/scenes/pieces/pendulum.x3d"
    if not src.exists():
        return None
    P, V, lab, _ = b.sim("wrecking_ball" + ("" if filters else "_nofilter"), src.read_text(), 960, filters=filters)
    z = P[:, Bench.idx(lab, "P1BobBody"), 2]
    if not np.all(np.isfinite(z)):
        return float("inf")                 # the state blew up (non-finite): the control has failed, loudly
    return float(z.max() - z[0])


def substep_sweep(b, subs=(1, 2, 4, 10)):
    """Not a reference: the hinge pendulum's period error against substeps per 1/240 s step (where a solver converges)."""
    L, r, th0 = 0.5, 0.01, 0.05
    I = 2 / 5 * r * r + L * L
    T = 2 * math.pi * math.sqrt(I / (G * L))
    src = b.work / "pendulum_hinge.usda"
    out = []
    for k in subs:
        model, solver, _ = nr.build(src, b.solver)
        P, V, _h = nr.run(model, solver, int(8.6 * T / H), H, substeps=k)
        x = P[:, 0, 0]
        t = np.arange(len(x)) * H
        up = [t[i] - x[i] * (t[i + 1] - t[i]) / (x[i + 1] - x[i]) for i in range(len(x) - 1) if x[i] < 0 <= x[i + 1]]
        out.append({"substeps": k, "dt": H / k, "period_rel_err": float(abs(np.diff(up).mean() - T) / T) if len(up) > 2 else None})
    return out


def suite(solver, work):
    b = Bench(solver, work)
    obs, detail = {}, {}
    for fn in (lambda: free_fall(b), lambda: pendulum(b, "ball"), lambda: pendulum(b, "hinge"), lambda: restitution(b),
               lambda: incline(b, 0.3), lambda: incline(b, 0.7), lambda: tunnelling(b)):
        r = fn()
        detail.update({k: r["_detail"] for k in r if k != "_detail"})
        obs.update({k: v for k, v in r.items() if k != "_detail"})
    refs = []
    for k in IDS:
        lim, ob = PHYSX_LIMITS[k], float(obs[k])
        refs.append({"id": IDS[k], "observed": ob, "limit": lim, "declared_limit": lim, "rule": "at most",
                     "status": "pass" if ob <= lim else "fail", "detail": detail.get(k),
                     "source": "x3dnv.newton_refs (set-up and limit: physx-bridge p1-analytic.json)"})
    ctl = []
    g0 = free_fall(b, gravity=False)
    ctl.append({"id": "gravity off: the free-fall height reference must miss", "expect": "fail",
                "observed": g0["ff_h"], "observed_failed": bool(g0["ff_h"] > PHYSX_LIMITS["ff_h"])})
    fast = tunnelling(b, speed=60.0, tag="tunnel60")
    ctl.append({"id": "a 60 m/s marble must tunnel the 5 mm wall in some phase (the test can see tunnelling)", "expect": "fail",
                "observed": fast["tunnel60"], "observed_failed": bool(fast["tunnel60"] > 0)})
    gain_on, gain_off = pendulum_energy(b, True), pendulum_energy(b, False)
    if gain_off is not None:
        ctl.append({"id": "wrecking ball without the declared filter pairs: the bob rises above its start (> 1 mm) or blows up",
                    "expect": "fail", "observed": gain_off if math.isfinite(gain_off) else None,
                    "blew_up": not math.isfinite(gain_off), "with_filters": gain_on, "observed_failed": bool(gain_off > 1e-3)})
    return {"solver": solver, "references": refs, "controls": ctl, "substep_sweep": substep_sweep(b)}


if __name__ == "__main__":
    a = sys.argv[1:]
    solver = a[a.index("--solver") + 1] if "--solver" in a else "xpbd"
    work = a[a.index("--work") + 1] if "--work" in a else tempfile.mkdtemp(prefix=f"refs_{solver}_")
    out = suite(solver, work)
    Path(a[0]).write_text(json.dumps(out, indent=1, default=float))
    for r in out["references"]:
        print(f"{r['status']:4s} {r['observed']:.3e} <= {r['limit']:.0e}  {r['id']}")
    for c in out["controls"]:
        print(f"ctrl {'failed (good)' if c['observed_failed'] else 'SURVIVED'} {c['observed']}  {c['id']}")
