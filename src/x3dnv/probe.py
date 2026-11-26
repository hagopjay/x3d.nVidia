"""Live probe of the NVIDIA API Catalog for X3D work. Needs NVIDIA_API_KEY.

    python -m x3dnv.probe --out receipts/            # catalog + chat rounds
    python -m x3dnv.probe --out receipts/ --trellis cube.png   # + TRELLIS (spends credits)

Each step writes what it saw; anything not measured is ``null``. Receipts
carry the key's 8-hex id, never the key. Steps:

1. catalog : every model id, and the ids matching 3D / USD / world / VLM words.
2. x3d     : each chat model writes a tiny X3D 4.0 scene; scored by x3dcheck.
3. usd     : each model is asked for pxr code making a ParticleField3DGaussianSplat
             (OpenUSD 26.03). Static check only; nothing is executed.
4. trellis : optional, image -> glb; the glb is saved and summarised.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import re
import sys
import time
from pathlib import Path

from . import __version__
from .nim import NIM, redact
from .x3dcheck import check_x3d, extract_x3d

WORDS = {
    "3d": r"3d|trellis|mesh|splat|lyra|gen3c|edify",
    "usd": r"usd",
    "world": r"cosmos",
    "vlm": r"vila|vl\b|-vl-|vision|omni|reason",
    "nemotron": r"nemotron",
    "embed": r"embed|rerank|retriev",
}
DEFAULT_CHAT = [
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-nano-30b-a3b",
]
X3D_TASK = (
    "Write a complete, minimal X3D 4.0 XML file (XML encoding, profile Interchange) "
    "with a Viewpoint at 0 0 6, a red Box of size 1 1 1, and a DirectionalLight. "
    "Return only the XML.")
USD_TASK = (
    "Using the OpenUSD Python API (pxr, version 26.03 or newer), write a short script that "
    "creates a stage with one UsdVol.ParticleField3DGaussianSplat prim holding two splats: set "
    "positions, orientations, scales, opacities, radiance:sphericalHarmonicsDegree = 0 and "
    "radiance:sphericalHarmonicsCoefficients, then save it as splats.usda. Return only code.")
USD_MARKERS = ["ParticleField3DGaussianSplat", "radiance:sphericalHarmonicsCoefficients",
               "orientations", "opacities", "scales"]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="x3dnv-probe")
    ap.add_argument("--out", default="receipts")
    ap.add_argument("--models", nargs="*", default=None, help="chat models (default: Nemotron 3 Super + Nano, plus any 'usd' ids)")
    ap.add_argument("--skip-chat", action="store_true")
    ap.add_argument("--trellis", default=None, help="PNG to send to microsoft/trellis")
    ap.add_argument("--rpm", type=float, default=None)
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log = lambda m: print(m, flush=True)
    nim = NIM(rpm=a.rpm, log=log)
    rec = {"schema": "x3dnv.probe/1", "started": now(), "x3dnv": __version__,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "key_id": nim.key_id, "rpm": nim.pacer.rpm, "catalog": None, "x3d": [], "usd": [],
           "trellis": None}

    def save():
        p = out / f"probe-{stamp}.json"
        p.write_text(json.dumps(rec, indent=2, default=str))
        return p

    # 1. catalog -------------------------------------------------------------
    log(f"[probe] key {nim.key_id}, pacing {nim.pacer.rpm:g} rpm")
    try:
        ids = nim.models()
        groups = {k: [i for i in ids if re.search(rx, i, re.I)] for k, rx in WORDS.items()}
        rec["catalog"] = {"count": len(ids), "ids": ids, "groups": groups}
        log(f"[probe] catalog: {len(ids)} ids; " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()))
    except Exception as e:  # noqa: BLE001
        rec["catalog"] = {"error": str(e)}
        log(f"[probe] catalog failed: {e}")
        groups, ids = {}, []
    save()

    # 2-3. chat rounds -------------------------------------------------------
    models = a.models if a.models is not None else DEFAULT_CHAT + groups.get("usd", [])
    if ids:
        missing = [m for m in models if m not in ids]
        if missing:
            log(f"[probe] not in catalog (recorded, skipped): {missing}")
            rec["missing_models"] = missing
        models = [m for m in models if m in ids]
    for m in ([] if a.skip_chat else models):
        for task, bucket in ((X3D_TASK, "x3d"), (USD_TASK, "usd")):
            log(f"[probe] {bucket} <- {m}")
            c = nim.chat(m, [{"role": "user", "content": task}], max_tokens=4096, temperature=0.2)
            row = {"model": m, **c.receipt()}
            if c.content is not None and bucket == "x3d":
                row["check"] = check_x3d(extract_x3d(c.content))
            if c.content is not None and bucket == "usd":
                row["markers"] = {k: (k in c.content) for k in USD_MARKERS}
                row["mentions_UsdVol"] = "UsdVol" in c.content
            row["content"] = (c.content or "")[:6000] or None
            row["reasoning"] = (c.reasoning or "")[:1500] or None
            rec[bucket].append(row)
            log(f"[probe]   status {c.status} in {c.seconds}s, attempts {c.attempts}"
                + (f", score {row['check']['score']}" if 'check' in row else "")
                + (f", markers {sum(row['markers'].values())}/{len(USD_MARKERS)}" if 'markers' in row else ""))
            save()

    # 4. TRELLIS ---------------------------------------------------------------
    if a.trellis:
        png = Path(a.trellis).read_bytes()
        log(f"[probe] trellis <- {a.trellis} ({len(png):,} bytes)")
        c, glbs = nim.trellis(png, seed=0)
        rec["trellis"] = {**c.receipt(), "response": redact(c.raw), "glbs": []}
        for i, g in enumerate(glbs):
            p = out / f"trellis-{stamp}-{i}.glb"
            p.write_bytes(g)
            rec["trellis"]["glbs"].append({"path": str(p), "bytes": len(g)})
        log(f"[probe]   status {c.status} in {c.seconds}s, glbs {len(glbs)}")

    rec["finished"] = now()
    p = save()
    log(f"[probe] receipt {p}")
    return rec


if __name__ == "__main__":
    main()
