# STRATEGY — how X3D wins on NVIDIA's ground

*26 Nov 2026. Facts carry their source and date in ATLAS.md; this file is the plan built on them. Owner: Jason (hagopjay). Revisit after each flywheel turn.*

## 1. The position in one paragraph

NVIDIA owns:
- **the compute:** CUDA, RTX, DGX;
- **the simulators:** Isaac Sim and Lab, Newton, PhysX, Omniverse;
- **the world models:** Cosmos, GR00T;
- **the data layer it builds on:** OpenUSD, plus its own rulebook for "simulation-ready", SimReady.

We do not compete with any of that. **We become the layer NVIDIA's stack does not have and keeps needing.** That layer is a standard, web-native, behaviour-carrying scene language whose files an AI can be held accountable for. ISO X3D, with the Loom's flywheel, is that layer today, and we can prove it with receipts.

## 2. Where USD is thin (and X3D is not)

| Gap in the USD/NVIDIA stack | Evidence | X3D's answer, already working |
|---|---|---|
| **Value-level validation.** USD's registered validators mostly police composition, not data | Fault Court (x3d.loom, 26 Nov): on 39 shared planted faults, USD's own checkers caught 5, X3D's 26 at turn 1 and more after; turn 3 maps all 340 OpenUSD, Omniverse Asset Validator and SimReady rules | x3d_mcp answers every one of the 66 rules X3D can state, each backed by an executed pair; 32 more are impossible to break in X3D. This includes SimReady's geometry and physics checks |
| **Interactivity and behaviour.** AOUSD formed the Characters, Motion and Interactivity interest group in March 2026 to *start* standardizing interactive behaviour | AOUSD press, 25 Mar 2026 | X3D has had sensors, ROUTEs, interpolators, scripts and humanoids (H-Anim, ISO 19774) as an ISO standard for over 20 years, plus a behaviour simulator judged event by event against X_ITE (x3d.loom behaviour-graph) |
| **The web.** OpenUSD 26.03 added WebAssembly builds; Omniverse streams pixels over WebRTC | AOUSD, Mar 2026; Isaac Sim 6.2 web-viewer skill | X_ITE runs any X3D world, behaviour included, in any page; one file, no server |
| **Accountable AI authoring** | NVIDIA's own agent push: Isaac Sim 6.0 ships an MCP server and agent skills; Omniverse libraries are part of the Agent Toolkit | x3d_mcp (about 50 tools, hash-chained claims ledger) plus the Loom (C/L/S grades, receipts, failure modes) |
| **Splats with behaviour** | glTF and USD now store 3D Gaussian splats; neither has sensors or ROUTEs | X3D 4.1 `GaussianSplats`, bit-equal to both (Splat Rosetta, X_ITE within 1/255) |

## 3. The moves, ranked

Each move ends in receipts and a page someone can open.

### M1. SimReady before export (the wedge)
**What.** An X3D scene that passes x3d_mcp's checks exports through Blender 5.x to a USD file that passes NVIDIA's own rulebooks: the Omniverse Asset Validator and a SimReady profile such as *Prop Robotics Neutral*. Measure it end to end.
**Why it wins.** It turns "X3D validation subsumes USD's" (turn 3, on paper and fixtures) into "X3D-authored assets arrive SimReady". That is a production claim NVIDIA's partners can use.
**Steps.**
1. Foundry: add the three rulebooks to its USD leg (`omniverse-asset-validator` on Python 3.12).
2. Write an **X3D SimReady profile**: metadata conventions for semantic labels, physics material, mass, facing and thumbnails, checked by x3d_mcp. That moves the 92 "policy" rows toward covered.
3. Run the x3d.demo corpus through it.

**Receipt.** Pass rate per SimReady requirement, X3D in vs USD out.

### M2. Behaviour is the gap: lead the interactivity conversation
**What.** A mapping of X3D's event model to what USD has (OmniGraph, UsdSkel, animation) and lacks, with the behaviour simulator's event-by-event test suite as reference semantics.
**Why it wins.** AOUSD CMI is defining interactivity now. Arriving with 20-plus years of ISO semantics and a *test suite* (not a slide deck) makes X3D the reference rather than a bystander.
**Steps.**
1. A doc: X3D behaviour ⟷ USD, row by row, graded.
2. A conformance pack: scenes plus expected event traces from X_ITE.
3. Offer both to Web3D (Dr Polys) and to the AOUSD CMI interest group.

**Receipt.** The pack runs in X_ITE and in the Blender behaviour simulator, with matching traces.

### M3. Robots: X3D physics and humanoids as a conformance flywheel
**What.** Add **Newton** (Linux Foundation, Apache-2.0, Warp plus OpenUSD; 1.0 GA at GTC 2026) as one more engine in x3d.physics, beside PhysX and X_ITE's own. One X3D RigidBodyPhysics scene, three engines, disagreements shrunk to tests. Then map H-Anim joints to humanoid robots (Isaac's humanoid assets, the GR00T family) through URDF/MJCF: Isaac Sim 6's importers 3.0 convert between both and USD.
**Why it wins.**
- Newton is pip-installable and runs on Colab GPUs, so we can be first to grade it with an independent standard.
- H-Anim is the only ISO humanoid skeleton standard. Robot learning increasingly retargets human motion to humanoid robots, and H-Anim is where human motion data lives in a standard.

**Receipts.** A physics ledger row per engine. An H-Anim → humanoid retarget scored by joint error.

### M4. ML/AI beyond token spend
| Play | NVIDIA surface | X3D advantage | First receipt |
|---|---|---|---|
| **Labelled synthetic data** | Replicator, Cosmos Transfer 2.5, Physical AI Data Factory | Ground truth comes free: every X3D node carries type, DEF and metadata, so semantic labels are exact, not guessed | 1,000 rendered frames with per-pixel labels from X3D metadata |
| **Judges for world models** | Cosmos 3 (VLM), Nemotron 3.5 VL; V-JEPA 2 on HF | X3D scenes give ground-truth physics and events to test whether a world model "understands" | A small benchmark: rendered X3D clip, question, the answer X3D knows |
| **Generative worlds made interactive** | TRELLIS (NIM), Lyra, 3DGRUT | Generators output glb/ply; X3D wraps them with Viewpoints, sensors and physics | Q2 and Q4 in QUESTS.md |
| **Agents that author and simulate** | Isaac Sim MCP, agent skills; Nemotron | x3d_mcp authors and validates; Isaac Sim MCP simulates; two MCP servers, one loop | Q16: an agent builds an X3D prop, validates it, exports it, and Isaac Sim drops it |
| **Prompt and program optimisation** | NIM chat (Nemotron), DSPy GEPA | The x3d_mcp validator is a free, exact metric | Q3 (budget: about 5k reasoning tokens per answer; try `--no-think`) |

### M5. The web front door for Omniverse content
USD → (Blender) → X3D → X_ITE gives any USD asset an interactive, linkable web page with no streaming server. We measure fidelity both ways with the reverse trip (glTF samples already done; USD next).

## 4. What we do not do

- **Claim X3D replaces USD.** USD is NVIDIA's composition layer and it is good at it. Our claim is narrower and provable: X3D says more, checks more of what it says, and runs on the web.
- **Spend the NVIDIA key in production, or multiply keys to dodge limits.** The trial terms are for development (AGENTS.md, "Staying in good standing").
- **Report a number without its instrument,** or a fixture result as a real-world result (FM 324, 325, 352).

## 5. Scoreboard (each a row in a ledger)

| Measure | Now (26 Nov) | Next |
|---|---|---|
| USD rules X3D can state, reported | 66 of 66 (turn 3) | Hold at 100% as rulebooks update; re-pin monthly |
| SimReady requirements passed by an X3D → Blender → USD export | not measured | M1 |
| Engines in the physics flywheel | PhysX bridge, X_ITE | + Newton (M3) |
| Behaviour conformance scenes with X_ITE traces | simulator judged on sensors, timers, interpolators (loom) | a packaged CMI pack (M2) |
| Catalog facts probed with the key | 2 models, X3D 5/5, USD reasoning budget measured | full catalog, TRELLIS (Q1, Q2) |
| Turns without a person | 0 | 1 (needs a spend cap) |

## 6. Next 30 days

1. **Merge the turn-3 kits** (x3d_mcp, x3d.loom, x3d.docs, this repo).
2. **M1 step 1:** the Foundry runs the three USD rulebooks on its Blender USD exports. The request is in the coordination doc.
3. **M3 step 1:** `pip install newton` on Colab; run one x3d.physics scene; write the first physics-ledger row with Newton.
4. **Q2:** TRELLIS glb → X3D world with sensors, on the free key.
5. **M2 step 1:** the X3D ⟷ USD behaviour mapping doc. Draft it, grade it, send it to Dr Polys first.
