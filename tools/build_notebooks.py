"""Build notebooks/*.ipynb from the cell lists below (run after editing)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(True)}


def code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": s.strip("\n").splitlines(True)}


OPTIONS = '''
# ── Options ──────────────────────────────────────────────────────────────
VERBOSE = True   # stream progress and important log lines while tools run
VISUAL  = True   # show charts and frames as soon as each exists
REPO    = "hagopjay/x3d.nVidia"
REF     = "main"
'''

SETUP = '''
# ── Setup: clone (private-repo safe), install. No token is ever printed or saved. ──
import os, sys, subprocess, base64, pathlib, time
def sh(cmd, env=None):
    if VERBOSE: print("$", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    p = subprocess.Popen(cmd, shell=isinstance(cmd, str), env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    last = 0.0
    for line in p.stdout:
        if VERBOSE and (time.time() - last > 0.2 or "rror" in line):
            print("  " + line.rstrip()[:240], flush=True); last = time.time()
    if p.wait(): raise RuntimeError(f"exit {p.returncode}: {cmd}")

env = dict(os.environ)
try:
    from google.colab import userdata
    tok = userdata.get("GITHUB_TOKEN")
except Exception:
    tok = os.environ.get("GITHUB_TOKEN")
if tok:  # header scoped to this repo; never in the URL
    env.update(GIT_CONFIG_COUNT="1",
               GIT_CONFIG_KEY_0=f"http.https://github.com/{REPO}.extraheader",
               GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{tok}".encode()).decode())
root = pathlib.Path("/content/x3d.nVidia") if pathlib.Path("/content").exists() else pathlib.Path("x3d.nVidia").resolve()
if not (root / ".git").exists():
    sh(["git", "clone", "--depth", "1", "-b", REF, f"https://github.com/{REPO}", str(root)], env=env)
else:
    sh(["git", "-C", str(root), "pull", "--ff-only"], env=env)
sh([sys.executable, "-m", "pip", "install", "-q", "-e", f"{root}[dev]"])
sys.path.insert(0, str(root / "src")); os.chdir(root)
print("x3d.nVidia at", subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip())
'''

probe = [
    md("""
# 00 · NVIDIA Probe: what the build.nvidia.com key reaches, for X3D

Turns ATLAS §2 into receipts: the catalog, X3D-writing scores per model, whether USD Code knows the OpenUSD 26.03 splat schema, and (opt-in) TRELLIS image → glb.
**Key:** Colab Secret `NVIDIA_API_KEY` (or a hidden prompt). Receipts store only its sha256 prefix. **Budget:** ~6–10 requests; TRELLIS spends credit.
"""),
    code(OPTIONS + '''
RUN_CHAT    = True
RUN_TRELLIS = False          # spends credit: image -> glb
RPM         = 36             # x3d.lab shares this key: lower it if the Duel is running
'''),
    code(SETUP),
    code('''
# ── Probe (streams as it goes) ──
import json
from x3dnv import probe
args = ["--out", "receipts", "--rpm", str(RPM)]
if not RUN_CHAT: args.append("--skip-chat")
if RUN_TRELLIS: args += ["--trellis", "docs/img/trellis_input.png"]
rec = probe.main(args)
'''),
    code('''
# ── Visual: catalog groups, scores, latency ──
if VISUAL:
    import matplotlib.pyplot as plt
    cat = rec.get("catalog") or {}
    if cat.get("groups"):
        g = cat["groups"]; plt.figure(figsize=(7, 2.6))
        plt.barh(list(g), [len(v) for v in g.values()]); plt.title(f"catalog: {cat['count']} model ids"); plt.show()
        for k, v in g.items(): print(f"{k:9s}", ", ".join(v[:12]) + (" …" if len(v) > 12 else ""))
    rows = [(r["model"].split("/")[-1], r.get("check", {}).get("score"), r["seconds"]) for r in rec["x3d"]]
    if rows:
        fig, ax = plt.subplots(1, 2, figsize=(10, 2.8))
        ax[0].barh([r[0] for r in rows], [r[1] or 0 for r in rows]); ax[0].set_xlim(0, 5); ax[0].set_title("X3D triage score (0–5)")
        ax[1].barh([r[0] for r in rows], [r[2] or 0 for r in rows]); ax[1].set_title("seconds per request"); plt.tight_layout(); plt.show()
    for r in rec["usd"]:
        print(r["model"], "markers", sum((r.get("markers") or {}).values()), "/ 5", "UsdVol" if r.get("mentions_UsdVol") else "")
    if rec.get("trellis"):
        print(json.dumps(rec["trellis"], indent=1)[:2000])
'''),
    md("""
**Next:** commit `receipts/probe-*.json` in a kit and update ATLAS §2 (🔎 → ✅/❌). If TRELLIS returned a glb, open it in X_ITE with `Inline { url "trellis-….glb" }`; that's Q2's first frame.
"""),
]

rosetta = [
    md("""
# 01 · Splat Rosetta: one Gaussian splat cloud, four standards, graded by X_ITE

PLY → X3D 4.1 `GaussianSplats` · OpenUSD 26.03 `ParticleField3DGaussianSplat` · glTF `KHR_gaussian_splatting`, plus round trips, official validators, and X_ITE frames: its own PLY loader vs our native X3D vs the glb → usda → x3d chain.
GPU optional: with `USE_GPU=True` on an NVIDIA runtime, Chrome draws through ANGLE/Vulkan (needs `x3dlab.graphics.enable()` from x3d.lab, which installs the Vulkan ICD).
"""),
    code(OPTIONS + '''
PLY_URL    = "https://raw.githubusercontent.com/create3000/media/main/docs/examples/GaussianSplats/GaussianSplats/assets/models-werner_amethyst.ply"
MAX_SPLATS = 20000
USE_GPU    = False
'''),
    code(SETUP),
    code('''
# ── Node tools: X_ITE, Playwright (uses system Chrome/Chromium), gltf-validator ──
node_dir = pathlib.Path("/content/node-tools" if pathlib.Path("/content").exists() else "node-tools"); node_dir.mkdir(exist_ok=True)
sh(f"cd {node_dir} && npm init -y >/dev/null && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm i x_ite@16.8.1 playwright@1.63.0 gltf-validator")
import shutil
chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
if not chrome:
    sh(f"cd {node_dir} && npx playwright install --with-deps chromium")
    import glob; chrome = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))[-1]
os.environ["CHROME"] = chrome; print("chrome:", chrome)
if USE_GPU:
    sh([sys.executable, "-m", "pip", "install", "-q", "git+https://github.com/hagopjay/x3d.lab"], env=env)
    import x3dlab.graphics; x3dlab.graphics.enable()
'''),
    code('''
# ── Fetch the splat (data only; parsed by numpy, never executed) ──
import urllib.request
ply = pathlib.Path("work/source.ply"); ply.parent.mkdir(exist_ok=True)
if not ply.exists(): urllib.request.urlretrieve(PLY_URL, ply)
print(f"{ply}: {ply.stat().st_size:,} bytes")
'''),
    code('''
# ── Run the conformance script (streams) ──
stamp = time.strftime("%Y%m%d")
gpu = ["--gpu"] if USE_GPU else []
sh([sys.executable, "tools/rosetta_check.py", "--ply", str(ply), "--work", "work/rosetta",
    "--node-dir", str(node_dir), "--max-splats", str(MAX_SPLATS),
    "--receipt", f"receipts/rosetta-{stamp}-{'gpu' if USE_GPU else 'cpu'}.json", *gpu])
'''),
    code('''
# ── Visual: frames and the receipt ──
import json, glob
r = json.load(open(sorted(glob.glob("receipts/rosetta-*.json"))[-1]))
print(json.dumps({k: r[k] for k in ("source_stats", "subset", "files", "validators", "xite") if k in r}, indent=1)[:3000])
if VISUAL:
    from IPython.display import Image, display
    display(Image("work/rosetta/frames/sheet.png"))  # inline | native | chain
'''),
    code('''
# ── Our own galaxy (ships with the repo): render three bound Viewpoints ──
sh(f"cd {node_dir} && node {root}/tools/xite_render.mjs --xite node_modules/x_ite/dist --root {root}/scenes "
   f"--out {root}/work/galaxy --size 480 --settle 2500 --viewpoints Tilted,FaceOn,EdgeOn {'--gpu' if USE_GPU else ''} splat_galaxy.x3d")
if VISUAL:
    for v in ("Tilted", "FaceOn", "EdgeOn"): display(Image(f"work/galaxy/splat_galaxy-{v}.png"))
'''),
]

for name, cells in (("00_NVIDIA_Probe", probe), ("01_Splat_Rosetta", rosetta)):
    nb = {"cells": cells, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                       "language_info": {"name": "python"}, "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 5}
    p = ROOT / "notebooks" / f"{name}.ipynb"
    p.write_text(json.dumps(nb, indent=1) + "\n")
    print("wrote", p)
