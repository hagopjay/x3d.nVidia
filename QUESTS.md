# QUESTS — fun, provable ways to show X3D's power on NVIDIA

Ranked by advocacy value ÷ cost on today's **free dev key (40 rpm)** and Colab GPUs. Each quest ends in receipts and something people can *open in a browser*. Claim one by adding your session name in **Owner**. One owner per quest.

| # | Quest | NVIDIA surface | Cost | Status | Owner |
|---|---|---|---|---|---|
| Q0 | **Splat Rosetta**: one cloud through PLY / X3D 4.1 / USD 26.03 / glTF KHR, graded by X_ITE | standards + 3DGRUT/gsplat ecosystem | CPU | ✅ v0.1 (X_ITE frame, 4 formats, validators) | founding thread |
| Q1 | **Probe the catalog**: model list, X3D-writing scores, USD Code vs the splat schema, TRELLIS response shape | NIM chat + genai | ~10 req | ⏳ needs the key | keyed agent |
| Q2 | **Words → X3D world**: text → (SANA/FLUX image) → TRELLIS glb → X3D scene with Viewpoints, sensors, ROUTEs, opened in X_ITE | TRELLIS NIM | ~3 req/asset | ⏳ | |
| Q3 | **GEPA writes X3D**: DSPy program `brief → X3D`, metric = x3d_mcp validator + X_ITE render-non-empty; optimise on Nemotron 3 Super | NIM chat, DSPy 3.3 | ~150–400 req (hours at 36 rpm) | ⏳ | |
| Q4 | **One photo → interactive splat world**: Lyra (or gsplat training) → PLY → X3D `GaussianSplats` + TouchSensor hotspots + Viewpoint tour | Lyra/gsplat on Colab A100 | GPU hours | ⏳ | |
| Q5 | **Omniverse as an engine in the fidelity chain**: `ovrtx` renders the same scene x3d.lab sends to X_ITE / Unreal / x3d.wgpu; Δ per pixel | ovrtx (early access) | GPU | ⏳ (check ovrtx install on Colab) | |
| Q6 | **Splats in Omniverse vs X_ITE**: our `.usda` vs `omni.kit.converter.gsplat`'s, rendered by RTX and X_ITE, same camera | Kit 110.2+ / hdParticleField | GPU | ⏳ ATLAS §7 Q3–Q4 | |
| Q7 | **VLM juror**: Cosmos 3 / Nemotron 3.5 VL grades engine frames ("is the red box lit from the left?") as a second opinion to pixel deltas | NIM VLM | ~1 req/frame | ⏳ | |
| Q8 | **Perceptual distance**: V-JEPA 2 embeddings of animated X3D clips across engines; does it rank fidelity like humans/Δ? | HF + CUDA | GPU | ⏳ | |
| Q9 | **Warp physics → X3D**: simulate an X3D RigidBodyCollection or ParticleSystem in Warp, bake to interpolators, compare with X_ITE's own physics | Warp | GPU minutes | ⏳ | |
| Q10 | **Objaverse at scale**: licence-filtered (CC0/CC-BY) glbs → X3D; loss histogram per node type | HF datasets | CPU/GPU | ⏳ | |
| Q11 | **Hugging Face home**: dataset `x3d-scenes` (with receipts) + a Space running X_ITE on generated worlds | HF | free | ⏳ | |
| Q12 | **SimReady before export** (STRATEGY M1): X3D → Blender 5.x → USD through the Omniverse Asset Validator and a SimReady profile; plus an X3D SimReady metadata profile checked by x3d_mcp | omniverse-asset-validator, SimReady Foundation. **First run done 26 Nov** (x3d_mcp #33, Blender 5.3.0, usd-core 26.11, Validator 1.18.0): 84 scenes, 27 mapped rules; 17 X3D-only pairs where Blender's importer repaired the fault. Open: real files, SimReady requirement rules | CPU | ⏳ (turn 3 is the X3D half ✅) | |
| Q13 | **Newton as a physics witness** (M3): one x3d.physics scene in Newton, PhysX and X_ITE; disagreements shrunk to tests | Newton 1.0 (Warp, pip) | Colab GPU | ⏳ | |
| Q14 | **Behaviour pack for AOUSD CMI** (M2): X3D event semantics ⟷ USD mapping and a conformance pack with X_ITE traces | AOUSD (standards) | CPU | ⏳ | |
| Q15 | **H-Anim → humanoid** (M3): retarget an H-Anim motion to an Isaac humanoid via URDF/MJCF; joint-error receipt | Isaac Sim 6 importers, GR00T assets | GPU | ⏳ | |
| Q16 | **MCP to MCP**: an agent builds and validates an X3D prop with x3d_mcp, exports it, and Isaac Sim MCP drops it into a scene | Isaac Sim 6 MCP, Nemotron | GPU + key | ⏳ | |

See STRATEGY.md for why Q12 to Q16 are the strategic spine.

## Why these and in this order
- **Q0–Q1 build trust.** They are standards-level proofs and catalog facts that NVIDIA's own engineers can check in five minutes.
- **Q2–Q4 are the demos.** Each turns an NVIDIA generator's output into something *interactive* in any browser, which is the one thing glb and USD viewers don't give you for free.
- **Q5–Q8 make NVIDIA tech part of the x3d.lab grading flywheel**, as more engines and more judges.
- **Q3 is the cheapest high-value use of a rate-limited key.** It is slow, not costly.

## The upgrade case (for a better key or NVIDIA programs)
A better key is worth asking for once Q1, Q2 and one of Q3/Q4 have receipts. Then the ask is concrete: "N requests per day produce M validated X3D worlds; here are the links." Write it from the receipts and keep claims to what was measured.
