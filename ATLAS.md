# ATLAS — where X3D meets NVIDIA

The reference map for this repo. Every row says what was checked, when, and how.

| Mark | Meaning |
|---|---|
| ✅ | **Measured here**, with a receipt in `receipts/` (tool, version, adapter named) |
| 🔎 | **Read from the source** (page or code) on the date given; not exercised |
| ⏳ | **Not run yet**: the value is `null` until a receipt exists |
| ❌ | Tried, and it fails (receipt says how) |

Last full pass: **26 Nov 2026**. A fact older than its last check date is a claim, not a fact. Re-check it before you build on it.

---

## 1. Gaussian splats: four standards, one cloud

The founding result. X3D 4.1, OpenUSD 26.03 and glTF `KHR_gaussian_splatting` all encode the same 3D Gaussian Splatting data the same way, and X3D is the only one of them with sensors, ROUTEs, Viewpoints and scripts around it.

### 1.1 Encoding contract (the Rosetta table)

| | 3DGS training `.ply` | **X3D 4.1 `GaussianSplats`** | **OpenUSD 26.03 `ParticleField3DGaussianSplat`** | **glTF `KHR_gaussian_splatting`** |
|---|---|---|---|---|
| Status | de-facto (Inria 2023) | 4.1 CD draft; X_ITE 16.8.1 implements | in OpenUSD 26.03 (Mar 2026) | **ratified 3 Sep 2026** |
| Position | `x y z` | `positions` MFVec3f | `positions` point3f[] | `POSITION` VEC3 (+min/max) |
| Rotation | `rot_0..3` = **w x y z** | `orientations` MFQuaternion **x y z w** | `orientations` quatf[] (real, i, j, k) | `…:ROTATION` VEC4 **x y z w** |
| Scale | `scale_*` = **log** | `scales` **linear**, ≥ 0 | `scales` float3[] linear | `…:SCALE` **linear**, ≥ 0 |
| Opacity | `opacity` = **logit** | `opacities` **linear 0..1** | `opacities` float[] | `…:OPACITY` **linear 0..1** |
| SH DC | `f_dc_0..2` raw | `sphericalHarmonicsDegree0Coef0` raw | first of each particle's K | `…:SH_DEGREE_0_COEF_0` raw |
| SH rest | `f_rest_*` **channel-major** (all R, all G, all B) | 15 MFVec3f fields `Degree{d}Coef{c}` | `radiance:sphericalHarmonicsCoefficients` float3[], **K = (d+1)² per particle, contiguous**; `radiance:sphericalHarmonicsDegree` | 15 VEC3 attributes `SH_DEGREE_{d}_COEF_{c}` |
| Colour | 0.5 + C0·DC | same (shader `sh0*SH_C0`) | same | 0.5 + C0·DC; `COLOR_0` fallback = linear, alpha = opacity |
| Colour space | n/a | `colorSpace` SRGB_REC709_DISPLAY (default) / LIN_… | none in schema; we write `customData x3dnv:colorSpace` | `colorSpace` `srgb_rec709_display` / `lin_…` (required) |

**Frame.** 3DGS training output usually has Y pointing down (COLMAP/OpenCV). When X_ITE 16.8.1 inlines a `.ply`, it wraps the splats in `Transform { rotation 1 0 0 π }` 🔎 (`x_ite.js` 16.8.1, PLY parser). `x3dnv.splats` never bakes that rotation into the arrays, so the round trip stays lossless. Each writer puts it on a parent instead: an X3D `Transform DEF="SplatFrame"`, USD `xformOp:rotateX = 180`, and a glTF node `rotation [1,0,0,0]`.

Sources 🔎 26 Nov 2026: X3D 4.1 CD `gaussianSplats.html` and the 4.1 XSD docs; X_ITE GaussianSplats node reference and the `x_ite@16.8.1` npm source (`parseVertices`, GaussianSplatsComponent shader); OpenUSD `usdVol/schema.usda` in `usd-core` 26.11; the Khronos `KHR_gaussian_splatting` README; Omniverse asset requirement VG.035.

### 1.2 Measured ✅ `receipts/rosetta-20261126-amethyst-llvmpipe.json`

Source: a 190,125-splat, SH-degree-3 training PLY (X_ITE's own example asset, fetched at run time and not committed). We kept the 20,000 most opaque splats.

| Format | Bytes (20k splats, SH3) | Round trip max \|Δ\| | Validator |
|---|---|---|---|
| `.ply` | 4,961,530 | ≤ 1.8e-7 | none |
| `.x3d` (XML, 7 sig. digits) | 12,250,618 (**2.5× PLY**) | ≤ 4.8e-7 (text rounding) | ⏳ X3D 4.1 XSD not reachable from the sandbox (`null`) |
| `.usda` | 14,999,449 | ≤ 3e-7 | usd-core 26.11 `UsdValidation`, 30 validators: **0 errors** (core has no particle-field validator yet) |
| `.glb` | 5,044,380 | ≤ 3e-7 | gltf-validator 2.0.0-dev.3.10: 19 errors, **all `MESH_PRIMITIVE_INVALID_ATTRIBUTE` on the extension's own semantics** + `UNSUPPORTED_EXTENSION`. The published validator predates the ratified extension |

**X_ITE 16.8.1 grades the chain** (headless Chrome, ANGLE/Vulkan on llvmpipe, LLVM 20.1.2, 512²):

| Frame | vs X_ITE's own PLY loader (`Inline url "cloud.ply"`) |
|---|---|
| native `GaussianSplats` X3D written by `x3dnv.splats` | max Δ **1/255**, 91 of 262,144 px differ (text rounding) |
| PLY → glb → usda → X3D chain | identical to the native frame (same 91 px, max 1) |

**Not yet shown:** a hardware-GPU frame, any Omniverse RTX or `hdParticleField` frame of these files, or SPZ compression.

---

### 1.3 X3D validation answers the USD rulebooks ✅ (flywheel turn 3, 26 Nov 2026)

Every rule of three USD rulebooks is mapped to what X3D does about the same mistake, executed scene by scene:

| Rulebook | Rules | X3D can state | Reported |
|---|---|---|---|
| OpenUSD `UsdValidation` (usd-core 26.11) | 30 | 7 | 7 |
| NVIDIA Omniverse Asset Validator 1.18.0 (PyPI, Python ≤ 3.12) | 40 | 18 | 18 |
| NVIDIA SimReady Foundation `c3bd1d8` (23 Nov 2026), what Isaac Sim validates against | 270 | 41 | 41 |

The other 274 rules:

| Why X3D has no rule for it | Rules |
|---|---|
| Impossible to break in X3D (one root, +Y up, metres, seconds, computed normals) | 32 |
| A convention the exporter converts (SimReady's Z up) | 1 |
| USD machinery X3D does not have | 50 |
| A feature X3D 4.0 lacks | 38 |
| One simulator's schema | 44 |
| Pipeline policy | 92 |
| Human judgement | 17 |

- **New checks:** 18 were written and surveyed on 1,548 real X3D files.
- **Where it lives:** x3d_mcp `docs/USD-VALIDATION-PARITY.md` and x3d.loom `LEARNINGS-flywheel-turn-3.md` (FM 364 to 373 after renumbering).
- **Status:** kits waiting to be merged on 26 Nov.

## 2. NVIDIA API Catalog (build.nvidia.com) — what a dev key reaches

| Surface | What it is | Checked | X3D angle |
|---|---|---|---|
| **Free dev key** | about **40 requests/minute**; NVIDIA staff on the forum say free personal keys get no manual increase (2026 threads). Credit counts: posts mention 1,000, but this is unverified (`null`) | 🔎 forum, Jun–Aug 2026 | x3d.lab and x3d.nVidia share one key → pace at 36 and split the budget when both run |
| Chat (OpenAI-compatible) | `https://integrate.api.nvidia.com/v1` | 🔎 | X3D authoring/repair rounds, DSPy programs |
| Nemotron 3 | Nano 30B-A3B (Dec 2025), **Super 120B-A12B** (11 Mar 2026, 1M context, tool calling), Ultra 550B-A55B (4 Jun 2026), 3.5 Super VL 120B (15 Oct 2026); open weights | 🔎 model cards | default probe models; the VL can grade X3D renders |
| **TRELLIS** (Microsoft) | image → GLB on `ai.api.nvidia.com/v1/genai/microsoft/trellis`, since 2 Sep 2025; also a downloadable NIM (Blackwell/Hopper/Lovelace) | 🔎 page; request encoding and response shape **not documented** → the probe settles them | glb → X3D (`Inline` or the add-on), the cheapest "words → X3D world" path |
| 3D Object Generation blueprint | Llama 3.1 8B + SANA + TRELLIS; **deprecated 26 Feb 2026** | 🔎 | don't build on it |
| **USD Code** | Llama-3.1-70B + RAG over OpenUSD docs → USD-Python | 🔎 model card | does it know `ParticleField3DGaussianSplat`? The probe asks |
| USD Search | AI search over OpenUSD/3D/image assets | 🔎 catalog listing | asset intake for X3D scenes |
| **Cosmos 3** | open omnimodel (4B Edge, 16B Nano, 64B Super), MoT; released 31 May 2026; hosted on build.nvidia.com | 🔎 NVIDIA llm-info page | VLM judge of X3D frames; X3D scene → world video |
| Live model list | `GET /v1/models` | ⏳ partly: ran 26 Nov (below); counts not yet copied into the repo | becomes §2's ground truth |
| **First keyed run** (26 Nov 2026, 07:34–07:48 UTC, claude.ai/code cloud session, key as a network secret) | `nemotron-3.5-super-vl-120b-a12b` and `nemotron-3.5-lightning-30b-a3b` both wrote valid X3D 4.0, **5/5**. Lightning used `<Head>`/`<Meta>`; X3D XML is case-sensitive, so x3dcheck now fails it (4/5). At `max_tokens` 4096 both USD answers were **truncated**: these models reason for **~4.7–5.6k tokens** before writing code. At 16384 both hit 5/5 on keywords. Read by eye: the 120B script looks right; Lightning uses `Vec3f` orientations and a scalar SH coefficient, and usd-core 26.11 raises a type error on each (checked here) | 🔎 relayed summary; receipts `probe-20261126-073326/073438/074827.json` are still in that session | probe default is now 16384 tokens and flags `finish_reason=length`; `tools/usd_judge.py` *runs* the scripts (⏳ needs those receipts) |

## 3. Omniverse and OpenUSD

| Item | Facts | Checked | X3D angle |
|---|---|---|---|
| Kit 110 line | 110.0 (Feb 2026) removed the Hydra 2 backend; 110.1.x Apr–Sep 2026; **110.2 (Jul 2026) adds Gaussian Splat ingestion and `omni.kit.converter.gsplat` (.PLY/.SPZ → USD)**; 110.4 Oct 2026 | 🔎 release notes | our `.usda` is an independent writer to check theirs against |
| Particle Fields in RTX | splats rendered natively, with path tracing, shadows, reflections and refraction | 🔎 Omniverse docs | the Omniverse frame for §1, ⏳ |
| Asset requirement VG.035 | rules for `ParticleField3DGaussianSplat`: consistent array lengths, valid ranges, SH matching the declared degree; OpenUSD 26.03+ / Kit 110.1+ | 🔎 | `SplatCloud.check()` implements the same rules |
| Isaac Sim 5.1 → 6.0 | 5.1's geometry path is wired for `OmniNuRecFieldAsset`; 6.0 is the path for the SH-preserving `ParticleField3DGaussianSplat` | 🔎 NVIDIA forum | target 6.0 |
| **Omniverse libraries** | `ovrtx` (RTX sensor sim/rendering), `ovphysx`, `ovstorage`: headless-first C APIs with Python bindings, early access on GitHub/NGC, now part of the NVIDIA Agent Toolkit; plus a blueprint for Omniverse in Blender | 🔎 NVIDIA blog/news | **an RTX renderer as one more engine in the x3d.lab fidelity chain, without Kit** ⏳ |
| OpenUSD 26.03 | new `UsdVol` particle-field schemas, reference renderer `hdParticleField`, WebAssembly builds | 🔎 AOUSD | `usd-core` 26.11 on PyPI has the schema ✅ |

## 4. Splats and neural rendering on CUDA

| Item | Facts | Checked | X3D angle |
|---|---|---|---|
| **3DGRUT** (nv-tlabs) | 3D Gaussian Ray Tracing and the Unscented Transform; RT cores recommended; Linux; `ply_to_usd` export; Kit 107.3 / Isaac Sim 5.0 integration | 🔎 repo + radiancefields.com | trains splats → `.ply` → **X3D** via §1 |
| **gsplat** (nerfstudio) | Apache-2.0 CUDA rasteriser; latest tag v1.5.3; `main` adds CUDA 13, NumPy 2, 3DGUT extensions and HiGS inference rendering (2026) | 🔎 README | Colab-trainable on T4/L4/A100 ⏳ |
| **Lyra / Lyra 2.0** (NVIDIA) | feed-forward 3DGS from one image, distilled from a video diffusion model; ICLR 2026; HF `nvidia/Lyra` | 🔎 | **one picture → an X3D splat world** ⏳ |
| TRELLIS.2 (Microsoft) | 4B, MIT; image → PBR mesh up to 1536³; on Hugging Face; not seen on NIM (⏳ probe) | 🔎 | higher-quality local route on A100 |

## 5. CUDA Python, world models, optimisers, data

| Item | Facts | Checked | X3D angle |
|---|---|---|---|
| **Warp** | Python → CUDA JIT kernels; docs at 1.19; CUDA-13 wheels need driver ≥ 580 (Colab L4 had 580.82.07, see the x3d.lab L4 finding) | 🔎 | X3D RigidBodyPhysics / particle systems simulated in Warp, baked back to interpolators |
| **V-JEPA 2 / 2.1** (Meta) | self-supervised video world model (1.2B); in HF Transformers | 🔎 | a *perceptual* distance between engines' frames and animations (x3d.lab's grading) |
| **DSPy 3.3** | `dspy.GEPA` reflective optimiser; experimental `dspy.Flex` lets GEPA rewrite a module's code | 🔎 release notes | **x3d_mcp validator as the GEPA metric** → prompts and programs that write valid X3D, cheap at 40 rpm |
| **Objaverse 1.0 / XL** | 800K objects, per-object CC licences (721K CC-BY); XL 10M+, ODC-By overall, mixed per-object, Polycam subset by request only | 🔎 HF cards | licence-filtered glb corpus for the X3D fidelity chain at scale |

## 5b. Robotics and physical AI (🔎 read 26 Nov 2026)

| Item | Facts | X3D angle |
|---|---|---|
| **Newton** | open, GPU physics engine by NVIDIA, Google DeepMind and Disney Research; a Linux Foundation project, Apache-2.0, built on Warp and OpenUSD; MuJoCo-Warp is one of its solvers; **1.0 GA at GTC 2026**; Toyota Research Institute (Drake) partners | a third engine for the x3d.physics flywheel (STRATEGY M3) |
| **Isaac Sim 6.x** | 6.0 GA on Kit 110 with PhysX and Newton backends, an Isaac Sim MCP server and agent skills; URDF and MJCF importers 3.0 (Asset Structure 3.0, Newton schema); 6.2 on Kit 110.4 adds a browser WebRTC viewer skill | MCP-to-MCP loop with x3d_mcp (Q16); SimReady validation (M1) |
| **Isaac Lab 3.0, GR00T 2, Isaac Lab-Arena** | Isaac Lab 3.0 GA late Oct 2026; GR00T 2 and an open policy benchmark shown at CoRL 2026; Lab-Arena for policy evaluation | H-Anim → humanoid retargeting (M3); X3D scenes as evaluation tasks |
| **Cosmos 3, Physical AI Data Factory** | Cosmos 3 (May 2026) unifies world generation, vision reasoning and action; the GTC 2026 Data Factory blueprint has Cosmos Curator, Transfer and Evaluator | labelled synthetic data from X3D (M4) |
| **ROS REP 158 (draft, 3 Mar 2026)** | an OpenUSD profile for robotics simulation assets that adopts AOUSD, ASWF and NVIDIA asset requirements | the same rules our USD parity answers; a ROS-facing audience |
| **AOUSD** | Core Specification 1.0; the Characters, Motion and Interactivity (CMI) interest group formed 25 Mar 2026 to standardize skeletal animation, blend shapes and interactive behaviour; new members July 2026 | X3D's event model and H-Anim as reference input (M2) |

## 6. Why X3D, in one paragraph (the advocacy thesis)

glTF and USD now carry splats, and X3D 4.1 carries the *same* splats bit for bit (§1.2). X3D's validator now answers every OpenUSD, Omniverse and SimReady rule an X3D file can break (§1.3). X3D adds what the other two leave to an application: a ROUTE graph, sensors, bindable Viewpoints, interpolators, Scripts, metadata, and a browser (X_ITE) that runs all of it from one file in any web page. So the pitch to NVIDIA isn't "another format". It's **the interactive, web-native, ISO-standard layer above NVIDIA's generators** (TRELLIS, Lyra, 3DGRUT, Cosmos), proven by receipts, not slides.

## 7. Open questions (each becomes a receipt)

1. TRELLIS on NIM: what image encoding does it accept, and what is the response shape (base64 glb? artifacts?). → `probe --trellis`.
2. Does USD Code know the 26.03 `ParticleField3DGaussianSplat` schema? → `probe` step 3. Nemotron 3.5 Super VL apparently does (above); run `usd_judge` on its script to be sure.
2b. Does `chat_template_kwargs.enable_thinking=false` turn off Nemotron 3.5's ~5k-token reasoning, and does quality hold? → `probe --no-think` vs default.
3. Do Omniverse's `omni.kit.converter.gsplat` and our writer produce the same USD for one PLY? (orientation convention, SH layout, frame)
4. Does `hdParticleField` / Omniverse RTX draw our `.usda` like X_ITE draws our `.x3d`? Measure with the same viewpoint and a pixel delta.
5. X3D 4.1 XSD validation of `GaussianSplats` (needs the x3d_mcp fork with the 4.1 schema).
6. Does an X3D scene that passes x3d_mcp export through Blender 5.x to USD that passes the Omniverse Asset Validator and a SimReady profile? (STRATEGY M1)
7. The SH-ordering wording in the USD schema doc ("sorted first by order (m) and then by index (l)") vs the 3DGS l-major order. We use 3DGS order; a test splat with only one non-zero higher band will settle it in `hdParticleField`.
