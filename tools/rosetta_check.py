"""Splat Rosetta conformance: one splat through PLY / X3D / USD / glTF, graded by X_ITE.

    python tools/rosetta_check.py --ply cloud.ply --work /tmp/rosetta --node-dir <dir with
        node_modules/{x_ite,playwright,gltf-validator}> [--max-splats 20000] [--gpu]

Steps (each recorded in the receipt; anything not run is null):
  1. read the 3DGS .ply; keep the N most opaque splats (X3D XML is ~2.5x the PLY bytes)
  2. write .ply (subset), .x3d (native GaussianSplats), .usda, .glb; read each back
  3. validators: OpenUSD UsdValidation (all registered), Khronos gltf-validator
  4. chain: ply -> glb -> usda -> x3d
  5. X_ITE renders  A = Inline .ply (X_ITE's own parser)  B = native node  C = chain
     and we compare B and C to A pixel by pixel.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from x3dnv import splats as S  # noqa: E402

VP = [{"description": "Initial View", "position": "0.3193368 0.8510529 1.491291",
       "orientation": "-0.917970710761992 0.385054407683762 0.0951991455131259 0.526171495114352"}]


def log(m):
    print(m, flush=True)


def usd_validate(path):
    try:
        from pxr import Usd, UsdValidation as V

        vs = V.ValidationRegistry().GetOrLoadAllValidators()
        errs = V.ValidationContext(vs).Validate(Usd.Stage.Open(str(path)))
        return {"tool": f"usd-core {'.'.join(map(str, Usd.GetVersion()))} UsdValidation",
                "validators": len(vs), "errors": [f"{e.GetName()}: {e.GetMessage()[:200]}" for e in errs]}
    except Exception as e:  # noqa: BLE001
        return {"tool": None, "error": str(e)}


def gltf_validate(path, node_dir):
    js = ("const v=require('gltf-validator'),fs=require('fs');"
          "v.validateBytes(new Uint8Array(fs.readFileSync(process.argv[1]))).then(r=>{const c={};"
          "for(const m of r.issues.messages){c[m.code]=(c[m.code]||0)+1};"
          "console.log(JSON.stringify({version:r.validatorVersion,errors:r.issues.numErrors,"
          "warnings:r.issues.numWarnings,infos:r.issues.numInfos,codes:c}))})")
    try:
        out = subprocess.run(["node", "-e", js, str(path)], cwd=node_dir, capture_output=True,
                             text=True, timeout=300, check=True).stdout
        return {"tool": "gltf-validator (npm)", **json.loads(out)}
    except Exception as e:  # noqa: BLE001
        return {"tool": None, "error": str(e)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True)
    ap.add_argument("--work", default="rosetta-out")
    ap.add_argument("--node-dir", default=".")
    ap.add_argument("--max-splats", type=int, default=20000)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--receipt", default=None)
    a = ap.parse_args(argv)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    rec = {"schema": "x3dnv.rosetta/1", "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "python": sys.version.split()[0], "platform": platform.platform(), "source": Path(a.ply).name}

    t = time.time()
    full = S.read_ply(a.ply)
    rec["source_stats"] = {"n": full.n, "degree": full.degree, "bytes": Path(a.ply).stat().st_size,
                           "read_s": round(time.time() - t, 3), "problems": full.check()}
    log(f"[rosetta] {a.ply}: {full.n:,} splats, SH degree {full.degree}")
    c = full.subset(np.sort(np.argsort(-full.opacities)[: a.max_splats])) if full.n > a.max_splats else full
    rec["subset"] = {"n": c.n, "rule": f"{a.max_splats} most opaque"}

    files, rt = {}, {}
    for ext in (".ply", ".x3d", ".usda", ".glb"):
        p = work / f"cloud{ext}"
        t = time.time()
        S.WRITERS[ext](c, p, **({"viewpoints": VP} if ext == ".x3d" else {}))
        w = time.time() - t
        t = time.time()
        back = S.READERS[ext](p)
        files[ext] = {"bytes": p.stat().st_size, "write_s": round(w, 3), "read_s": round(time.time() - t, 3)}
        rt[ext] = c.equal(back)
        log(f"[rosetta] {ext}: {files[ext]['bytes']:,} bytes, max |delta| "
            + ", ".join(f"{k} {v:.2g}" for k, v in rt[ext].items() if isinstance(v, float)))
    rec["files"], rec["round_trip"] = files, rt
    rec["validators"] = {"usd": usd_validate(work / "cloud.usda"),
                         "gltf": gltf_validate(work / "cloud.glb", a.node_dir), "x3d": None}
    log(f"[rosetta] validators: {json.dumps(rec['validators'])[:400]}")

    chain = S.read_usd(S.write_usd(S.read_glb(work / "cloud.glb"), work / "chain.usda"))
    S.write_x3d(chain, work / "chain.x3d", viewpoints=VP)
    S.write_x3d(c, work / "inline.x3d", inline_ply="cloud.ply", viewpoints=VP)
    S.write_x3d(c, work / "native.x3d", viewpoints=VP)
    rec["chain_equal"] = c.equal(chain)

    cmd = ["node", str(Path(__file__).with_name("xite_render.mjs")), "--xite",
           str(Path(a.node_dir) / "node_modules/x_ite/dist"), "--root", str(work), "--out",
           str(work / "frames"), "--size", str(a.size), "--settle", "4000"] + (["--gpu"] if a.gpu else []) + [
           "inline.x3d", "native.x3d", "chain.x3d"]
    try:
        out = subprocess.run(cmd, cwd=a.node_dir, capture_output=True, text=True, timeout=900, check=True).stdout
        renders = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        xite_ver = json.loads((Path(a.node_dir) / "node_modules/x_ite/package.json").read_text())["version"]
        from PIL import Image

        img = {Path(r["png"]).stem: np.asarray(Image.open(r["png"]).convert("RGB")).astype(int) for r in renders}
        ref = img["inline"]
        rec["xite"] = {"version": xite_ver, "renderer": renders[0]["rendererInfo"]["renderer"],
                       "errors": sum((r["errors"] for r in renders), []), "size": a.size,
                       "lit_pixels": int((ref.max(2) > 8).sum()), "compare_to_inline": {}}
        for k in ("native", "chain"):
            d = np.abs(img[k] - ref)
            rec["xite"]["compare_to_inline"][k] = {"max": int(d.max()), "mean": round(float(d.mean()), 5),
                                                   "pixels_differing": int((d.max(2) > 0).sum())}
        sheet = Image.new("RGB", (a.size * 3, a.size))
        for i, k in enumerate(("inline", "native", "chain")):
            sheet.paste(Image.fromarray(img[k].astype("uint8")), (i * a.size, 0))
        sheet.save(work / "frames" / "sheet.png")
        log(f"[rosetta] X_ITE {xite_ver} on {rec['xite']['renderer']}: {rec['xite']['compare_to_inline']}")
    except Exception as e:  # noqa: BLE001
        rec["xite"] = {"error": str(e)[:1000]}
        log(f"[rosetta] X_ITE render failed: {e}")

    rec["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = Path(a.receipt) if a.receipt else work / "rosetta-receipt.json"
    out.write_text(json.dumps(rec, indent=2))
    log(f"[rosetta] receipt {out}")
    return rec


if __name__ == "__main__":
    main()
