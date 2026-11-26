"""Toppling-wave speed of a domino run from a Newton trajectory, in the units of the PhysX bridge's study:
v / sqrt(g H) against gap / H (Larham, arXiv:1302.3311, as cited in physx-bridge SPEC.md).

    python domino_wave.py TRAJ.npz [--height 0.0516] [--thickness 0.0079] [--tilt 30]

A domino has fallen when it has turned more than --tilt degrees from its start. The wave speed is the slope of a
straight-line fit of path length (along the run, domino to domino) against fall time over the middle 60 % of the
dominoes (start-up and the last ones left out). A median of single spacings / time differences is not used: fall times
are sampled per frame, and at these speeds one spacing takes about one frame, so that median returns the frame rate."""
import json
import re
import sys

import numpy as np

A = sys.argv[1:]
opt = lambda k, d: float(A[A.index(k) + 1]) if k in A else d
g, H, T, TILT = 9.81, opt("--height", 0.0516), opt("--thickness", 0.0079), opt("--tilt", 30)
d = np.load(A[0])
P, L = d["poses"], [str(x) for x in d["labels"]]
dt = float(d["dt"]) * int(d["keep_every"])
idx = sorted((int(m.group(1)), k) for k, l in enumerate(L) if (m := re.search(r"/D(\d+)Body$", l)))
ks = [k for _, k in idx]
q = P[:, ks, 3:7]
ang = np.degrees(2 * np.arccos(np.clip(np.abs((q * q[0]).sum(-1)), -1, 1)))
tf = [float(np.argmax(ang[:, i] > TILT) * dt) if (ang[:, i] > TILT).any() else None for i in range(len(ks))]
seg = np.linalg.norm(np.diff(P[0, ks, :2], axis=0), axis=1)
rows = [(seg[i - 1], seg[i - 1] / (tf[i] - tf[i - 1])) for i in range(1, len(ks))
        if tf[i] is not None and tf[i - 1] is not None and tf[i] > tf[i - 1] and seg[i - 1] < 4 * H]
out = {"dominoes": len(ks), "fallen": sum(t is not None for t in tf), "last_fall_s": max([t for t in tf if t is not None], default=None)}
# the run can hold several rows (strokes): a gap of more than 4 H starts a new one; the longest row is measured
breaks = [0] + [i + 1 for i in range(len(seg)) if seg[i] >= 4 * H] + [len(ks)]
r0, r1 = max(zip(breaks[:-1], breaks[1:]), key=lambda ab: ab[1] - ab[0])
out.update(rows=len(breaks) - 1, row_measured=[int(r0), int(r1)])
path = np.full(len(ks), np.nan)
path[r0:r1] = np.concatenate([[0.0], np.cumsum(seg[r0:r1 - 1])])
ok = [i for i in range(r0, r1) if tf[i] is not None]
if len(ok) >= 10:
    mid = ok[len(ok) // 5: len(ok) - len(ok) // 5]
    slope, icpt = np.polyfit([tf[i] for i in mid], [path[i] for i in mid], 1)
    resid = np.array([path[i] - (slope * tf[i] + icpt) for i in mid])
    s = float(np.median(seg[seg < 4 * H]))
    out.update(v_over_sqrt_gH=float(slope / np.sqrt(g * H)), v_m_s=float(slope), fit_rms_m=float(np.sqrt((resid ** 2).mean())),
               gap_over_H=float((s - T) / H), spacing_m=s, fitted=len(mid), fall_times=tf)
print(json.dumps({k: v for k, v in out.items() if k != "fall_times"}))
if "--json" in A:
    open(A[A.index("--json") + 1], "w").write(json.dumps(out))
