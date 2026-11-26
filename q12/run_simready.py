"""Q12 run 2, stage 2b: the SimReady Foundation requirements, executed, on every exported .usdc.

    python -I run_simready.py USD_DIR RULES.json OUT.json

Needs Python 3.11-3.13 with usd-validation-nvidia 1.23.0 and the SimReady tiers built from NVIDIA/simready-foundation
(nv_core/tiers: core, newton, isaac, aif, sensors), e.g.
    pip install usd-validation-nvidia==1.23.0 usd-core==26.11 ./nv_core/tiers/simready_foundation_tier_core ...

x3d_mcp #33 reported SimReady as "270 requirement pages, not executable". The tiers ARE executable: their rules
register with usd_validation_nvidia, which tags every issue with the requirement it enforces. Every rule of every
installed tier runs on every file (no profile is chosen, so requirements that a profile would not apply still run;
the join only reads the ones x3d_mcp maps to an X3D check).

Verdict per requirement code (codes as in usd_rules.json, "sr:" + code without the com.nvidia.* prefix):
    fail       an error, failure or warning issue tagged with it (or raised by a rule bound only to it)
    not-run    every issue for it says the requirement was not evaluated (a schema or tier is missing)
    pass       a rule bound to it ran and raised nothing
    no-rule    registered, but no installed rule enforces it (it stays a requirement page)
"""
import glob
import importlib.metadata as md
import json
import logging
import os
import re
import sys
from collections import defaultdict

logging.disable(logging.CRITICAL)
import usd_validation_nvidia as v  # noqa: E402

usd_dir, rules_json, dest = sys.argv[1:4]
short = lambda c: re.sub(r"^com\.nvidia\.(usd|simready)\.", "", c)
PINNED = {r["id"][3:] for r in json.load(open(rules_json))["rules"] if r["id"].startswith("sr:")}
eng = v.ValidationEngine(init_rules=True)
R = v.RequirementsRegistry()
rules = list(eng.rules)
served = defaultdict(set)                     # code -> rule names
by_rule = {}
for r in rules:
    cs = {short(q.code) for q in R.get_requirements(r)}
    by_rule[r.__name__] = cs
    for c in cs:
        served[c].add(r.__name__)
registered = {short(q.code) for q in R}
BAD = {v.IssueSeverity.ERROR, v.IssueSeverity.FAILURE, v.IssueSeverity.WARNING}
NOT_EVAL = re.compile(r"not evaluated|unavailable|not installed|could not be imported|uncaught error", re.I)   # a rule that crashed did not judge


def code_of(issue):
    q = getattr(issue, "requirement", None)
    c = getattr(q, "code", None)
    if c:
        return {short(c)}
    rule = getattr(issue, "rule", None)
    return set(by_rule.get(getattr(rule, "__name__", ""), set()))


res = {}
for f in sorted(glob.glob(os.path.join(usd_dir, "*", "*", "*.usd[ac]"))):
    var, n = f.split(os.sep)[-3:-1]
    try:
        issues = list(eng.validate(f).issues())
    except Exception as e:
        res.setdefault(var, {})[n] = {"crash": str(e)[:200]}
        continue
    bad, noeval, msg, sev = defaultdict(int), defaultdict(int), {}, {}
    for i in issues:
        if i.severity not in BAD:
            continue
        m = str(getattr(i, "message", ""))
        for c in code_of(i):
            if NOT_EVAL.search(m):
                noeval[c] += 1
            else:
                bad[c] += 1
                msg.setdefault(c, m[:160])
                sev[c] = str(i.severity).split(".")[-1]
    verdicts = {}
    for c in sorted(served):
        verdicts[c] = "fail" if bad[c] else ("not-run: not evaluated" if noeval[c] else "pass")
    res.setdefault(var, {})[n] = {"verdicts": verdicts, "messages": msg, "severity": sev, "issues": len(issues)}
pins = {"usd-validation-nvidia": md.version("usd-validation-nvidia"), "usd-core": md.version("usd-core"),
        "python": sys.version.split()[0]}
for d in md.distributions():
    nm = d.metadata["Name"] or ""
    if nm.startswith("simready-foundation-tier"):
        pins[nm] = d.version
out = {"pins": pins, "rules": len(rules), "codes_with_rule": sorted(served), "registered": sorted(registered),
       "pinned_with_rule": sorted(PINNED & set(served)), "pinned_registered_no_rule": sorted((PINNED & registered) - set(served)),
       "pinned_not_registered": sorted(PINNED - registered), "executable_not_pinned": sorted(set(served) - PINNED),
       "variants": res}
json.dump(out, open(dest, "w"), indent=0)
print(len(rules), "rules;", len(served), "codes executable;", len(PINNED & set(served)), "of", len(PINNED), "pinned;",
      {k: len(s) for k, s in res.items()}, "scenes")
