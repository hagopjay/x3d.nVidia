"""Q12 run 2, stage 2a: usd-core UsdValidation and the Omniverse Asset Validator on every exported .usdc.

    python -I run_rulebooks.py USD_DIR RULES.json OUT.json        # Python 3.12: omniverse-asset-validator 1.18.0

USD_DIR holds <variant>/<scene>/<scene>.usdc (export_blender.py). RULES.json is x3d_mcp's tests/usd_rules.json, the
pinned rule list. Each rule runs alone and guarded, as in x3d_mcp #33: a rule that raises is "not-run", never a pass.
Verdicts per rule: pass, fail (any error, failure or warning), not-run: <why>. Messages of failures are kept (first 2).
"""
import glob
import importlib.metadata as md
import json
import logging
import os
import sys

logging.disable(logging.CRITICAL)
from pxr import Usd, UsdValidation  # noqa: E402
import omni.asset_validator as av  # noqa: E402

usd_dir, rules_json, dest = sys.argv[1:4]
PINNED = {r["id"] for r in json.load(open(rules_json))["rules"]}
reg = UsdValidation.ValidationRegistry()
usd_vals = {"usd:" + v.GetMetadata().name: v for v in reg.GetOrLoadAllValidators()}
oav = {}
for n in dir(av):
    c = getattr(av, n)
    if "oav:" + n in PINNED and isinstance(c, type) and issubclass(c, av.BaseRuleChecker):
        oav["oav:" + n] = c
BAD = (av.IssueSeverity.ERROR, av.IssueSeverity.FAILURE, av.IssueSeverity.WARNING)
res = {}
for f in sorted(glob.glob(os.path.join(usd_dir, "*", "*", "*.usd[ac]"))):
    v, n = f.split(os.sep)[-3:-1]
    r, msg = {}, {}
    stage = Usd.Stage.Open(f)
    for rid, val in usd_vals.items():
        try:
            errs = val.Validate(stage)
            r[rid] = "fail" if errs else "pass"
            if errs:
                msg[rid] = [e.GetMessage()[:160] for e in errs[:2]]
        except Exception as e:
            r[rid] = "not-run: " + str(e)[:80]
    for rid, cls in oav.items():
        try:
            e = av.ValidationEngine(init_rules=False)
            e.enable_rule(cls)
            iss = [i for i in e.validate(f).issues() if i.severity in BAD]
            r[rid] = "fail" if iss else "pass"
            if iss:
                msg[rid] = [str(i.message)[:160] for i in iss[:2]]
        except Exception as ex:
            r[rid] = "not-run: " + str(ex)[:80]
    res.setdefault(v, {})[n] = {"verdicts": r, "messages": msg}
versions = {"usd-core": md.version("usd-core"), "omniverse-asset-validator": md.version("omniverse-asset-validator"),
            "python": sys.version.split()[0]}
json.dump({"versions": versions, "rules": sorted(set(usd_vals) | set(oav)), "variants": res}, open(dest, "w"), indent=0)
print({v: len(s) for v, s in res.items()}, "scenes;", len(usd_vals), "usd-core +", len(oav), "Omniverse rules")
