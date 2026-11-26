"""A procedural Gaussian-splat galaxy, and an X3D world built around it.

Not trained data: every splat is placed by formula, so the repo can ship it
under its own licence. It exercises SH degree 1 (a view-dependent tint, so
the higher bands of every converter are on the path) and X3D behaviour that
the other splat formats have no words for: Viewpoints, a TimeSensor-driven
rotation ROUTEd into the splats' parent, a NavigationInfo, and metadata.
"""
from __future__ import annotations

import math
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from .splats import SH_C0, SplatCloud, normalize, write_x3d


def _quat_from_axis_angle(axis, ang):
    axis = axis / np.linalg.norm(axis, axis=1, keepdims=True)
    s = np.sin(ang / 2)[:, None]
    return np.concatenate([axis * s, np.cos(ang / 2)[:, None]], 1)


def make_galaxy(n: int = 12000, arms: int = 2, seed: int = 7, degree: int = 1) -> SplatCloud:
    rng = np.random.default_rng(seed)
    nb = n // 5  # bulge
    nd = n - nb  # disc
    # Disc: logarithmic spiral arms with scatter, thin in y.
    r = rng.gamma(2.2, 0.55, nd).clip(0.15, 4.0)
    arm = rng.integers(0, arms, nd)
    pitch = 0.28
    theta = np.log(r / 0.15) / math.tan(pitch) + arm * (2 * math.pi / arms)
    theta += rng.normal(0, 0.28, nd) * (0.6 + 0.4 / (r + 0.3))
    y = rng.normal(0, 0.04 + 0.02 * r, nd)
    disc = np.stack([r * np.cos(theta), y, r * np.sin(theta)], 1)
    # Bulge: flattened Gaussian.
    bulge = rng.normal(0, [0.35, 0.18, 0.35], (nb, 3))
    pos = np.concatenate([disc, bulge]).astype(np.float32)

    rad = np.linalg.norm(pos[:, [0, 2]], axis=1)
    # Colour: warm core -> blue-white arms; a few pink HII knots.
    t = np.clip(rad / 3.0, 0, 1)[:, None]
    core = np.array([1.0, 0.78, 0.45])
    arm_c = np.array([0.55, 0.7, 1.0])
    col = (1 - t) * core + t * arm_c
    knots = rng.random(n) < 0.015
    col[knots] = [1.0, 0.35, 0.65]
    col *= rng.uniform(0.7, 1.15, (n, 1))
    col = np.clip(col, 0.02, 1.0)

    # Shape: flattened ellipsoids tangent to the disc, small for stars, larger for dust.
    base = np.where(knots, 0.05, 0.022) * rng.uniform(0.6, 1.6, n)
    scales = np.stack([base * 1.8, base * 0.35, base], 1).astype(np.float32)
    scales[nd:] = (rng.uniform(0.02, 0.06, (nb, 1)) * [1, 0.7, 1]).astype(np.float32)
    up = np.tile([[0.0, 1.0, 0.0]], (n, 1))
    rot = normalize(_quat_from_axis_angle(up, -np.arctan2(pos[:, 2], pos[:, 0])))
    opac = np.clip(rng.beta(2.5, 1.6, n) * np.where(knots, 1.0, 0.85), 0.05, 0.99).astype(np.float32)

    k = (degree + 1) ** 2
    sh = np.zeros((n, k, 3), np.float32)
    sh[:, 0] = (col - 0.5) / SH_C0
    if degree >= 1:
        # A gentle view-dependent tint. In the 3DGS/X_ITE degree-1 basis the
        # colour gains C1 * (-y*sh[1] + z*sh[2] - x*sh[3]) for view direction
        # (x, y, z) from camera to splat. Seen from above, y < 0, so sh[1]
        # pushes blue up there; edge-on (y ~ 0) it has no effect.
        sh[:, 1] = np.array([-0.06, 0.0, 0.14])
    return SplatCloud(pos, rot, scales, opac, sh, frame="none",
                      meta={"generator": "x3dnv.galaxy", "seed": seed, "n": n, "arms": arms})


def galaxy_world(path: str | Path, cloud: SplatCloud | None = None, period_s: float = 120.0) -> Path:
    cloud = cloud or make_galaxy()
    nav = ET.Element("NavigationInfo", {"type": '"EXAMINE" "ANY"', "headlight": "false"})
    bg = ET.Element("Background", {"skyColor": "0.005 0.006 0.012"})
    clock = ET.Element("TimeSensor", {"DEF": "Spin", "cycleInterval": str(period_s), "loop": "true"})
    interp = ET.Element("OrientationInterpolator", {
        "DEF": "SpinAngle", "key": "0 0.5 1",
        "keyValue": f"0 1 0 0 0 1 0 {math.pi:.6f} 0 1 0 {2*math.pi:.6f}"})
    routes = [ET.Element("ROUTE", {"fromNode": "Spin", "fromField": "fraction_changed",
                                   "toNode": "SpinAngle", "toField": "set_fraction"}),
              ET.Element("ROUTE", {"fromNode": "SpinAngle", "fromField": "value_changed",
                                   "toNode": "SplatRoot", "toField": "set_rotation"})]
    vps = [
        {"DEF": "Tilted", "description": "Tilted", "position": "0 4.6 9.5",
         "orientation": f"-1 0 0 {math.atan2(4.6, 9.5):.6f}", "centerOfRotation": "0 0 0"},
        {"DEF": "FaceOn", "description": "Face on", "position": "0 11.5 0",
         "orientation": f"-1 0 0 {math.pi/2:.6f}"},
        {"DEF": "EdgeOn", "description": "Edge on", "position": "0 0.2 11"},
    ]
    p = write_x3d(cloud, path, title="x3d.nVidia splat galaxy", viewpoints=vps,
                  extra_children=[nav, bg, clock, interp], meta=cloud.meta, prec=6)
    # ROUTEs must come after the nodes they name: append them at the end of Scene.
    tree = ET.parse(p)
    scene = tree.getroot().find("Scene")
    for rt in routes:
        scene.append(rt)
    ET.indent(tree.getroot(), "  ")
    head = p.read_text().split("<X3D", 1)[0]
    p.write_text(head + ET.tostring(tree.getroot(), encoding="unicode") + "\n")
    return p
