"""The X3D SimReady profile, crossed: every proof scene of x3d_mcp's profile checks, written to USD and judged by
NVIDIA's own validator. One receipt per rule.

    python -I q12/profile_crossing.py X3D_MCP_DIR WORK_DIR RECEIPT.json

For each rule that x3d_mcp's tests/usd_parity.py maps with status "profile", its fixture has a failing and a passing
X3D scene. This script

    1. asks x3d_mcp whether its check reports the failing scene and passes the passing one (x3d_mcp's own runner),
    2. writes both scenes to USD with src/x3dnv/x3d2usdphysics.py (no --meta, nothing repaired),
    3. runs the SimReady requirement the rule names, as registered by the installed tiers, on both USD files,

and grades the crossing:

    confirmed    X3D reports the failing scene, SimReady fails its USD; X3D passes the passing scene, SimReady passes
                 its USD. The X3D check predicts the SimReady verdict on this pair.
    x3d-only     the X3D pair behaves, and no installed SimReady rule enforces the requirement (it is a page only)
    mismatch     anything else; printed, and the exit code is 1

Needs Python 3.11 to 3.13 with usd-core 26.11, usd-validation-nvidia 1.23.0, the SimReady tiers built from
NVIDIA/simready-foundation (nv_core/tiers: core, newton, isaac, aif, sensors), numpy, lxml, and x3d_mcp's validator
imports (xmlschema, jsonschema, x3d).

Nine checker classes of the core tier (semantic labels and the six dataset taxonomies) are registered with their
requirement but are not in the engine's default rule set; they are enabled here with enable_rule and listed in the
receipt under "enabled_by_hand". Nothing else about the engine is changed.
"""
import hashlib
import importlib.metadata as md
import json
import logging
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

A = sys.argv[1:]
MCP, WORK, DEST = Path(A[0]).resolve(), Path(A[1]).resolve(), Path(A[2])
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(MCP / "tests"), str(MCP / "src"), str(HERE.parent / "src")]

logging.disable(logging.CRITICAL)
import usd_parity as up  # noqa: E402
import usd_validation_nvidia as v  # noqa: E402
from x3dnv import x3d2usdphysics as xw  # noqa: E402

short = lambda c: re.sub(r"^com\.nvidia\.(usd|simready)\.", "", c)  # noqa: E731
REG = v.RequirementsRegistry()
BY_NAME = {q.display_name: short(q.code) for q in REG}
BAD = {v.IssueSeverity.ERROR, v.IssueSeverity.FAILURE, v.IssueSeverity.WARNING}
NOT_EVAL = re.compile(r"not evaluated|unavailable|not installed|could not be imported|uncaught error", re.I)


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
    served, by_rule = defaultdict(set), {}
    for r in eng.rules:
        cs = {short(q.code) for q in REG.get_requirements(r)}
        by_rule[r.__name__] = cs
        for c in cs:
            served[c].add(r.__name__)
    return eng, served, by_rule, sorted(by_hand), len(default)


ENG, SERVED, BY_RULE, BY_HAND, N_DEFAULT = engine()


def code_for(rule: dict):
    """The SimReady requirement code of a pinned rule: its own code, or the one registered under its name."""
    return rule.get("code") or BY_NAME.get(rule["name"])


def judge(usd: Path, code: str):
    issues = list(ENG.validate(str(usd)).issues())
    hits, noeval = [], 0
    for i in issues:
        if i.severity not in BAD:
            continue
        q = getattr(i, "requirement", None)
        codes = {short(q.code)} if getattr(q, "code", None) else set(BY_RULE.get(getattr(getattr(i, "rule", None), "__name__", ""), set()))
        if code not in codes:
            continue
        m = str(getattr(i, "message", "")).replace(str(WORK), "WORK")      # no machine paths in a receipt
        if NOT_EVAL.search(m):
            noeval += 1
        else:
            hits.append((str(i.severity).split(".")[-1], m[:200]))
    if hits:
        return "fail", hits[0]
    return ("not-run", None) if noeval else ("pass", None)


def main():
    results = up.run_all()                                   # x3d_mcp's own verdict on every fixture
    rules = {r["id"]: r for r in up.RULES["rules"]}
    rows, done = [], {}
    for rid, (status, fx, note) in up.MAP.items():
        if status != "profile":
            continue
        by, check, bad, good = up.F[fx]
        code = code_for(rules[rid])
        x3d = {"reports_failing_scene": bool(results[fx]["bad"]), "reports_passing_scene": bool(results[fx]["good"])}
        row = {"rule": rid, "simready_code": code, "summary": rules[rid].get("summary", "")[:160], "x3d_check": check,
               "fixture": fx, "x3d": x3d, "simready_rules": sorted(SERVED.get(code, [])), "note": note}
        if fx not in done:
            done[fx] = {}
            for label, text in (("failing", bad), ("passing", good)):
                d = WORK / fx / label
                d.mkdir(parents=True, exist_ok=True)
                if '"tex.png"' in text:                      # the one file a proof scene names (the thumbnail)
                    (d / "tex.png").write_bytes(up.IMG["tex.png"])
                src = d / f"{fx.replace('-', '_')}.x3d"
                src.write_text(text, encoding="utf-8")
                out = d / f"{fx.replace('-', '_')}.usda"
                rep = xw.convert(src, out)
                done[fx][label] = (out, {k: rep.get(k) for k in ("dynamic", "static", "shapes", "labels", "meters_per_unit",
                                                                 "meta_missing", "thumbnail")})
        usd = {}
        for label in ("failing", "passing"):
            out, rep = done[fx][label]
            if code and SERVED.get(code):
                verdict, hit = judge(out, code)
                usd[label] = {"verdict": verdict, "severity": hit[0] if hit else None, "message": hit[1] if hit else None,
                              "writer": rep, "usd": str(out.relative_to(WORK))}
            else:
                usd[label] = {"verdict": "no-rule", "writer": rep, "usd": str(out.relative_to(WORK))}
        row["usd"] = usd
        x_ok = x3d["reports_failing_scene"] and not x3d["reports_passing_scene"]
        if not (code and SERVED.get(code)):
            row["crossing"] = "x3d-only" if x_ok else "mismatch"
        elif x_ok and usd["failing"]["verdict"] == "fail" and usd["passing"]["verdict"] == "pass":
            row["crossing"] = "confirmed"
        else:
            row["crossing"] = "mismatch"
        rows.append(row)
    def git_head(d):
        try:
            return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
        except OSError:
            return None
    pins = {"usd-validation-nvidia": md.version("usd-validation-nvidia"), "usd-core": md.version("usd-core"),
            "python": sys.version.split()[0], "simready-foundation": up.RULES["pins"]["simready-foundation"],
            "x3d_mcp": git_head(MCP),
            "x3d2usdphysics_sha256": hashlib.sha256((HERE.parent / "src" / "x3dnv" / "x3d2usdphysics.py").read_bytes()).hexdigest()}
    for d in md.distributions():
        nm = d.metadata["Name"] or ""
        if nm.startswith("simready-foundation-tier"):
            pins[nm] = d.version
    tally = defaultdict(int)
    for r in rows:
        tally[r["crossing"]] += 1
    counts = up.counts(results)
    plain = sum(counts[k] for k in up.STATEABLE) - counts["gap"]
    out = {"what": "X3D SimReady profile draft 2: proof scenes crossed to USD and judged by SimReady's validator",
           "pins": pins, "engine_default_rules": N_DEFAULT, "enabled_by_hand": BY_HAND,
           "ledger": {"rules": len(up.MAP), "stated_by_plain_x3d": plain, "stated_under_profile": counts["profile"],
                      "total_stated": plain + counts["profile"]},
           "crossing": dict(tally), "rows": rows}
    DEST.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['crossing']:10} {r['rule'][3:]:52} {str(r['simready_code']):13} x3d {r['x3d_check']:34} "
              f"usd failing={r['usd']['failing']['verdict']:8} passing={r['usd']['passing']['verdict']}")
    print(dict(tally), "| ledger", out["ledger"])
    return 1 if tally.get("mismatch") else 0


if __name__ == "__main__":
    sys.exit(main())
