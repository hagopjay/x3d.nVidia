#!/usr/bin/env python3
"""x3d.nVidia Q1 probe, one file, stdlib only (from hagopjay/x3d.nVidia, matches repo probe v0.1.1).

    python3 x3dnv_probe.py                 # catalog + X3D + USD rounds (~5 requests)
    python3 x3dnv_probe.py --trellis a.png # + TRELLIS image -> glb (spends credit)

Auth: sends NO Authorization header unless NVIDIA_API_KEY is set; in a Claude
cloud environment with a network secret for *.api.nvidia.com the proxy adds it.
Writes probe-<stamp>.json (never contains the key) and prints a summary.
"""
import argparse, base64, datetime as dt, json, os, re, sys, time, urllib.error, urllib.request
from xml.etree import ElementTree as ET

CHAT, GENAI = "https://integrate.api.nvidia.com/v1", "https://ai.api.nvidia.com/v1/genai"
KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
RPM = float(os.environ.get("X3DNV_NVIDIA_RPM", 36))
MAX_TOKENS = int(os.environ.get("X3DNV_MAX_TOKENS", 16384))  # Nemotron 3.5 reasons ~4.7-5.6k tokens first
ONLY = os.environ.get("X3DNV_ONLY", "")  # "x3d" or "usd"
NO_THINK = os.environ.get("X3DNV_NO_THINK", "") not in ("", "0")
WORDS = {"3d": r"3d|trellis|mesh|splat|lyra|gen3c|edify", "usd": r"usd", "world": r"cosmos",
         "vlm": r"vila|vl\b|-vl-|vision|omni|reason", "nemotron": r"nemotron", "embed": r"embed|rerank|retriev"}
MODELS = ["nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b",
          "nvidia/nemotron-3-super-120b-a12b"]
X3D_TASK = ("Write a complete, minimal X3D 4.0 XML file (XML encoding, profile Interchange) with a Viewpoint "
            "at 0 0 6, a red Box of size 1 1 1, and a DirectionalLight. Return only the XML.")
USD_TASK = ("Using the OpenUSD Python API (pxr, version 26.03 or newer), write a short script that creates a stage "
            "with one UsdVol.ParticleField3DGaussianSplat prim holding two splats: set positions, orientations, "
            "scales, opacities, radiance:sphericalHarmonicsDegree = 0 and radiance:sphericalHarmonicsCoefficients, "
            "then save it as splats.usda. Return only code.")
USD_MARKERS = ["ParticleField3DGaussianSplat", "radiance:sphericalHarmonicsCoefficients", "orientations", "opacities", "scales"]
_next = [0.0]


def http(method, url, payload=None):
    wait = max(0.0, _next[0] - time.monotonic()); time.sleep(wait)
    _next[0] = max(time.monotonic(), _next[0]) + 60.0 / RPM
    h = {"Accept": "application/json"}
    if KEY: h["Authorization"] = f"Bearer {KEY}"
    body = json.dumps(payload).encode() if payload is not None else None
    if body: h["Content-Type"] = "application/json"
    t0 = time.monotonic()
    for attempt in range(1, 7):
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                st, hd, data = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            st, hd, data = e.code, dict(e.headers or {}), e.read()
        if (st == 429 or st >= 500) and attempt < 6:
            d = float(hd.get("Retry-After") or min(60, 2 ** attempt)); print(f"  {st}, retry in {d:.0f}s", flush=True)
            time.sleep(d); continue
        break
    try: js = json.loads(data) if data else None
    except ValueError: js = {"_text": data[:2000].decode("utf-8", "replace")}
    rl = {k: v for k, v in hd.items() if k.lower().startswith(("x-ratelimit", "retry-after", "nvcf", "x-request"))}
    return {"status": st, "seconds": round(time.monotonic() - t0, 2), "attempts": attempt, "headers": rl}, js


def chat(model, task):
    payload = {"model": model, "max_tokens": MAX_TOKENS, "temperature": 0.2,
               "messages": [{"role": "user", "content": task}]}
    if NO_THINK: payload["chat_template_kwargs"] = {"enable_thinking": False}
    meta, js = http("POST", f"{CHAT}/chat/completions", payload)
    ch = ((js or {}).get("choices") or [{}])[0] if meta["status"] == 200 else {}
    text = ch.get("message", {}).get("content")
    meta["finish_reason"] = ch.get("finish_reason"); meta["truncated"] = ch.get("finish_reason") == "length"
    if meta["truncated"]: print(f"  WARNING {model} hit max_tokens={MAX_TOKENS}: not a fair score", flush=True)
    if text is not None: text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip()
    return {**meta, "usage": (js or {}).get("usage"), "error": None if text is not None else json.dumps(js)[:500]}, text


def check_x3d(text):
    m = re.search(r"```(?:xml|x3d)?\s*(.*?)```", text, re.S); text = m.group(1) if m else text
    s, e = text.find("<X3D") if "<?xml" not in text else text.find("<?xml"), text.rfind("</X3D>")
    xml = text[s:e + 6] if s >= 0 and e > s else text
    out = {"parses": False, "score": 0}
    try: root = ET.fromstring(xml)
    except ET.ParseError as err: out["error"] = str(err); return out
    tags = {el.tag for el in root.iter()}
    arity = {"position": 3, "size": 3, "diffuseColor": 3, "direction": 3, "orientation": 4}
    bad = [f"{el.tag}@{k}" for el in root.iter() for k, n in arity.items()
           if el.get(k) is not None and len(el.get(k).replace(",", " ").split()) != n]
    missing = [w for w in ("Viewpoint", "Box", "DirectionalLight") if w not in tags]
    bad += [f"X3D/{c.tag}" for c in root if c.tag not in ("head", "Scene")]  # X3D XML is case-sensitive
    hd = root.find("head")
    bad += [f"head/{c.tag}" for c in (hd if hd is not None else []) if c.tag not in ("component", "unit", "meta")]
    scene = root.find("Scene")
    out.update(parses=True, version=root.get("version"), missing=missing, arity_errors=bad,
               score=1 + int(root.tag == "X3D" and bool(root.get("version"))) + int(scene is not None and len(scene) > 0)
               + int(not missing) + int(not bad))
    return out


def glbs(obj, found=None):
    found = [] if found is None else found
    if isinstance(obj, dict): [glbs(v, found) for v in obj.values()]
    elif isinstance(obj, list): [glbs(v, found) for v in obj]
    elif isinstance(obj, str):
        s = obj.split(",", 1)[1] if obj.startswith("data:") else obj
        if s.startswith("Z2xURg"): found.append(base64.b64decode(s))
    return found


def short(o):
    if isinstance(o, dict): return {k: short(v) for k, v in o.items()}
    if isinstance(o, list): return [short(v) for v in o]
    return o[:60] + f"...<{len(o)} chars>" if isinstance(o, str) and len(o) > 300 else o


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trellis"); ap.add_argument("--models", nargs="*")
    a = ap.parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    rec = {"schema": "x3dnv.probe/1", "source": "x3dnv_probe.py standalone (75cad4e)", "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "python": sys.version.split()[0], "auth": "env key" if KEY else "proxy network secret", "rpm": RPM, "max_tokens": MAX_TOKENS, "only": ONLY or None, "no_think": NO_THINK, "x3d": [], "usd": []}
    save = lambda: open(f"probe-{stamp}.json", "w").write(json.dumps(rec, indent=2))
    meta, js = http("GET", f"{CHAT}/models")
    ids = sorted(m["id"] for m in (js or {}).get("data", [])) if meta["status"] == 200 else []
    groups = {k: [i for i in ids if re.search(rx, i, re.I)] for k, rx in WORDS.items()}
    rec["catalog"] = {**meta, "count": len(ids), "groups": groups, "ids": ids,
                      "error": None if ids else json.dumps(js)[:500]}
    print(f"[catalog] HTTP {meta['status']}: {len(ids)} ids; " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()), flush=True)
    for k, v in groups.items(): print(f"  {k:8s} {', '.join(v)}")
    save()
    models = a.models or (MODELS + groups["usd"])
    rec["missing_models"] = [m for m in models if ids and m not in ids]
    for m in [m for m in models if not ids or m in ids]:
        if ONLY != "usd":
            meta, text = chat(m, X3D_TASK)
            row = {"model": m, **meta, "check": check_x3d(text) if text else None, "content": (text or "")[:6000] or None}
            rec["x3d"].append(row); save()
            print(f"[x3d] {m}: HTTP {meta['status']} {meta['seconds']}s score {row['check'] and row['check']['score']}/5", flush=True)
        if ONLY == "x3d": continue
        meta, text = chat(m, USD_TASK)
        mk = {k: k in (text or "") for k in USD_MARKERS}
        rec["usd"].append({"model": m, **meta, "markers": mk, "content": (text or "")[:12000] or None}); save()
        print(f"[usd] {m}: HTTP {meta['status']} {meta['seconds']}s markers {sum(mk.values())}/5", flush=True)
    if a.trellis:
        img = "data:image/png;base64," + base64.b64encode(open(a.trellis, "rb").read()).decode()
        meta, js = http("POST", f"{GENAI}/microsoft/trellis", {"image": img, "seed": 0})
        out = []
        for i, g in enumerate(glbs(js)):
            open(f"trellis-{stamp}-{i}.glb", "wb").write(g); out.append({"file": f"trellis-{stamp}-{i}.glb", "bytes": len(g)})
        rec["trellis"] = {**meta, "response": short(js), "glbs": out}
        print(f"[trellis] HTTP {meta['status']} {meta['seconds']}s glbs {len(out)}", flush=True)
    rec["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); save()
    print(f"[probe] wrote probe-{stamp}.json")


if __name__ == "__main__":
    main()
