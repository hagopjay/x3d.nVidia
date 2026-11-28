"""SimReady on real assets: real X3D physics scenes, judged by NVIDIA's own validator against NVIDIA's own
Robotics-Prop profile, as authored and after the opt-in upgrade to the X3D SimReady profile.

    python -I q12/real_assets.py X3D_MCP_DIR TIERS_DIR SCENES_DIR THUMBS_DIR FACTS.json OUT_DIR RECEIPT.json

For every *.x3d under SCENES_DIR:

    as authored   write it to USD with src/x3dnv/x3d2usdphysics.py (nothing repaired) and run every executable rule
                  that Robotics-Prop 5.0.0 requires (the profile resolved by simready.foundation.contracts)
    opted in      the same file with one <meta name="simready:features"> added and nothing else: x3d_mcp's profile
                  checks now speak, and what they report is compared, rule by rule, with what SimReady said of the
                  USD above. This is the agreement table: does the X3D check predict NVIDIA's verdict on a real file?
    upgraded      src/x3dnv/simready_upgrade.py writes a copy into OUT_DIR with the facts of FACTS.json, a thumbnail
                  from THUMBS_DIR and each Box as a mesh; the copy is checked against the X3D 4.0 XSD, by x3d_mcp
                  (with the folder), written to USD and judged again

Pass is NVIDIA's own rule in its package sample (skills/.../sr_pkg_sample/_validate_package.py): no issue of
severity ERROR or FAILURE on a required requirement. Warnings are counted apart. Requirements with no executable
rule are listed and are not counted as passed.
"""
import glob
import hashlib
import importlib.metadata as md
import json
import logging
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

A = sys.argv[1:]
MCP, TIERS, SCENES, THUMBS, FACTS, OUT = (Path(a).resolve() for a in A[:6])
DEST = Path(A[6])
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(MCP / "src"), str(HERE.parent / "src")]
logging.disable(logging.CRITICAL)

import usd_validation_nvidia as v  # noqa: E402
from lxml import etree  # noqa: E402
from simready.foundation import contracts as C, validation as V  # noqa: E402
from validation.semantic import semantic_diagnostics_with_files  # noqa: E402
from validation.validate import validate_xml  # noqa: E402
from x3dnv import simready_upgrade as su, x3d2usdphysics as xw  # noqa: E402

PROFILE = ("Robotics-Prop", "5.0.0")
short = lambda c: re.sub(r"^com\.nvidia\.(usd|simready)\.", "", c)  # noqa: E731
FAIL = {v.IssueSeverity.ERROR, v.IssueSeverity.FAILURE}
# x3d_mcp profile diagnostic -> the SimReady requirement it answers (x3d_mcp docs/USD-VALIDATION-PARITY.md)
PAIRS = {"SR.004": "simready-metadata-missing", "SR.002": "simready-thumbnail-missing", "SL.001": "simready-shape-unlabelled",
         "SL.MAT.001": "simready-material-unlabelled", "VG.MESH.001": "simready-geometry-not-mesh", "RB.001": "simready-no-rigid-body"}


def plan():
    g = lambda k: sorted(glob.glob(str(TIERS / f"*/simready/foundation/*/{k}")))  # noqa: E731
    feat, caps, profs = C.load_feature_definitions(g("features")), C.load_capability_definitions(g("capabilities")), C.load_profile_definitions(g("profiles"))
    p = V.build_validation_plan(C.resolve_profile(profs[PROFILE], feat, caps), feat, caps)
    return [short(c) for c in p.required_requirements], [short(c) for c in p.optional_requirements]


def engine():
    eng = v.ValidationEngine(init_rules=True)
    default = {r.__name__ for r in eng.rules}
    import simready.foundation.tier_core.rules_and_reqs.dataset_taxonomies.validation as tx
    import simready.foundation.tier_core.rules_and_reqs.semantic_labels.validation as sl
    by_hand = []
    for mod in (sl, tx):
        for name in mod.__all__:
            if name not in default:
                eng.enable_rule(getattr(mod, name))
                by_hand.append(name)
    reg, served, by_rule = v.RequirementsRegistry(), defaultdict(set), {}
    for r in eng.rules:
        cs = {short(q.code) for q in reg.get_requirements(r)}
        by_rule[r.__name__] = cs
        for c in cs:
            served[c].add(r.__name__)
    return eng, served, by_rule, sorted(by_hand)


REQ, OPT = plan()
ENG, SERVED, BY_RULE, BY_HAND = engine()


def judge(usd: Path):
    """{required code: 'fail' | 'warn'} with one message each, from every rule the profile requires."""
    out, msg = {}, {}
    for i in ENG.validate(str(usd)).issues():
        if i.severity not in FAIL and i.severity != v.IssueSeverity.WARNING:
            continue
        q = getattr(i, "requirement", None)
        codes = {short(q.code)} if getattr(q, "code", None) else set(BY_RULE.get(getattr(getattr(i, "rule", None), "__name__", ""), set()))
        for c in codes & set(REQ):
            lvl = "fail" if i.severity in FAIL else "warn"
            if out.get(c) != "fail":
                out[c] = lvl
                msg[c] = re.sub(r"/\S*/", "", str(i.message))[:160]          # no machine paths in a receipt
    return out, msg


def x3d_codes(text: str, folder: Path):
    return Counter(d.check for d in semantic_diagnostics_with_files(text, folder) if d.check.startswith("simready-"))


def opt_in_only(text: str) -> str:
    return text.replace("</head>", '<meta name="simready:features" content="rigid_bodies semantic_labels material_labels"/></head>', 1)


def main():
    facts = json.loads(FACTS.read_text())
    corpus, kinds = facts["corpus"], facts["kinds"]
    mats = {k: val[0] for k, val in facts["materials"].items()}
    rows = []
    for p in sorted(SCENES.rglob("*.x3d")):
        rel = p.relative_to(SCENES).with_suffix("").as_posix()
        text = p.read_text()
        work = OUT / ".usd" / rel.replace("/", "__")
        work.mkdir(parents=True, exist_ok=True)
        row = {"scene": rel + ".x3d", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        (work / "authored").mkdir(exist_ok=True)
        (work / "upgraded").mkdir(exist_ok=True)
        rep = xw.convert(p, work / "authored" / (p.stem.replace("-", "_") + ".usda"))
        row["bodies_moving"], row["bodies_static"], row["shapes"] = rep.get("dynamic"), rep.get("static"), rep.get("shapes")
        a, amsg = judge(work / "authored" / (p.stem.replace("-", "_") + ".usda"))
        row["authored"] = {"fail": sorted(c for c in a if a[c] == "fail"), "warn": sorted(c for c in a if a[c] == "warn")}
        # agreement: the untouched file, opted in by one meta, as x3d_mcp sees it
        xc = x3d_codes(opt_in_only(text), p.parent)
        row["agreement"] = {c: {"simready": a.get(c, "pass"), "x3d_mcp_reports": bool(xc.get(d))} for c, d in PAIRS.items()}
        # upgrade
        kind = facts["scenes"].get(rel)
        q, cat = kinds.get(kind, (None, None))
        f = {"creator": corpus["creator"]["value"], "license": corpus["license"]["value"], "category": cat, "qcode": q,
             "features": corpus["features"], "materials": mats}
        dst = OUT / (rel + ".x3d")
        thumb = THUMBS / (rel + ".png")
        up = su.upgrade(p, dst, f, thumb if thumb.is_file() else None)
        utext = dst.read_text()
        xsd = validate_xml(utext)
        row["upgrade"] = {k: up[k] for k in ("metas_added", "facts_not_supplied", "materials_labelled", "materials_unlabelled", "boxes_to_meshes", "primitives_left")}
        row["upgrade"]["kind"] = kind
        row["upgrade"]["xsd_valid"] = bool(xsd.get("valid"))
        row["upgrade"]["xsd_errors"] = [str(e)[:160] for e in (xsd.get("errors") or [])][:3]
        row["upgrade"]["x3d_mcp_simready"] = dict(x3d_codes(utext, dst.parent))
        rep2 = xw.convert(dst, work / "upgraded" / (dst.stem.replace("-", "_") + ".usda"))
        row["upgrade"]["labels_written"] = rep2.get("labels")
        b, bmsg = judge(work / "upgraded" / (dst.stem.replace("-", "_") + ".usda"))
        row["upgraded"] = {"fail": sorted(c for c in b if b[c] == "fail"), "warn": sorted(c for c in b if b[c] == "warn"),
                           "messages": {c: bmsg[c] for c in b}}
        row["authored"]["messages"] = {c: amsg[c] for c in a if a[c] == "fail"}
        row["passes_required_rules"] = not row["upgraded"]["fail"]
        rows.append(row)
        print(f"{rel:44} moving={row['bodies_moving']:>3} authored fail {len(row['authored']['fail'])} -> upgraded fail {row['upgraded']['fail']} warn {row['upgraded']['warn']}")
    cells = [(c, r["agreement"][c]) for r in rows for c in PAIRS]
    agree = sum(1 for _, x in cells if (x["simready"] != "pass") == x["x3d_mcp_reports"])
    props = [r for r in rows if r["bodies_moving"]]
    git = lambda d: subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()  # noqa: E731
    receipt = {
        "what": "Real X3D physics scenes against NVIDIA's Robotics-Prop profile, as authored and after the opt-in upgrade",
        "profile": {"name": PROFILE[0], "version": PROFILE[1], "required": len(REQ), "optional": len(OPT),
                    "required_with_an_executable_rule": sum(1 for c in REQ if SERVED.get(c)),
                    "required_without_one": [c for c in REQ if not SERVED.get(c)]},
        "pass_rule": "no ERROR or FAILURE on a required requirement (NVIDIA's package sample, sr_pkg_sample/_validate_package.py); warnings apart",
        "instruments": {"usd-validation-nvidia": md.version("usd-validation-nvidia"), "usd-core": md.version("usd-core"),
                        "simready-foundation tiers": sorted(d.name for d in TIERS.iterdir() if d.is_dir()),
                        "python": sys.version.split()[0], "x3d_mcp": git(MCP), "x3d.nvidia": git(HERE.parent),
                        "enabled_by_hand": BY_HAND},
        "counts": {"scenes": len(rows), "with_a_moving_body": len(props),
                   "authored_pass": sum(1 for r in rows if not r["authored"]["fail"]),
                   "upgraded_pass": sum(1 for r in rows if r["passes_required_rules"]),
                   "upgraded_pass_with_a_moving_body": sum(1 for r in props if r["passes_required_rules"]),
                   "upgraded_pass_without_any_warning": sum(1 for r in rows if r["passes_required_rules"] and not r["upgraded"]["warn"]),
                   "upgraded_xsd_valid": sum(1 for r in rows if r["upgrade"]["xsd_valid"]),
                   "authored_failures_by_rule": dict(Counter(c for r in rows for c in r["authored"]["fail"])),
                   "upgraded_failures_by_rule": dict(Counter(c for r in rows for c in r["upgraded"]["fail"])),
                   "upgraded_warnings_by_rule": dict(Counter(c for r in rows for c in r["upgraded"]["warn"])),
                   "boxes_to_meshes": sum(r["upgrade"]["boxes_to_meshes"] for r in rows)},
        "agreement": {"cells": len(cells), "agree": agree,
                      "by_rule": {c: {"agree": sum(1 for cc, x in cells if cc == c and (x["simready"] != "pass") == x["x3d_mcp_reports"]),
                                      "of": len(rows)} for c in PAIRS},
                      "disagreements": [{"scene": r["scene"], "rule": c, **r["agreement"][c]} for r in rows for c in PAIRS
                                        if (r["agreement"][c]["simready"] != "pass") != r["agreement"][c]["x3d_mcp_reports"]]},
        "scenes": rows,
    }
    DEST.write_text(json.dumps(receipt, indent=1))
    print(json.dumps(receipt["counts"], indent=1))
    print("agreement", agree, "of", len(cells), receipt["agreement"]["by_rule"])


main()
