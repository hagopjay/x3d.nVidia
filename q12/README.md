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

## Runtime variants in the writer (`--runtimes physx,newton,mujoco`), 26 Nov 2026

SimReady's isolation matrix (RV.010, RV.011) forbids engine schemas in the neutral stage and Mjc* under Newton (and the
reverse), so the writer puts each engine's schemas in `runnables/physics/<engine>.usda` behind a variant set named after it
(`PhysX`, `Newton`, `MuJoCo`; Disabled by default; `SimReady_Metadata.Variants.Physics` documents each). Neutral extras: one
`PhysicsArticulationRootAPI` per joint graph, on its first dynamic body. Per engine, by schema name:

| Payload | Carries |
|---|---|
| `physx` | passive `PhysicsDriveAPI` (stiffness 0, damping 0, force limit FLT_MAX) and `PhysicsJointStateAPI` per joint axis (a ball joint gets rotX/Y/Z) |
| `newton` | `NewtonCollisionAPI`; `NewtonMeshCollisionAPI` on dynamic meshes, `NewtonSDFCollisionAPI` on static concave ones; `NewtonMaterialAPI`; `NewtonArticulationRootAPI` with `newton:selfCollisionEnabled` false; the passive drives |
| `mujoco` | `MjcCollisionAPI`; `MjcMeshCollisionAPI` on dynamic meshes; `MjcJointAPI` on non-fixed joints |

`q12/writer_runtimes.py` reproduces the table below (Python 3.12, usd-validation-nvidia 1.23.0 + tiers c3bd1d8, usd-core 26.11,
omniverse-asset-validator 1.18.0; 21 PhysX-bridge scenes; receipt `receipts/writer-runtimes-20261126.json`). Scenes failing a requirement:

| Requirement | Neutral writer | Its own target composition | |
|---|---|---|---|
| RV.001, RV.004, RV.007 (variant sets) | 21 | 0 (default asset; RV.001-RV.011 all 0) | flipped |
| DJ.002 joint state, DJ.004 drive (PhysX) | 8, 8 | 0, 0 | flipped |
| NEWTON.DJ.001 drive, NEWTON.COL.001 mesh API | 8, 3 | 0, 0 | flipped |
| MUJOCO.COL.001 collider API, MUJOCO.DJ.001 joint API | 21, 8 | 0, 0 | flipped |
| BA.001 articulation root | 8 | 2 | the 2 have two joint graphs; the rule wants exactly one root per stage |
| NEWTON.BA.001 | 21 | 15 | the 15 have no joints, and the rule still wants a root |
| MUJOCO.COL.002 convex hull | 0 | 3 | **refused**: a hull of the static curve, half-pipe and marble-machine pipe would fill the bowl |
| MUJOCO.DJ.002 actuator | 0 | 8 | **rule tension**: DJ.001 wants MjcJointAPI on every joint, DJ.002 then wants an MjcActuator; a passive pendulum has none (Suspected rule gap; a zero-gain actuator would pass it by inventing one) |
| COL.001 (sdf, PhysX) | 3 | 3 | not applied: PhysX's reference runs use the triangle mesh (9/9) |
| DJ.011 | 1 | 1 | a true property of one scene (two hinges between one body pair) |

So 9 requirement codes flip to 0, 2 improve, and 2 new conflicts surface: the "14" in the earlier note was an estimate (Suspected);
the measured figure is 9 fully flipped. SimReady's rules are not gated by runtime, so a MuJoCo rule fails while Newton is selected: read
each runtime on its own composition (`writer_runtimes.py` flattens one per runtime).
All 70 usd-core and Omniverse rules pass on the `.usdc` form of the three mesh scenes; the ASCII `.usda` form trips
`UsdAsciiPerformanceChecker` on those three (also in the neutral writer): write `.usdc` for assets that carry meshes.

**Does Newton use the roots? No (Confirmed, Newton 1.8.0 CPU, `newton/repros/`).** With the writer's roots, `add_usd` still leaves the joint
outside any articulation (`joint_articulation == [-1]`), because the jointed body's partner is a static Xform and not a rigid body.
`x3dnv.newton_run` keeps wrapping those joints itself. Runs of pendulum, seesaw and wheel under XPBD and MuJoCo are bit-identical
with and without `--runtimes` (max |dq| 0.0 over 480 steps).

## The X3D SimReady profile, crossed (`profile_crossing.py`), 27 Nov 2026

```bash
python3 -I q12/profile_crossing.py X3D_MCP q12/profile-crossing q12/receipts/profile-crossing-20261127.json
```

x3d_mcp #40 adds an opt-in SimReady profile: 20 SimReady rules that plain X3D leaves open, each with a failing and a passing
proof scene. This script writes every pair to USD with `x3d2usdphysics` and runs the named SimReady requirement on both
(usd-validation-nvidia 1.23.0, tiers c3bd1d8, usd-core 26.11, Python 3.12). **19 of 20 confirmed both ways, 1 X3D-only (VG.021
has no executable rule), 0 mismatched; 2 more pairs confirm the warning side of VG.MESH.001 and CITY.001.** The ledger reads 66 rules stated by plain X3D plus 20 under the profile, 86 of 340.
Table, grammar and caveats: `docs/SIMREADY-X3D-PROFILE.md`. Scenes and USD files: `q12/profile-crossing/<pair>/failing|passing/`.

The writer learned three things for this, all "carry it as written": `<unit category='length'>` becomes `metersPerUnit`
(before, a centimetre scene was written as metres: Confirmed defect, fixed here), a `semantics:labels` MetadataSet becomes
`SemanticsLabelsAPI`, and `<meta name='Image'>` becomes the SimReady thumbnail.
