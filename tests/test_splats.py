import math
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from x3dnv import splats as S
from x3dnv.galaxy import galaxy_world, make_galaxy

pxr = pytest.importorskip  # alias for readability below


def tiny(degree=3, n=7, frame="colmap"):
    rng = np.random.default_rng(1)
    k = (degree + 1) ** 2
    return S.SplatCloud(rng.normal(size=(n, 3)), S.normalize(rng.normal(size=(n, 4))),
                        rng.uniform(0.01, 0.2, (n, 3)), rng.uniform(0.05, 0.95, n),
                        rng.normal(size=(n, k, 3)) * 0.3, frame=frame)


def close(a, b, tol=2e-6):
    d = a.equal(b)
    assert d["n"][0] == d["n"][1] and d["degree"][0] == d["degree"][1]
    for k in ("positions", "rotations", "scales", "opacities", "sh"):
        assert d[k] <= tol, (k, d[k])
    assert a.frame == b.frame


@pytest.mark.parametrize("ext", [".ply", ".x3d", ".glb"])
@pytest.mark.parametrize("degree", [0, 1, 3])
def test_round_trip(tmp_path, ext, degree):
    c = tiny(degree)
    p = S.WRITERS[ext](c, tmp_path / f"t{ext}")
    close(c, S.READERS[ext](p))


@pytest.mark.parametrize("degree", [0, 3])
def test_round_trip_usd(tmp_path, degree):
    pytest.importorskip("pxr.UsdVol")
    from pxr import UsdVol

    if not hasattr(UsdVol, "ParticleField3DGaussianSplat"):
        pytest.skip("usd-core < 26.03")
    c = tiny(degree)
    p = S.write_usd(c, tmp_path / "t.usda")
    close(c, S.read_usd(p))
    txt = p.read_text()
    assert "ParticleField3DGaussianSplat" in txt and "rotateX = 180" in txt
    assert f"elementSize = {(degree + 1) ** 2}" in txt


def test_ply_edge_encodings(tmp_path):
    """The PLY edge is where log/logit/wxyz/channel-major live (X_ITE 16.8.1 rules)."""
    c = tiny(1, n=2)
    p = S.write_ply(c, tmp_path / "t.ply")
    raw = p.read_bytes()
    hdr, body = raw.split(b"end_header\n")
    names = [l.split()[-1].decode() for l in hdr.splitlines() if l.startswith(b"property")]
    v = np.frombuffer(body, "<f4").reshape(2, len(names))
    col = {n: v[:, i] for i, n in enumerate(names)}
    np.testing.assert_allclose(np.exp(col["scale_0"]), c.scales[:, 0], rtol=1e-6)
    np.testing.assert_allclose(1 / (1 + np.exp(-col["opacity"])), c.opacities, rtol=1e-5)
    np.testing.assert_allclose(col["rot_0"], c.rotations[:, 3], rtol=1e-6)  # w first
    # channel-major rest: f_rest_0..2 = R of coeffs 1..3, f_rest_3..5 = G
    np.testing.assert_allclose(col["f_rest_0"], c.sh[:, 1, 0], rtol=1e-6)
    np.testing.assert_allclose(col["f_rest_3"], c.sh[:, 1, 1], rtol=1e-6)


def test_x3d_fields_and_frame(tmp_path):
    c = tiny(2, n=3)
    p = S.write_x3d(c, tmp_path / "t.x3d")
    root = ET.parse(p).getroot()
    assert root.get("version") == "4.1"
    assert any(e.get("name") == "GaussianSplats" for e in root.iter("component"))
    frame = next(t for t in root.iter("Transform") if t.get("DEF") == "SplatFrame")
    x, y, z, a = map(float, frame.get("rotation").split())
    assert (x, y, z) == (1, 0, 0) and math.isclose(a, math.pi, rel_tol=1e-8)
    gs = next(root.iter("GaussianSplats"))
    assert gs.get("sphericalHarmonicsDegree2Coef4") and not gs.get("sphericalHarmonicsDegree3Coef0")
    assert len(gs.get("orientations").split()) == 12


def test_inline_ply_route(tmp_path):
    c = tiny(0)
    p = S.write_x3d(c, tmp_path / "i.x3d", inline_ply="cloud.ply")
    root = ET.parse(p).getroot()
    assert next(root.iter("Inline")).get("url") == '"cloud.ply"'
    assert not list(root.iter("GaussianSplats"))


def test_glb_extension_block(tmp_path):
    import json, struct

    c = tiny(1)
    raw = S.write_glb(c, tmp_path / "t.glb").read_bytes()
    jl = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20:20 + jl])
    prim = g["meshes"][0]["primitives"][0]
    assert prim["mode"] == 0
    assert prim["extensions"]["KHR_gaussian_splatting"]["kernel"] == "ellipse"
    assert prim["extensions"]["KHR_gaussian_splatting"]["colorSpace"] == "srgb_rec709_display"
    assert "COLOR_0" in prim["attributes"] and "KHR_gaussian_splatting:SH_DEGREE_1_COEF_2" in prim["attributes"]
    np.testing.assert_allclose(g["nodes"][0]["rotation"], [1, 0, 0, 0], atol=1e-12)


def test_checks_catch_bad_data():
    c = tiny(0, n=3)
    c.opacities[0] = 1.5
    c.scales[1, 0] = -1
    c.rotations[2] = [0, 0, 0, 2]
    probs = " ".join(c.check())
    assert "opacities" in probs and "negative scales" in probs and "unit" in probs


def test_galaxy_world(tmp_path):
    g = make_galaxy(n=500)
    assert g.check() == [] and g.degree == 1
    p = galaxy_world(tmp_path / "g.x3d", g)
    root = ET.parse(p).getroot()
    routes = list(root.iter("ROUTE"))
    defs = {e.get("DEF") for e in root.iter() if e.get("DEF")}
    assert {r.get("toNode") for r in routes} <= defs and {r.get("fromNode") for r in routes} <= defs
    close(g, S.read_x3d(p), tol=1e-4)  # 6 significant digits in this world file
