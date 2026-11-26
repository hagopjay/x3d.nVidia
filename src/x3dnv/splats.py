"""Splat Rosetta: one Gaussian splat cloud, four standards.

    3DGS .ply  <->  SplatCloud  <->  X3D 4.1 GaussianSplats
                                <->  OpenUSD 26.03 ParticleField3DGaussianSplat
                                <->  glTF 2.0 KHR_gaussian_splatting (.glb)

The canonical in-memory form (``SplatCloud``) uses the encoding that X3D 4.1,
KHR_gaussian_splatting and the X_ITE GaussianSplats node all share:

* positions   float32 (N, 3)
* rotations   float32 (N, 4) unit quaternions, **x, y, z, w**
* scales      float32 (N, 3) **linear**, >= 0
* opacities   float32 (N,)   **linear**, 0..1
* sh          float32 (N, K, 3) raw SH coefficients, K = (degree + 1) ** 2,
              ordered l = 0..3, then m = -l..l (the 3DGS / glTF order).
              Colour = 0.5 + C0 * sh[:, 0] + higher bands.

The 3DGS training PLY stores log scales, logit opacities, w-first quaternions
and channel-major ``f_rest_*``. Those are converted only at the PLY edge.

Frame: 3DGS training output is usually in a Y-down (COLMAP/OpenCV) frame.
X_ITE 16.8.1, when it inlines a .ply, wraps the splats in
``Transform { rotation 1 0 0 pi }``. We never bake that into the arrays (so the
round trip is lossless); each writer puts it on a parent transform instead.
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

import numpy as np

SH_C0 = 0.28209479177387814
SH_COUNTS = (1, 3, 5, 7)  # coefficients per degree
FRAME_ROTATIONS = {
    # name -> axis-angle (x, y, z, angle) applied on a parent node
    "none": None,
    "colmap": (1.0, 0.0, 0.0, math.pi),  # what X_ITE 16.8.1 does for Inline .ply
}


def k_for_degree(d: int) -> int:
    return (d + 1) ** 2


def degree_for_k(k: int) -> int:
    d = int(round(math.sqrt(k))) - 1
    if k_for_degree(d) != k:
        raise ValueError(f"{k} SH coefficients is not (d+1)^2 for d in 0..3")
    return d


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p, eps=1e-7):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


@dataclass
class SplatCloud:
    positions: np.ndarray
    rotations: np.ndarray  # xyzw
    scales: np.ndarray  # linear
    opacities: np.ndarray  # linear 0..1
    sh: np.ndarray  # (N, K, 3)
    color_space: str = "SRGB_REC709_DISPLAY"  # X3D spelling
    frame: str = "none"  # parent-node rotation, see FRAME_ROTATIONS
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.positions = np.asarray(self.positions, np.float32).reshape(-1, 3)
        n = len(self.positions)
        self.rotations = np.asarray(self.rotations, np.float32).reshape(n, 4)
        self.scales = np.asarray(self.scales, np.float32).reshape(n, 3)
        self.opacities = np.asarray(self.opacities, np.float32).reshape(n)
        sh = np.asarray(self.sh, np.float32)
        self.sh = sh.reshape(n, -1, 3)
        degree_for_k(self.sh.shape[1])
        if self.frame not in FRAME_ROTATIONS:
            raise ValueError(f"unknown frame {self.frame!r}")

    # ------------------------------------------------------------------ info
    @property
    def n(self) -> int:
        return len(self.positions)

    @property
    def degree(self) -> int:
        return degree_for_k(self.sh.shape[1])

    def base_color(self) -> np.ndarray:
        """Diffuse colour (N, 3) in the cloud's colour space, clamped 0..1."""
        return np.clip(0.5 + SH_C0 * self.sh[:, 0], 0.0, 1.0)

    def extent(self) -> tuple[np.ndarray, np.ndarray]:
        r = 3.0 * self.scales.max(axis=1, keepdims=True)
        return (self.positions - r).min(0), (self.positions + r).max(0)

    def check(self) -> list[str]:
        """Encoding rules shared by X3D 4.1, KHR_gaussian_splatting and USD VG.035."""
        problems = []
        qn = np.linalg.norm(self.rotations, axis=1)
        if np.any(np.abs(qn - 1) > 1e-3):
            problems.append(f"{int((np.abs(qn-1)>1e-3).sum())} rotations not unit length")
        if np.any(self.scales < 0):
            problems.append("negative scales")
        if np.any((self.opacities < 0) | (self.opacities > 1)):
            problems.append("opacities outside 0..1")
        for name in ("positions", "rotations", "scales", "opacities", "sh"):
            if not np.all(np.isfinite(getattr(self, name))):
                problems.append(f"non-finite {name}")
        return problems

    def equal(self, other: "SplatCloud", atol=1e-5) -> dict:
        """Max abs difference per array (quaternion sign-agnostic)."""
        q = np.abs(np.sum(self.rotations * other.rotations, axis=1))
        return {
            "n": (self.n, other.n),
            "degree": (self.degree, other.degree),
            "positions": float(np.abs(self.positions - other.positions).max(initial=0)),
            "rotations": float(np.abs(1 - q).max(initial=0)),
            "scales": float(np.abs(self.scales - other.scales).max(initial=0)),
            "opacities": float(np.abs(self.opacities - other.opacities).max(initial=0)),
            "sh": float(np.abs(self.sh - other.sh).max(initial=0)),
        }

    def subset(self, idx) -> "SplatCloud":
        return SplatCloud(self.positions[idx], self.rotations[idx], self.scales[idx],
                          self.opacities[idx], self.sh[idx], self.color_space, self.frame,
                          dict(self.meta))

    def truncate_degree(self, d: int) -> "SplatCloud":
        return SplatCloud(self.positions, self.rotations, self.scales, self.opacities,
                          self.sh[:, : k_for_degree(d)], self.color_space, self.frame,
                          dict(self.meta))


def normalize(q: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(q, axis=1, keepdims=True)
    n[n == 0] = 1
    return (q / n).astype(np.float32)


# ====================================================================== PLY
_PLY_TYPES = {
    "float": "f4", "float32": "f4", "double": "f8", "float64": "f8",
    "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
    "ushort": "u2", "uint16": "u2", "short": "i2", "int16": "i2",
    "uint": "u4", "uint32": "u4", "int": "i4", "int32": "i4",
}


def read_ply(path: str | Path, frame: str = "colmap") -> SplatCloud:
    """Read a 3DGS training .ply (binary little endian), as X_ITE 16.8.1 does.

    exp(scale_i), sigmoid(opacity), rot_0..3 (w x y z) -> x y z w, f_dc raw,
    f_rest channel-major (all R, then all G, then all B) -> (N, K-1, 3).
    """
    raw = Path(path).read_bytes()
    end = raw.index(b"end_header") + len(b"end_header")
    end = raw.index(b"\n", end) + 1
    header = raw[:end].decode("ascii", "replace").splitlines()
    if "format binary_little_endian 1.0" not in header:
        raise ValueError("only binary_little_endian PLY is supported")
    count, props, in_vertex = 0, [], False
    for line in header:
        parts = line.split()
        if parts[:2] == ["element", "vertex"]:
            count, in_vertex = int(parts[2]), True
        elif parts[:1] == ["element"]:
            in_vertex = False
        elif parts[:1] == ["property"] and in_vertex:
            if parts[1] == "list":
                raise ValueError("list property in vertex element")
            props.append((parts[2], "<" + _PLY_TYPES[parts[1]]))
    dt = np.dtype(props)
    v = np.frombuffer(raw, dtype=dt, count=count, offset=end)
    names = set(dt.names)
    pos = np.stack([v["x"], v["y"], v["z"]], 1)
    rot = normalize(np.stack([v["rot_1"], v["rot_2"], v["rot_3"], v["rot_0"]], 1))
    scales = np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1))
    opac = sigmoid(v["opacity"].astype(np.float64))
    dc = np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], 1)[:, None, :]
    n_rest = sum(1 for nm in names if nm.startswith("f_rest_"))
    if n_rest:
        rest = np.stack([v[f"f_rest_{i}"] for i in range(n_rest)], 1)  # (N, 3*(K-1))
        km1 = n_rest // 3
        rest = rest.reshape(count, 3, km1).transpose(0, 2, 1)  # (N, K-1, 3)
        sh = np.concatenate([dc, rest], 1)
    else:
        sh = dc
    return SplatCloud(pos, rot, scales, opac, sh, frame=frame,
                      meta={"source": str(path), "ply_properties": len(props)})


def write_ply(cloud: SplatCloud, path: str | Path) -> Path:
    km1 = cloud.sh.shape[1] - 1
    names = (["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
             + [f"f_rest_{i}" for i in range(3 * km1)]
             + ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"])
    n = cloud.n
    cols = [cloud.positions, np.zeros((n, 3), np.float32), cloud.sh[:, 0],
            cloud.sh[:, 1:].transpose(0, 2, 1).reshape(n, 3 * km1),
            logit(cloud.opacities.astype(np.float64))[:, None],
            np.log(np.maximum(cloud.scales, 1e-30)),
            cloud.rotations[:, [3, 0, 1, 2]]]
    data = np.concatenate([np.asarray(c, np.float32).reshape(n, -1) for c in cols], 1)
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {n}"]
    head += [f"property float {nm}" for nm in names] + ["end_header"]
    p = Path(path)
    p.write_bytes(("\n".join(head) + "\n").encode() + np.ascontiguousarray(data, "<f4").tobytes())
    return p


# ====================================================================== X3D
def _fmt(a: np.ndarray, prec: int = 7) -> str:
    return " ".join(f"{x:.{prec}g}" for x in np.asarray(a, np.float64).ravel())


def _sh_field(d: int, c: int) -> str:
    return f"sphericalHarmonicsDegree{d}Coef{c}"


def gaussian_splats_element(cloud: SplatCloud, def_name: str | None = "Splats",
                            prec: int = 7) -> ET.Element:
    el = ET.Element("GaussianSplats")
    if def_name:
        el.set("DEF", def_name)
    if cloud.color_space != "SRGB_REC709_DISPLAY":
        el.set("colorSpace", cloud.color_space)
    el.set("positions", _fmt(cloud.positions, prec))
    el.set("orientations", _fmt(cloud.rotations, prec))
    el.set("scales", _fmt(cloud.scales, prec))
    el.set("opacities", _fmt(cloud.opacities, prec))
    i = 0
    for d, cnt in enumerate(SH_COUNTS[: cloud.degree + 1]):
        for c in range(cnt):
            el.set(_sh_field(d, c), _fmt(cloud.sh[:, i], prec))
            i += 1
    return el


def write_x3d(cloud: SplatCloud, path: str | Path, *, title: str = "Splats",
              inline_ply: str | None = None, extra_children: Iterable[ET.Element] = (),
              viewpoints: Iterable[dict] = (), prec: int = 7, meta: dict | None = None) -> Path:
    """Write an X3D 4.1 scene holding the cloud as a native GaussianSplats node.

    ``inline_ply`` instead writes ``Inline { url "<file>.ply" }`` (X_ITE's own
    example route); X_ITE then applies the COLMAP frame itself.
    """
    root = ET.Element("X3D", {
        "profile": "Interchange", "version": "4.1",
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema-instance",
        "xsd:noNamespaceSchemaLocation": "https://www.web3d.org/specifications/x3d-4.1.xsd"})
    head = ET.SubElement(root, "head")
    if not inline_ply:
        ET.SubElement(head, "component", {"name": "GaussianSplats", "level": "1"})
    for k, v in {"title": title, "generator": "x3d.nVidia x3dnv.splats",
                 **{f"x3dnv:{k}": str(v) for k, v in (meta or {}).items()}}.items():
        ET.SubElement(head, "meta", {"name": k, "content": v})
    scene = ET.SubElement(root, "Scene")
    ET.SubElement(scene, "WorldInfo", {"title": title})
    for vp in viewpoints:
        ET.SubElement(scene, "Viewpoint", {k: str(v) for k, v in vp.items()})
    for ch in extra_children:
        scene.append(ch)
    holder = ET.SubElement(scene, "Transform", {"DEF": "SplatRoot"})
    if inline_ply:
        ET.SubElement(holder, "Inline", {"DEF": "SplatInline", "url": f'"{inline_ply}"'})
    else:
        rot = FRAME_ROTATIONS[cloud.frame]
        frame_parent = holder
        if rot:
            frame_parent = ET.SubElement(holder, "Transform", {
                "DEF": "SplatFrame", "rotation": " ".join(f"{x:.9g}" for x in rot)})
        frame_parent.append(gaussian_splats_element(cloud, prec=prec))
    ET.indent(root, "  ")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 4.1//EN" '
           '"https://www.web3d.org/specifications/x3d-4.1.dtd">\n'
           + ET.tostring(root, encoding="unicode") + "\n")
    p = Path(path)
    p.write_text(xml, encoding="utf-8")
    return p


def read_x3d(path: str | Path) -> SplatCloud:
    """Read the first GaussianSplats node of an X3D XML file."""
    tree = ET.parse(path)
    el = next(tree.getroot().iter("GaussianSplats"))
    frame = "none"
    for t in tree.getroot().iter("Transform"):
        if t.get("DEF") == "SplatFrame":
            frame = "colmap"

    def arr(name, w):
        txt = (el.get(name) or "").replace(",", " ")
        return np.array(txt.split(), np.float32).reshape(-1, w)

    pos = arr("positions", 3)
    sh_cols = []
    for d, cnt in enumerate(SH_COUNTS):
        cols = [el.get(_sh_field(d, c)) for c in range(cnt)]
        if not all(cols):
            break
        sh_cols += [arr(_sh_field(d, c), 3) for c in range(cnt)]
    sh = np.stack(sh_cols, 1)
    return SplatCloud(pos, arr("orientations", 4), arr("scales", 3),
                      arr("opacities", 1).ravel(), sh,
                      color_space=el.get("colorSpace", "SRGB_REC709_DISPLAY"), frame=frame,
                      meta={"source": str(path)})


# ====================================================================== USD
def write_usd(cloud: SplatCloud, path: str | Path, prim_path: str = "/World/Splats") -> Path:
    """OpenUSD 26.03+ UsdVol.ParticleField3DGaussianSplat (needs usd-core>=26.3)."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdVol, Vt

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, prim_path.rsplit("/", 1)[0] or "/World")
    stage.SetDefaultPrim(world.GetPrim())
    splat = UsdVol.ParticleField3DGaussianSplat.Define(stage, prim_path)
    prim = splat.GetPrim()
    rot = FRAME_ROTATIONS[cloud.frame]
    if rot:  # same parent-rotation idea as X3D: data untouched
        UsdGeom.Xformable(prim).AddRotateXOp().Set(math.degrees(rot[3]))
    q = cloud.rotations
    prim.GetAttribute("positions").Set(Vt.Vec3fArray.FromNumpy(cloud.positions))
    prim.GetAttribute("orientations").Set(
        Vt.QuatfArray([Gf.Quatf(float(w), float(x), float(y), float(z)) for x, y, z, w in q]))
    prim.GetAttribute("scales").Set(Vt.Vec3fArray.FromNumpy(cloud.scales))
    prim.GetAttribute("opacities").Set(Vt.FloatArray.FromNumpy(cloud.opacities))
    prim.GetAttribute("radiance:sphericalHarmonicsDegree").Set(cloud.degree)
    shc = prim.GetAttribute("radiance:sphericalHarmonicsCoefficients")
    shc.Set(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(cloud.sh.reshape(-1, 3))))
    # As in Omniverse asset-requirement VG.035's valid example (degree 0 there:
    # elementSize 1); we write elementSize = (degree+1)^2 per particle.
    shc.SetMetadata("interpolation", "vertex")
    shc.SetMetadata("elementSize", k_for_degree(cloud.degree))
    lo, hi = cloud.extent()
    prim.GetAttribute("extent").Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))]))
    prim.SetCustomDataByKey("x3dnv:colorSpace", cloud.color_space)
    stage.GetRootLayer().customLayerData = {"generator": "x3d.nVidia x3dnv.splats"}
    stage.GetRootLayer().Save()
    return Path(path)


def read_usd(path: str | Path) -> SplatCloud:
    from pxr import Usd, UsdVol

    stage = Usd.Stage.Open(str(path))
    prim = next(p for p in stage.Traverse() if p.IsA(UsdVol.ParticleField3DGaussianSplat))
    get = lambda n: prim.GetAttribute(n).Get()
    q = np.array([[o.GetImaginary()[0], o.GetImaginary()[1], o.GetImaginary()[2], o.GetReal()]
                  for o in get("orientations")], np.float32)
    d = int(get("radiance:sphericalHarmonicsDegree"))
    sh = np.array(get("radiance:sphericalHarmonicsCoefficients"), np.float32).reshape(-1, k_for_degree(d), 3)
    frame = "colmap" if prim.GetAttribute("xformOp:rotateX").IsValid() else "none"
    return SplatCloud(np.array(get("positions"), np.float32), q,
                      np.array(get("scales"), np.float32), np.array(get("opacities"), np.float32),
                      sh, color_space=prim.GetCustomDataByKey("x3dnv:colorSpace") or "SRGB_REC709_DISPLAY",
                      frame=frame, meta={"source": str(path)})


# ====================================================================== glTF
_KHR = "KHR_gaussian_splatting"


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def write_glb(cloud: SplatCloud, path: str | Path) -> Path:
    """glTF 2.0 + KHR_gaussian_splatting (ratified 3 Sep 2026), float32 accessors.

    COLOR_0 is the point-cloud fallback: 0.5 + C0*SH0, clamped, sRGB-decoded to
    linear when the cloud is sRGB, alpha = opacity (as the extension says).
    """
    n = cloud.n
    blobs, views, accessors, attrs = [], [], [], {}
    offset = 0

    def add(name, arr, typ, minmax=False):
        nonlocal offset
        a = np.ascontiguousarray(arr, "<f4")
        b = a.tobytes()
        pad = (-len(b)) % 4
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(b),
                      "target": 34962})  # ARRAY_BUFFER
        acc = {"bufferView": len(views) - 1, "componentType": 5126, "count": n, "type": typ}
        if minmax:
            acc["min"] = [float(x) for x in a.reshape(n, -1).min(0)]
            acc["max"] = [float(x) for x in a.reshape(n, -1).max(0)]
        accessors.append(acc)
        attrs[name] = len(accessors) - 1
        blobs.append(b + b"\0" * pad)
        offset += len(b) + pad

    base = cloud.base_color()
    lin = srgb_to_linear(base) if cloud.color_space == "SRGB_REC709_DISPLAY" else base
    add("POSITION", cloud.positions, "VEC3", minmax=True)
    add("COLOR_0", np.concatenate([lin, cloud.opacities[:, None]], 1), "VEC4")
    add(f"{_KHR}:ROTATION", cloud.rotations, "VEC4")
    add(f"{_KHR}:SCALE", cloud.scales, "VEC3")
    add(f"{_KHR}:OPACITY", cloud.opacities, "SCALAR")
    i = 0
    for d, cnt in enumerate(SH_COUNTS[: cloud.degree + 1]):
        for c in range(cnt):
            add(f"{_KHR}:SH_DEGREE_{d}_COEF_{c}", cloud.sh[:, i], "VEC3")
            i += 1
    node = {"mesh": 0, "name": "Splats"}
    rot = FRAME_ROTATIONS[cloud.frame]
    if rot:
        s = math.sin(rot[3] / 2)
        node["rotation"] = [rot[0] * s, rot[1] * s, rot[2] * s, math.cos(rot[3] / 2)]
    gltf = {
        "asset": {"version": "2.0", "generator": "x3d.nVidia x3dnv.splats"},
        "extensionsUsed": [_KHR],
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
        "meshes": [{"primitives": [{"attributes": attrs, "mode": 0, "extensions": {_KHR: {
            "kernel": "ellipse", "colorSpace": cloud.color_space.lower(),
            "projection": "perspective", "sortingMethod": "cameraDistance"}}}]}],
        "buffers": [{"byteLength": offset}], "bufferViews": views, "accessors": accessors,
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binb = b"".join(blobs)
    total = 12 + 8 + len(js) + 8 + len(binb)
    out = struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(binb), b"BIN\0") + binb
    p = Path(path)
    p.write_bytes(out)
    return p


def read_glb(path: str | Path) -> SplatCloud:
    raw = Path(path).read_bytes()
    magic, _ver, _len = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF":
        raise ValueError("not a glb")
    jl, _ = struct.unpack_from("<I4s", raw, 12)
    g = json.loads(raw[20:20 + jl])
    bl, _ = struct.unpack_from("<I4s", raw, 20 + jl)
    binb = raw[28 + jl: 28 + jl + bl]
    prim = g["meshes"][0]["primitives"][0]
    width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}

    def get(sem):
        acc = g["accessors"][prim["attributes"][sem]]
        bv = g["bufferViews"][acc["bufferView"]]
        if acc["componentType"] != 5126:
            raise NotImplementedError("only float32 splat accessors are read")
        a = np.frombuffer(binb, "<f4", acc["count"] * width[acc["type"]],
                          bv.get("byteOffset", 0) + acc.get("byteOffset", 0))
        return a.reshape(acc["count"], width[acc["type"]])

    sh = []
    for d, cnt in enumerate(SH_COUNTS):
        if f"{_KHR}:SH_DEGREE_{d}_COEF_0" not in prim["attributes"]:
            break
        sh += [get(f"{_KHR}:SH_DEGREE_{d}_COEF_{c}") for c in range(cnt)]
    ext = prim["extensions"][_KHR]
    frame = "colmap" if "rotation" in g["nodes"][0] else "none"
    return SplatCloud(get("POSITION"), get(f"{_KHR}:ROTATION"), get(f"{_KHR}:SCALE"),
                      get(f"{_KHR}:OPACITY").ravel(), np.stack(sh, 1),
                      color_space=ext["colorSpace"].upper(), frame=frame, meta={"source": str(path)})


READERS = {".ply": read_ply, ".x3d": read_x3d, ".usda": read_usd, ".usd": read_usd,
           ".usdc": read_usd, ".glb": read_glb}
WRITERS = {".ply": write_ply, ".x3d": write_x3d, ".usda": write_usd, ".usd": write_usd,
           ".usdc": write_usd, ".glb": write_glb}


def convert(src: str | Path, dst: str | Path, **kw) -> Path:
    src, dst = Path(src), Path(dst)
    cloud = READERS[src.suffix.lower()](src)
    return WRITERS[dst.suffix.lower()](cloud, dst, **kw)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(prog="x3dnv-splats", description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst", nargs="+")
    ap.add_argument("--max-splats", type=int, default=0, help="keep the N most opaque")
    ap.add_argument("--degree", type=int, default=-1, help="truncate SH degree")
    a = ap.parse_args(argv)
    cloud = READERS[Path(a.src).suffix.lower()](a.src)
    if a.max_splats and cloud.n > a.max_splats:
        cloud = cloud.subset(np.sort(np.argsort(-cloud.opacities)[: a.max_splats]))
    if a.degree >= 0:
        cloud = cloud.truncate_degree(min(a.degree, cloud.degree))
    print(f"[splats] {a.src}: n={cloud.n} degree={cloud.degree} frame={cloud.frame} problems={cloud.check()}")
    for d in a.dst:
        p = WRITERS[Path(d).suffix.lower()](cloud, d)
        print(f"[splats] wrote {p} ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
