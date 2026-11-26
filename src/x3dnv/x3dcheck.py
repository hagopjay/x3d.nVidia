"""A fast, dependency-free first look at model-written X3D.

This is a triage metric (for probes and DSPy/GEPA loops), not a validator.
Real validation is the x3d_mcp fork's XSD + semantic checks (owner's lane).
Score, 0..5: parses (1), root X3D with version (1), has Scene with children (1),
every requested node present (1), no obvious field-arity errors (1).
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

ARITY = {  # attribute -> number of floats expected
    "position": 3, "size": 3, "translation": 3, "scale": 3, "diffuseColor": 3,
    "emissiveColor": 3, "baseColor": 3, "direction": 3, "orientation": 4, "rotation": 4,
}
WANT = ("Viewpoint", "Box", "DirectionalLight")


def extract_x3d(text: str) -> str:
    m = re.search(r"```(?:xml|x3d)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    i = text.find("<?xml")
    j = text.find("<X3D")
    start = i if 0 <= i < (j if j >= 0 else 10**9) else j
    end = text.rfind("</X3D>")
    if start >= 0 and end > start:
        return text[start:end + 6]
    return text.strip()


def check_x3d(xml: str, want=WANT) -> dict:
    out = {"parses": False, "root": None, "version": None, "profile": None,
           "scene_children": None, "nodes": {}, "missing": list(want), "arity_errors": [], "score": 0}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        out["error"] = str(e)
        return out
    out["parses"] = True
    out["root"] = root.tag
    out["version"] = root.get("version")
    out["profile"] = root.get("profile")
    scene = root.find("Scene")
    out["scene_children"] = len(scene) if scene is not None else None
    for el in root.iter():
        out["nodes"][el.tag] = out["nodes"].get(el.tag, 0) + 1
        for k, n in ARITY.items():
            v = el.get(k)
            if v is None or el.tag in ("Text", "FontStyle"):
                continue
            try:
                nums = [float(x) for x in v.replace(",", " ").split()]
            except ValueError:
                out["arity_errors"].append(f"{el.tag}@{k}={v!r}")
                continue
            if len(nums) != n:
                out["arity_errors"].append(f"{el.tag}@{k}={v!r}")
    out["missing"] = [w for w in want if w not in out["nodes"]]
    out["score"] = (int(out["parses"]) + int(out["root"] == "X3D" and bool(out["version"]))
                    + int(bool(out["scene_children"])) + int(not out["missing"])
                    + int(not out["arity_errors"]))
    return out
