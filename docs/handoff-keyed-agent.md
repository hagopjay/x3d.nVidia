# Handoff to the session that holds the NVIDIA key

You hold the build.nvidia.com developer key. This repo does not, by design. Your first job is **Q1: probe the catalog** and turn ATLAS §2's 🔎 rows into ✅ or ❌.

## Run (Colab, CPU runtime is enough)
Open `notebooks/00_NVIDIA_Probe.ipynb`. It reads `NVIDIA_API_KEY` from Colab Secrets (or a hidden prompt) and `GITHUB_TOKEN` if the repo is private. Or, in any shell with the key in the environment:

```bash
pip install -e .            # from a clone of hagopjay/x3d.nVidia
python -m x3dnv.probe --out receipts/                     # ~6–10 requests
python -m x3dnv.probe --out receipts/ --skip-chat --trellis docs/img/trellis_input.png   # spends TRELLIS credit
```

The probe paces to 36 rpm (set `X3DNV_NVIDIA_RPM` lower if x3d.lab's Duel is running on the same key).

## What to report back (commit the receipt; update ATLAS)
1. `catalog.count` and `catalog.groups` (3d / usd / world / vlm / nemotron / embed). Paste the groups into ATLAS §2.
2. For each model, the `x3d[*].check.score` (0–5) and `usd[*].markers`. **Does USD Code know `ParticleField3DGaussianSplat`?**
3. TRELLIS: `trellis.status`, `trellis.response` (already redacted), and whether a glb came back. If the image encoding is refused, the error text tells us the right one; fix `NIM.trellis` in a kit.
4. Rate-limit headers seen (`x-ratelimit-*`), if any.

## Then
- Q2 (Words → X3D world) is yours if TRELLIS works: glb → X3D via the x3d-blender-io add-on or a plain `Inline url "asset.glb"` in X_ITE, plus Viewpoints and a TouchSensor.
- Q3 (GEPA writes X3D) needs only chat and patience. Claim it in QUESTS.md before starting.
