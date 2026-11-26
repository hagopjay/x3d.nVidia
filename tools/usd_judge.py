"""Run model-written OpenUSD splat scripts and grade what they actually write.

    python tools/usd_judge.py receipts/probe-*.json [--out receipts/usd-judge-<stamp>.json]

For each ``usd[*]`` row of a probe receipt: extract the code block, show it,
run it with ``python -I`` in its own empty temp dir (timeout 120 s), then open
the ``splats.usda`` it wrote with usd-core and check, in order:

  ran      exit 0 and a .usda/.usd file appeared
  prim     a prim of type ParticleField3DGaussianSplat exists
  arrays   positions/orientations/scales/opacities authored, same length N >= 2
  types    orientations are quatf[] (not vec), scales float3[], opacities float[]
  sh       radiance:sphericalHarmonicsCoefficients length == N * (degree+1)^2
  ranges   x3dnv's SplatCloud.check(): unit quaternions, scales >= 0, opacities 0..1
  x3d      the file converts to an X3D 4.1 GaussianSplats node (x3dnv.splats)

Score = checks passed (0..7). The code is model output: it runs isolated, and
it is printed before it runs so a human can see what ran.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CHECKS = ["ran", "prim", "arrays", "types", "sh", "ranges", "x3d"]


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return max(blocks, key=len) if blocks else (text or "")


def judge_file(path: Path) -> dict:
    from pxr import Usd, UsdVol

    from x3dnv import splats as S

    r = {k: False for k in CHECKS[1:]}
    st = Usd.Stage.Open(str(path))
    prims = [p for p in st.Traverse() if p.GetTypeName() == "ParticleField3DGaussianSplat"]
    if not prims:
        r["detail"] = "no ParticleField3DGaussianSplat prim"
        return r
    r["prim"] = True
    p = prims[0]
    attrs = {n: p.GetAttribute(n) for n in ("positions", "orientations", "scales", "opacities",
                                            "radiance:sphericalHarmonicsCoefficients",
                                            "radiance:sphericalHarmonicsDegree")}
    vals = {n: (a.Get() if a and a.HasAuthoredValue() else None) for n, a in attrs.items()}
    lens = {n: (len(v) if v is not None and hasattr(v, "__len__") else None) for n, v in vals.items()}
    r["lengths"] = lens
    n = lens["positions"]
    r["arrays"] = bool(n and n >= 2 and all(lens[k] == n for k in ("orientations", "scales", "opacities")))
    tn = {k: str(attrs[k].GetTypeName()) if attrs[k] else None for k in attrs}
    r["type_names"] = tn
    r["types"] = (tn["orientations"] == "quatf[]" and tn["scales"] == "float3[]" and tn["opacities"] == "float[]")
    deg = vals["radiance:sphericalHarmonicsDegree"]
    deg = int(deg) if deg is not None else 3  # schema fallback is 3
    r["degree"] = deg
    shn = lens["radiance:sphericalHarmonicsCoefficients"]
    r["sh"] = bool(n and shn == n * (deg + 1) ** 2)
    if r["arrays"] and r["types"] and r["sh"]:
        try:
            c = S.read_usd(path)
            probs = c.check()
            r["range_problems"] = probs
            r["ranges"] = not probs
            out = path.with_suffix(".x3d")
            S.write_x3d(c, out)
            r["x3d"] = S.read_x3d(out).n == c.n
        except Exception as e:  # noqa: BLE001
            r["detail"] = f"x3dnv: {e}"
    return r


def judge_row(row: dict, show=print) -> dict:
    code = extract_code(row.get("content") or "")
    res = {"model": row.get("model"), "code_lines": code.count("\n") + 1, "ran": False}
    show(f"\n===== {row.get('model')} ({res['code_lines']} lines) =====\n{code}\n===== end =====")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "model_script.py").write_text(code)
        try:
            pr = subprocess.run([sys.executable, "-I", "model_script.py"], cwd=d, capture_output=True,
                                text=True, timeout=120)
            res["returncode"] = pr.returncode
            res["stderr_tail"] = pr.stderr[-1500:] or None
        except subprocess.TimeoutExpired:
            res["returncode"] = None
            res["stderr_tail"] = "timeout 120 s"
        files = sorted(p for p in Path(d).iterdir() if p.suffix in (".usda", ".usd", ".usdc"))
        res["files"] = [p.name for p in files]
        res["ran"] = res.get("returncode") == 0 and bool(files)
        if files:
            try:
                res.update(judge_file(files[0]))
                res["usda_head"] = files[0].read_text(errors="replace")[:1500] if files[0].suffix == ".usda" else None
            except Exception as e:  # noqa: BLE001
                res["detail"] = f"open failed: {e}"
    res["score"] = sum(bool(res.get(k)) for k in CHECKS)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    from pxr import Usd

    rows = []
    for f in a.receipts:
        rows += [dict(r, _receipt=Path(f).name) for r in json.loads(Path(f).read_text()).get("usd", [])]
    results = []
    for r in rows:
        j = judge_row(r)
        j["receipt"] = r["_receipt"]
        j["probe_markers"] = sum((r.get("markers") or {}).values())
        j["probe_truncated"] = r.get("truncated")
        results.append(j)
        print(f"[usd-judge] {j['model']}: {j['score']}/7 " + " ".join(f"{k}={'Y' if j.get(k) else 'n'}" for k in CHECKS))
    rec = {"schema": "x3dnv.usd-judge/1", "when": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "usd_core": ".".join(map(str, Usd.GetVersion())), "python": sys.version.split()[0], "results": results}
    out = Path(a.out or f"usd-judge-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
    out.write_text(json.dumps(rec, indent=2, default=str))
    print(f"[usd-judge] wrote {out}")
    return rec


if __name__ == "__main__":
    main()
