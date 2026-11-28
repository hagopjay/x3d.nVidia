# SimReady on real assets

28 November 2026. The X3D SimReady profile was proved on 20 small scenes written for the purpose
(`../profile-crossing/`). This folder asks the harder question: what happens to real scenes that were written
for another reason, when NVIDIA's own validator judges them against NVIDIA's own asset profile?

## The result

| Measure | Count |
|---|---|
| Real scenes | 27 (the marble-machine scenes of x3d.loom `x3d.physics/physx-bridge/scenes`) |
| Of those, with at least one body that can move | 18 |
| Pass Robotics-Prop 5.0.0 as authored | **0 of 27** |
| Pass after the opt-in upgrade | **13 of 27** (13 of the 18 that can move) |
| Pass with no warning either | 6 |
| Upgraded copies that are valid X3D 4.0 (XSD) | 27 of 27 |
| x3d_mcp's profile checks agree with NVIDIA's verdict on the untouched files | 157 of 162 cells (27 scenes by 6 rules) |

Instruments: usd-validation-nvidia 1.23.0, usd-core 26.11, SimReady tiers built from
NVIDIA/simready-foundation `c3bd1d8`, Python 3.12.3, x3d_mcp `c185673`. The yardstick is NVIDIA's
**Robotics-Prop 5.0.0** profile, resolved by NVIDIA's own resolver (`simready.foundation.contracts`): it requires
47 requirements, of which 38 have a rule that can be run. The other
9 (AF.001, VM.MAT.001, VM.PS.002, VM.TEX.001, VM.TEX.003, AA.001, AA.002, HI.001, HI.003) are pages with no code and are not counted as passed.
"Pass" is NVIDIA's own rule in its package sample: no issue of severity ERROR or FAILURE on a required requirement.
Warnings are counted apart. Every number is in `../receipts/real-assets-20261128.json`, written by `../real_assets.py`.

## What it means

1. **As authored, nothing passes, and only six rules are in the way.** Every scene lacks provenance (SR.004,
   27) and a thumbnail (SR.002, 27); 26 have unlabelled shapes and materials (SL.001, SL.MAT.001);
   21 have no mesh (VG.MESH.001); 9 have nothing that moves (RB.001). All six are rules the X3D
   SimReady profile already states. No physics rule fails: the bodies, colliders, masses and joints that the X3D
   files carry satisfy the profile as written.
2. **The gap is facts, not geometry or physics.** The upgrade adds a creator, a licence, a category, a Wikidata
   code, a thumbnail and one material word per look. It changes no shape and no number in the scene.
3. **The X3D check predicts NVIDIA's verdict on real files.** Opted in by one meta element and otherwise
   untouched, each file was read by x3d_mcp's profile checks; they agree with the validator on 157 of 162
   scene-by-rule cells. The 5 disagreements are listed below, and four of them are one cause.
4. **Fourteen do not pass, and each for a stated reason.** Nine have no body that can move, so they are not
   rigid-body props and are not dressed up as one. Two are test fixtures for which no Wikidata code is honest. Three
   draw with looks that have no name the facts file can label.

## Every scene

| Scene | Moving bodies | Required rules failing as authored | After the upgrade | Warnings after | Kind (Wikidata label) |
|---|---|---|---|---|---|
| `demos/dominoes-spiral.x3d` | 134 | 5 | **passes** | none | domino toppling |
| `demos/galton-board.x3d` | 240 | 5 | **passes** | VG.MESH.001 | bean machine |
| `demos/musicbox-twinkle.x3d` | 10 | 5 | **passes** | VG.MESH.001 | music box |
| `demos/trebuchet-keep.x3d` | 135 | 5 | **passes** | VG.MESH.001 | trebuchet |
| `experiments/machine-with-sound.x3d` | 65 | 4 | **passes** | VG.MESH.001 | marble run |
| `experiments/marble-minimal-friction2-zero.x3d` | 1 | 5 | fails SL.001, SL.MAT.001 | VG.MESH.001 | inclined plane |
| `experiments/ode-only-fields.x3d` | 1 | 5 | fails SL.001, SL.MAT.001, SR.004 | none | none given |
| `experiments/race-ghost.x3d` | 65 | 4 | fails SL.001, SL.MAT.001 | VG.MESH.001 | marble run |
| `experiments/race-main.x3d` | 65 | 4 | **passes** | VG.MESH.001 | marble run |
| `joints-and-sensors.x3d` | 10 | 5 | fails SL.001, SL.MAT.001, SR.004 | VG.MESH.001 | none given |
| `marble-machine-build.x3d` | 0 | 4 | fails RB.001, SR.004, VG.MESH.001 | none | marble run |
| `marble-machine.x3d` | 65 | 4 | **passes** | VG.MESH.001 | marble run |
| `marble-minimal.x3d` | 1 | 5 | fails SL.001, SL.MAT.001 | VG.MESH.001 | inclined plane |
| `pieces/bell.x3d` | 0 | 6 | fails RB.001, SR.004, VG.MESH.001 | none | bell |
| `pieces/curve.x3d` | 0 | 5 | fails RB.001, SR.004 | none | chute |
| `pieces/dominoes.x3d` | 10 | 5 | **passes** | none | domino toppling |
| `pieces/elevator.x3d` | 0 | 6 | fails RB.001, SR.004 | none | elevator |
| `pieces/flipper.x3d` | 1 | 5 | **passes** | none | lever |
| `pieces/funnel.x3d` | 0 | 6 | fails RB.001, SR.004 | none | funnel |
| `pieces/halfpipe.x3d` | 0 | 5 | fails RB.001, SR.004 | none | half-pipe |
| `pieces/launcher.x3d` | 1 | 5 | **passes** | none | catapult |
| `pieces/pendulum.x3d` | 1 | 5 | **passes** | VG.MESH.001 | pendulum |
| `pieces/ramp.x3d` | 0 | 6 | fails RB.001, SR.004 | none | inclined plane |
| `pieces/seesaw.x3d` | 1 | 5 | **passes** | none | seesaw |
| `pieces/wheel.x3d` | 1 | 5 | **passes** | none | paddle wheel |
| `pieces/xylophone.x3d` | 0 | 6 | fails RB.001, SR.004 | none | xylophone |
| `pieces/zigzag.x3d` | 0 | 6 | fails RB.001, SR.004 | none | chute |

The warning on eleven passing scenes is VG.MESH.001's second half: the stage has meshes, and also spheres or
cylinders. They are left as they are on purpose. A faceted marble does not roll like a marble.

## Where the X3D check and NVIDIA's validator disagree

| Scene | Rule | NVIDIA's validator on the USD | x3d_mcp on the X3D |
|---|---|---|---|
| `experiments/ode-only-fields.x3d` | SL.MAT.001 | fail | silent |
| `marble-machine-build.x3d` | SL.001 | pass | reports |
| `marble-machine-build.x3d` | SL.MAT.001 | pass | reports |
| `pieces/curve.x3d` | VG.MESH.001 | pass | reports |
| `pieces/halfpipe.x3d` | VG.MESH.001 | pass | reports |

Four of the five are one cause: the writer puts into USD only what takes part in physics, so a shape that is only
drawn (or a whole scene that is only drawn, `marble-machine-build.x3d`) is judged by x3d_mcp and never reaches the
validator. The fifth is an x3d_mcp gap: a Shape with no Appearance has no look to hang a complaint on, so the
missing material label goes unreported, while the writer gives it a default material that the validator then fails.
The same cause shows after the upgrade: x3d_mcp still reports unlabelled drawn-only shapes (a guide line named
`LoomLine`) on scenes the validator passes.

## What the real files taught

- **Rewriting a Box as a mesh in the X3D breaks the scene in X_ITE.** The first upgrader turned every Box into an
  IndexedFaceSet of the same corners. In X_ITE 16.8.0 (headless Chromium 158.0.8127.36, SwiftShader) the ten
  dominoes of `pieces/dominoes.x3d` were gone from view 2.5 seconds after load; with Boxes they stand (grade C that
  they vanish, L that X_ITE's physics does not hold a moving mesh collider). So the X3D keeps its Boxes, and the
  writer emits each Box as its exact twelve-triangle mesh (`box_as_mesh`, 783 boxes here). The X3D
  profile check `simready-geometry-not-mesh` still warns on those files; a Box should count as a mesh there. That
  is a change to the profile draft, not made here.
- **Two USD files in one folder fail NP.005.** The harness's first layout put the authored and the upgraded USD
  side by side and every scene failed "exactly one USD file". One folder per asset.
- **An authored Viewpoint is not a thumbnail camera.** The single-piece scenes frame a whole board, and the piece
  was 130 pixels of 65,536. X_ITE's `viewAll` made it worse (most frames came back empty). The thumbnails are
  rendered at 1024, cropped to what is drawn, and scaled to 256 (`thumbnails.mjs`).

## The facts, and who vouches for them

`facts.json` holds every fact the upgrade adds, each with its source and a grade. The licence is read from the
repository (C). The creator is the repository's owner (L). Ten material words are the author's own names (wood,
steel, brass and so on, C); the rest are read from the generator's sound table or its PBR values (L) or are the
editor's suggestion (S: the dominoes as plastic, the Galton beads as glass). The 17 Wikidata codes were each
matched by exact English label through QLever on 28 November 2026 (C that the code carries the label, L that it is
the right class). **Everything graded L or S is waiting for the owner's review.** Change a value and rerun.

## What this does not show

One corpus by one generator: 27 scenes that share their materials and their style. Nine required requirements have
no executable rule. No engine was run: passing the validator says the asset is well formed, not that it simulates
well in PhysX, Newton or MuJoCo. The upgraded copies were loaded in X_ITE 16.8.0 (27 of 27 load; one logs a missing sound
file that the original also lacks). At 2.5 seconds 25 of 27 draw within 5% of the original's pixel count; the two
that differ, the flipper and the pendulum, are single moving parts caught at another point of their swing (L: not
compared frame by frame).

## Attribution

The 27 scenes and their upgraded copies in `upgraded/` are from
[hagopjay/x3d.loom, x3d.physics/physx-bridge](https://github.com/hagopjay/x3d.loom/tree/main/x3d.physics/physx-bridge),
Apache License 2.0; each copy names its source file and sha256 in `<meta name="simready:source">`. Class codes are
from [Wikidata](https://www.wikidata.org/) (CC0), queried through [QLever](https://qlever.dev/). The profile and
rules are NVIDIA's [simready-foundation](https://github.com/NVIDIA/simready-foundation) at `c3bd1d8`. If anything
here is yours and should not be, open an issue on this repository and it will be taken down promptly.

## Rerun

```
node q12/real-assets/thumbnails.mjs X_ITE_DIR SCENES_DIR THUMBS_DIR
python -I q12/real_assets.py X3D_MCP_DIR SIMREADY_TIERS_DIR SCENES_DIR THUMBS_DIR q12/real-assets/facts.json OUT_DIR RECEIPT.json
pytest tests/test_simready_upgrade.py
```
