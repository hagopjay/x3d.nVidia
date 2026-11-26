# Q12 run 2: X3D → Blender 5.3 → USD, judged by three executed rulebooks and joined with x3d_mcp

This builds on the first run, x3d_mcp #33 (`tests/usd_q12/`): it uses the same classes and reads the same MAP. It adds four things:

1. **SimReady executed.** #33 recorded the SimReady requirements as "not executable". They are executable: `usd-validation-nvidia` 1.23.0, together with the five tiers built from `NVIDIA/simready-foundation` c3bd1d8 (core, newton, isaac, aif, sensors), registers 216 rules covering 203 requirement codes. 165 of the 270 pinned requirements have a rule. `run_simready.py` runs every rule and reads each issue's requirement code. A requirement whose only issues say "not evaluated", or report a rule's own crash ("Uncaught error"), is recorded as not run, never as a failure.
2. **Real files.** `x3d_views.py` runs x3d_mcp over 1,503 files. From those, up to 8 files are picked for each mapped X3D check, in sha256 order, plus 50 clean controls: 141 files in all. The real files are imported where they sit, so their Inlines and textures resolve.
3. **Both orientations.** Every scene is exported twice: Z up (Blender's own, as the Foundry writes it) and Y up (converted). SimReady's up-axis rule then has a negative control.
4. **Fired pairs (loom FM 373).** Agreement is reported only on pairs where either side fires. Every USD failure that no X3D check covers carries MAP's status for its rule.

## Run

```bash
python3 -I q12/x3d_views.py X3D_MCP views.json DIR...                 # Python with lxml (x3d_mcp's)
python3 -I q12/export_blender.py SCENES_DIR|corpus.json OUT ADDON/source export.json   # Python 3.13 + bpy==5.3.0
python3 -I q12/run_rulebooks.py OUT X3D_MCP/tests/usd_rules.json rb.json   # Python 3.12: usd-core 26.11, OAV 1.18.0
python3 -I q12/run_simready.py  OUT X3D_MCP/tests/usd_rules.json sr.json   # usd-validation-nvidia 1.23.0 + tiers
python3 -I q12/join.py X3D_MCP join.json --parity SCENES export.json rb.json sr.json \
                                         --real views.json corpus.json export-real.json rb-real.json sr-real.json
```

## Results, 26 Nov 2026 (receipts in `receipts/`, raw verdicts gzipped)

| Corpus | Fired pairs | Both | X3D only | USD only |
|---|---|---|---|---|
| Parity fixtures, 84 scenes | 67 | 17 | 32 | 18 |
| Real files, 141 | 359 | 140 | 117 | 102 |

The run executed 48 mapped rules: 7 usd-core, 20 Omniverse and 21 SimReady (#33: 27). The 102 USD-only pairs on real files break down as follows:

| Pairs | Cause | Status |
|---|---|---|
| 38 | PointSet and LineSet exported as `UsdGeom.Mesh` with 0 faces | Export-made, confirmed |
| 32 | Non-manifold vertices | Likely export-made: `fall.x3d` has 0 bow-tie vertices in the X3D and 668 after export |
| 18 | Identical shapes in one world place under different Transforms | x3d_mcp gap, confirmed on d3-bridge `scatter.x3d`; fixed on x3d_mcp branch `q12-coincident-world` |
| 6 | PointSet normals of length 0 | Export-made |
| 6 | Unused points | Likely export-made |
| 2 | Extents | Likely export-made |

- **Up axis.** SimReady UN.006 and VG.025 pass all 225 Z-up exports and fail all 225 Y-up ones.
- **Blender drops X3D physics.** SimReady RB.001 fails on every export.
- **Add-on (parity scenes).** RigidBody collision shapes are placed at the origin, ignoring `position`, and a body that a joint USEs is imported twice.
- **Direct writer.** On the 21 PhysX-bridge scenes, the output of `src/x3dnv/x3d2usdphysics.py` passes every usd-core and Omniverse rule; Blender's exports of the same scenes fail 38 pairs. It also fixes 10 SimReady requirements: metadata, rigid bodies, coincident meshes, point-set topology and others. 14 more now apply because there is physics to judge (engine schemas, joint drives, articulation roots). Those are the writer's next work.
