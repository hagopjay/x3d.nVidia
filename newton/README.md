# Q13: Newton as the second physics check

X3D RigidBodyPhysics goes into Newton 1.8 (Linux Foundation; Warp and OpenUSD) through OpenUSD, along this path:

1. `src/x3dnv/x3d2usdphysics.py` writes the scene as UsdPhysics (Z up, SimReady provenance).
2. `newton.ModelBuilder.add_usd` loads it.
3. Newton steps it at the X3D bridges' fixed 1/240 s.

Everything here ran on the CPU (`warp-lang` 1.19.0, device `cpu`).

| File | What |
|---|---|
| `src/x3dnv/newton_run.py` | Load and step, with a hash of every step's state. It works around two gaps in Newton's importer, below |
| `src/x3dnv/newton_refs.py` | The PhysX bridge's nine exact references and three negative controls, each authored as an X3D scene |
| `tools/newton_showcase.py` | Simulates a scene for a render or a replay (`--stage` replays the recorded stage byte for byte; `--push` and `--tip` are the viewer's touch) |
| `tools/newton_record.py` | Writes a `loom.physics-run/1` record for x3d.loom's physics witness |
| `tools/render_newton.py` | Renders the UsdPhysics stage in Blender 5.3 Cycles from Newton's trajectory |
| `tools/domino_wave.py` | Toppling-wave speed in v/√(gH), as in the PhysX bridge's study |
| `stages/dominoes-spiral.usda` | The stage both run records were recorded and replayed on |
| `runs/newton-{xpbd,mujoco}-dominoes-spiral.physics.json` | The run records |
| `refs/` | The reference results, the substep sweep and the wave speeds |

## Results, 26 Nov 2026

| Reference (PhysX limit) | PhysX 5.12 | Newton XPBD | Newton MuJoCo 4.0.1 (CPU) |
|---|---|---|---|
| Free fall: height, velocity, gap | pass | pass, identical to PhysX | pass |
| Pendulum, ball and hinge (0.5 %) | pass | **14.5 %** at one step (converges: 3.7, 0.96, 0.17 % at 2, 4, 10 substeps) | pass, 0.014 % |
| Restitution e(v+gh) (1e-3) | pass | pass, 1.6e-7 | **misses**: effective e 0.14 against 0.6 (Likely, restitution is not carried into MuJoCo) |
| Incline, μ 0.3 slides (2 %) | pass | pass | pass |
| Incline, μ 0.7 holds (1 mm) | pass | **4.5 mm** creep | **3.5 mm** creep |
| Tunnelling at 5 m/s (0 of 40) | pass | pass | **40 of 40** |

- **Determinism.** The 134-domino spiral (1,680 steps) replays with 0 mismatched step hashes in fresh processes on CPython 3.13 and 3.12, for both solvers.
- **The witness.** x3d.loom's physics witness passes both records on schema, trace, replays, controls and losses. Each record then stops at `PHYS_REFERENCE_FAIL` on its three misses, as it should.
- **Wave speed.** Under the same tip, MuJoCo's wave runs at 1.23–1.31 √(gH), inside the PhysX bridge's μ 0.2 range of 1.05–1.46. XPBD's runs at 1.54–2.31, faster than real dominoes (peak 1.53). The PhysX range comes from straight runs, so the comparison is Likely.
- **Two gaps in Newton 1.8's USD importer (measured).**
  - `add_usd` makes no collision filter pair from `FilteredPairsAPI`, nor from a joint with collisionEnabled false, when one side is a static collider. A pendulum's bob then collides with its own pivot, gains energy, and under XPBD blows up.
  - A joint with no ArticulationRootAPI belongs to no articulation, so MuJoCo integrates its angle but no body moves.

  `build()` applies the declared pairs itself and wraps such joints into articulations.

**Not shown:** a GPU, another machine, or Isaac Sim.
