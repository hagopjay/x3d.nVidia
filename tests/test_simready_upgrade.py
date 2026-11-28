"""The opt-in upgrader writes a copy, invents no fact, and leaves geometry alone unless asked."""
import hashlib

import pytest
from lxml import etree

from x3dnv import simready_upgrade as su

SCENE = """<?xml version="1.0" encoding="UTF-8"?>
<X3D profile="Immersive" version="4.0"><head><meta name="title" content="t"/></head><Scene>
<Shape><Appearance DEF="Mat_wood"><Material/></Appearance><Box size="2 4 6"/></Shape>
<Shape><Appearance DEF="Mat_red"><Material/></Appearance><Sphere/></Shape>
</Scene></X3D>
"""
FACTS = {"creator": "A", "license": "Apache-2.0", "category": "toy", "qcode": None, "features": ["rigid_bodies"],
         "materials": {"Mat_wood": "wood"}}


def run(tmp_path, **kw):
    src = tmp_path / "in" / "s.x3d"
    src.parent.mkdir()
    src.write_text(SCENE)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    rep = su.upgrade(src, tmp_path / "out" / "s.x3d", FACTS, **kw)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before          # the source is never changed
    return rep, etree.parse(str(tmp_path / "out" / "s.x3d")).getroot()


def test_a_fact_that_is_not_supplied_is_not_written(tmp_path):
    rep, root = run(tmp_path)
    names = [m.get("name") for m in root.iter("meta")]
    assert "simready:qcode" not in names and "simready:qcode" in rep["facts_not_supplied"]
    assert {"creator", "license", "simready:category", "simready:features", "simready:source"} <= set(names)
    assert "Image" not in names                                            # no thumbnail given, none claimed


def test_only_named_materials_are_labelled(tmp_path):
    rep, root = run(tmp_path)
    assert rep["materials_labelled"] == {"Mat_wood": "wood"} and rep["materials_unlabelled"] == ["Mat_red"]
    ms = root.find(".//Appearance[@DEF='Mat_wood']/MetadataSet")
    assert ms.get("name") == "semantics:labels" and ms[0].get("value") == '"wood"'


def test_geometry_is_left_alone_by_default(tmp_path):
    rep, root = run(tmp_path)
    assert rep["boxes_to_meshes"] == 0 and len(list(root.iter("Box"))) == 1


def test_mesh_boxes_writes_an_outward_closed_box(tmp_path):
    rep, root = run(tmp_path, mesh_boxes=True)
    ifs = root.find(".//IndexedFaceSet")
    pts = [float(x) for x in ifs.find("Coordinate").get("point").split()]
    p = [pts[i:i + 3] for i in range(0, 24, 3)]
    idx = [int(x) for x in ifs.get("coordIndex").split()]
    tris = [idx[i:i + 3] for i in range(0, len(idx), 4)]
    vol = 0.0
    for a, b, c in tris:                                                   # signed volume: positive when wound outwards
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p[a], p[b], p[c]
        vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6
    assert rep["boxes_to_meshes"] == 1 and len(tris) == 12 and vol == pytest.approx(2 * 4 * 6)
    assert len(list(root.iter("Sphere"))) == 1                             # a ball stays a ball
