"""Q12 run 2, stage 3: join the X3D verdicts with three executed USD rulebooks, per rule, scene and orientation.

    python -I join.py X3D_MCP_DIR OUT.json --parity SCENES_DIR EXPORT.json RB.json SR.json
                                          [--real VIEWS.json CORPUS.json EXPORT.json RB.json SR.json]

Builds on x3d_mcp #33 (tests/usd_q12/join.py): the same classes, the same reading of x3d_mcp's MAP and fixtures.

    agree-fail   the X3D check fires and the USD rule fails
    agree-pass   both quiet
    x3d-only     the X3D check fires, the USD rule passes the export (Blender repaired it, or X3D is stricter)
    export-made  the scene has no X3D finding at all, the USD rule fails: the Blender leg made it
    x3d-missed?  the X3D check is quiet, the USD rule fails, the scene has other X3D findings: for a person to read
    not-run      the rule could not run on this file; export-failed: Blender could not export the scene

What run 2 adds:
  * SimReady requirements executed (run_simready.py), so the 39 stateable rules #33 could not run are judged;
  * real files (select_real.py's corpus), not only the parity fixtures;
  * both orientations: z (Blender's) and y (converted); `orientation` lists every rule whose verdict differs;
  * FM 373: agreement is reported on FIRED pairs only (either side fires), and every rulebook's silent rules are named;
  * every USD failure with no X3D check behind it, with MAP's status for that rule (policy, design, engine, ...),
    so "fails on every export" reads as "a SimReady profile convention X3D does not define", not as a defect.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

A = sys.argv[1:]
MCP, DEST = Path(A[0]).resolve(), Path(A[1])
sys.path[:0] = [str(MCP / "tests"), str(MCP / "src")]
import gltf_parity as gp  # noqa: E402
import usd_parity as u  # noqa: E402


def grab(flag, n):
    return A[A.index(flag) + 1:A.index(flag) + 1 + n] if flag in A else None


def load(p):
    return json.loads(Path(p).read_text())


def view_text(text):
    ok, xsd, ds = gp.findings(text, None)
    return {"parse_ok": ok, "xsd": xsd, "codes": sorted({c for lv, c in ds if lv in ("error", "warning")}),
            "info": sorted({c for lv, c in ds if lv == "info"})}


def fires(v, check, by=""):
    if check is None:
        return v["xsd"] > 0 or not v["parse_ok"]
    return check in v["codes"] or (by.endswith("-info") and check in v["info"])


def usd_verdicts(rb, sr, var):
    """{scene: {rule id: verdict}} for one orientation, the three rulebooks merged ("sr:" + code)."""
    out = defaultdict(dict)
    for n, row in rb["variants"].get(var, {}).items():
        out[n].update(row["verdicts"])
    for n, row in sr["variants"].get(var, {}).items():
        if "crash" in row:
            out[n]["sr:*"] = "not-run: " + row["crash"][:60]
            continue
        out[n].update({"sr:" + c: v for c, v in row["verdicts"].items()})
    return out


def book(rid):
    return {"usd": "usd-core", "oav": "omniverse", "sr": "simready"}[rid.split(":")[0]]


MAPPED = {rid: (st, fx) for rid, (st, fx, _) in u.MAP.items() if st in u.STATEABLE}
STATUS = {rid: st for rid, (st, _fx, _n) in u.MAP.items()}


def judge(views, exp, rb, sr, corpus_name, own_pairs):
    res = {"orientations": {}}
    per_var = {}
    for var in ("z", "y"):
        usd = usd_verdicts(rb, sr, var)
        executed = {r for s in usd.values() for r, v in s.items() if not v.startswith("not-run")}
        mapped = {rid: m for rid, m in MAPPED.items() if rid in executed}
        tally, rows = defaultdict(Counter), []
        for rid, (st, fx) in sorted(mapped.items()):
            check, by = (u.F[fx][1], u.F[fx][0]) if fx else (None, "")
            for n, v in views.items():
                if check is None and not (own_pairs and n.split("__")[0] == "p_" + str(fx)):
                    continue              # schema rules: only on their own fixture pair (other scenes break other rules)
                if n not in usd or "error" in exp["scenes"].get(n, {}):
                    cls = "export-failed"
                else:
                    r = usd[n].get(rid, "not-run: absent")
                    if r.startswith("not-run"):
                        cls = "not-run"
                    else:
                        uf, xf = r == "fail", fires(v, check, by)
                        flagged = bool(v["codes"]) or v["xsd"] > 0 or not v["parse_ok"]
                        cls = (("agree-fail" if uf else "agree-pass") if uf == xf else
                               "x3d-only" if xf else ("x3d-missed?" if flagged else "export-made"))
                tally[rid][cls] += 1
                if cls not in ("agree-pass",):
                    rows.append({"rule": rid, "scene": n, "class": cls, "x3d_codes": v["codes"],
                                 "usd": usd.get(n, {}).get(rid)})
        totals = Counter()
        for t in tally.values():
            totals.update(t)
        fired = totals["agree-fail"] + totals["x3d-only"] + totals["export-made"] + totals["x3d-missed?"]
        unmapped = defaultdict(list)
        fired_rules = Counter()
        for n, s in usd.items():
            for rid, r in s.items():
                if r == "fail":
                    fired_rules[rid] += 1
                    if rid not in mapped:
                        unmapped[rid].append(n)
        silent = {b: sorted(r for r in executed if book(r) == b and not fired_rules[r]) for b in ("usd-core", "omniverse", "simready")}
        per_var[var] = usd
        res["orientations"][var] = {
            "scenes": len(views), "exported": sum(1 for n in views if n in usd),
            "executed_rules": {b: sum(1 for r in executed if book(r) == b) for b in ("usd-core", "omniverse", "simready")},
            "mapped_executed": {b: sum(1 for r in mapped if book(r) == b) for b in ("usd-core", "omniverse", "simready")},
            "pair_totals": dict(totals),
            "fired_pairs": {"total": fired, "both": totals["agree-fail"], "x3d_only": totals["x3d-only"],
                            "usd_only": totals["export-made"] + totals["x3d-missed?"]},
            "silent_rules": silent,
            "unmapped_failures": {rid: {"scenes": len(ns), "map_status": STATUS.get(rid, "not in MAP"), "examples": ns[:3]}
                                  for rid, ns in sorted(unmapped.items(), key=lambda kv: -len(kv[1]))},
            "per_rule": {rid: dict(t) for rid, t in tally.items()},
            "disagreements": rows,
        }
    diff = defaultdict(list)
    for n in per_var["z"]:
        for rid in set(per_var["z"][n]) | set(per_var["y"].get(n, {})):
            a, b = per_var["z"][n].get(rid, ""), per_var["y"].get(n, {}).get(rid, "")
            if a != b:
                diff[rid].append({"scene": n, "z": a, "y": b})
    res["orientation_diff"] = {rid: {"scenes": len(v), "z": Counter(x["z"] for x in v), "y": Counter(x["y"] for x in v),
                                     "map_status": STATUS.get(rid, "not in MAP")} for rid, v in sorted(diff.items())}
    print(f"[{corpus_name}]", {var: res["orientations"][var]["fired_pairs"] for var in ("z", "y")})
    return res


out = {"pins": {}, "corpora": {}}
par = grab("--parity", 4)
if par:
    scenes, exp, rb, sr = Path(par[0]), load(par[1]), load(par[2]), load(par[3])
    views = {p.stem: view_text(p.read_text()) for p in sorted(scenes.glob("*.x3d"))}
    out["corpora"]["parity"] = judge(views, exp, rb, sr, "parity", own_pairs=True)
    out["pins"] = {**u.RULES["pins"], "blender": exp["blender"], "x3d_blender_io": exp.get("addon_version"),
                   "export_settings": exp.get("settings"), "rulebook_runner": rb["versions"], "simready_runner": sr["pins"],
                   "simready_coverage": {k: len(sr[k]) for k in ("codes_with_rule", "pinned_with_rule",
                                         "pinned_registered_no_rule", "pinned_not_registered", "executable_not_pinned")},
                   "executable_not_pinned": sr["executable_not_pinned"]}
real = grab("--real", 5)
if real:
    V, corpus, exp, rb, sr = (load(p) for p in real)
    views = {n: V["files"][s["path"]] for n, s in corpus["scenes"].items()}
    out["corpora"]["real"] = judge(views, exp, rb, sr, "real", own_pairs=False)
    out["corpora"]["real"]["corpus"] = {"files": len(views), "controls": sum(1 for s in corpus["scenes"].values() if s["why"] == ["(control)"])}
DEST.write_text(json.dumps(out, indent=1, default=dict))
