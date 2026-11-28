"""Opt an X3D scene into the X3D SimReady profile (draft 2) by writing an upgraded COPY. The source is never changed.

    upgrade(src, dst, facts, thumbnail=None) -> report

What it writes, and nothing else:

    <head>      creator, license, simready:category, simready:qcode, simready:features, simready:source (the source
                file's name and sha256), and Image when a thumbnail PNG is given (copied beside the copy). A meta
                the source already has is kept. A fact that is not supplied is not written: the upgrader invents none.
    labels      a MetadataSet "semantics:labels" with one MetadataString "material" on every Appearance whose DEF name
                the facts give a material for (SimReady SL.MAT.001, and SL.001 through the bound material).
    Box         left alone by default. SimReady VG.MESH.001 wants meshes, and the writer can emit each Box as its exact
                twelve-triangle mesh (x3d2usdphysics.convert(..., box_as_mesh=True)) without touching the X3D.
                mesh_boxes=True rewrites each Box as an IndexedFaceSet in the copy instead; that is exact geometry
                but it changes how the scene plays in X_ITE 16.8.0, whose physics let ten dominoes rewritten this way
                fall out of view within 2.5 seconds. Sphere, Cylinder and Cone are never touched: a faceted ball does
                not roll like a ball, and SimReady then warns about them, truthfully.

Facts are a dict: {"creator", "license", "category", "qcode", "features": [...], "materials": {DEF name: label}}.
Where each fact came from belongs in the caller's sidecar, not here.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from lxml import etree

_TRIS = "0 2 1 -1 0 3 2 -1 4 5 6 -1 4 6 7 -1 0 1 5 -1 0 5 4 -1 3 6 2 -1 3 7 6 -1 0 4 7 -1 0 7 3 -1 1 2 6 -1 1 6 5 -1"


def _box_points(size):
    x, y, z = (abs(float(v)) / 2 for v in size)
    c = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    return " ".join(f"{a:.9g} {b:.9g} {d:.9g}" for a, b, d in c)


def upgrade(src, dst, facts, thumbnail=None, mesh_boxes=False):
    src, dst = Path(src), Path(dst)
    raw = src.read_bytes()
    tree = etree.fromstring(raw, etree.XMLParser(remove_blank_text=False)).getroottree()
    root = tree.getroot()
    head = root.find("head")
    if head is None:
        head = etree.Element("head")
        root.insert(0, head)
    have = {(m.get("name") or "").strip().lower() for m in head.iter("meta")}
    rep = {"source": src.name, "source_sha256": hashlib.sha256(raw).hexdigest(), "metas_added": [], "metas_kept": [],
           "facts_not_supplied": [], "materials_labelled": {}, "materials_unlabelled": [], "boxes_to_meshes": 0,
           "primitives_left": {}}

    def meta(name, value):
        if name.lower() in have:
            rep["metas_kept"].append(name)
            return
        if value in (None, "", []):
            rep["facts_not_supplied"].append(name)
            return
        m = etree.SubElement(head, "meta", name=name, content=str(value))
        m.tail = "\n "
        rep["metas_added"].append(name)

    meta("creator", facts.get("creator"))
    meta("license", facts.get("license"))
    meta("simready:category", facts.get("category"))
    meta("simready:qcode", facts.get("qcode"))
    meta("simready:features", " ".join(facts.get("features") or []))
    meta("simready:source", f"{src.name} sha256 {rep['source_sha256']}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if thumbnail is not None:
        png = dst.with_suffix(".png")
        shutil.copyfile(thumbnail, png)
        meta("Image", png.name)

    mats = facts.get("materials") or {}
    for app in root.iter("Appearance"):
        if app.get("USE"):
            continue
        name = app.get("DEF") or ""
        if any(c.tag == "MetadataSet" and c.get("name") == "semantics:labels" for c in app):
            continue
        label = mats.get(name)
        if not label:
            rep["materials_unlabelled"].append(name or "(no DEF)")
            continue
        ms = etree.Element("MetadataSet", containerField="metadata", name="semantics:labels")
        etree.SubElement(ms, "MetadataString", containerField="value", name="material", value=f'"{label}"')
        app.insert(0, ms)
        rep["materials_labelled"][name] = label

    for box in (list(root.iter("Box")) if mesh_boxes else []):
        mesh = etree.Element("IndexedFaceSet")
        for k in ("DEF", "USE", "containerField", "class", "id"):
            if box.get(k) is not None:
                mesh.set(k, box.get(k))
        if box.get("USE") is None:
            mesh.set("solid", box.get("solid", "true"))
            mesh.set("coordIndex", _TRIS)
            for c in box:
                mesh.append(c)
            etree.SubElement(mesh, "Coordinate", point=_box_points((box.get("size") or "2 2 2").split()))
            rep["boxes_to_meshes"] += 1
        mesh.tail = box.tail
        box.getparent().replace(box, mesh)
    for t in ("Sphere", "Cylinder", "Cone"):
        n = sum(1 for e in root.iter(t) if not e.get("USE"))
        if n:
            rep["primitives_left"][t] = n
    tree.write(str(dst), xml_declaration=True, encoding="UTF-8")
    return rep
