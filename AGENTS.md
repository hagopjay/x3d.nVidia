# AGENTS.md — rules for every session working in x3d.nVidia

This repo is the agentic home for **X3D × NVIDIA**. Several Claude sessions and the owner (Jason, `hagopjay`) share it. Read this, then `ATLAS.md`, then `QUESTS.md`.

## House rules (from the owner's standing preferences)
1. **Evidence.** Every number names its source: adapter + driver, tool + version, validator + commit. A missing measurement is `null`, never a substitute. Receipts go in `receipts/` as JSON, one file per run, named `<what>-<yyyymmdd>-<detail>.json`.
2. **Secrets.** Never write a token, a key or a presigned link into a notebook, receipt, log or commit. Notebooks are saved to GitHub from Colab. Use Colab Secrets (`NVIDIA_API_KEY`, `GITHUB_TOKEN`) or a hidden `getpass`. Receipts carry `key_id` = sha256(key)[:8] only.
3. **Notebooks.** The first cell has `VERBOSE = True` and `VISUAL = True`. Long tools stream rate-limited progress, and every image or chart is shown as soon as it exists. Long runs are fine; silent runs are not.
4. **Shipping changes.** Each change ships as a kit: `<kit>.zip`, one folder holding only `apply.sh`, `PR.md`, `README.txt` and exactly one `.patch`. `apply.sh` clones into `./repo`, is safe to re-run, says "already in main" once merged, and refuses a second patch. One kit per round, against current main; never stack on an unmerged branch.
5. **Dense tables, verbose logs**, and short prose.

## The NVIDIA key
- One developer key: **~40 rpm** on build.nvidia.com, and no manual increases for free keys. The *other agent* holds it; this repo never sees it.
- `x3dnv.nim` paces to `X3DNV_NVIDIA_RPM` (falls back to `X3DLAB_NVIDIA_RPM`, default 36). **x3d.lab's Model Duel / Foundry rounds use the same key.** Don't run both at once, or split the rpm.
- Calls that spend credits (TRELLIS, VLM frames, GEPA runs) are opt-in flags, never defaults.

## Staying in good standing (NVIDIA and GitHub)
- **The build.nvidia.com key is a trial key for development and evaluation, not production** (NVIDIA API Trial Terms of Service). Pre-generate content and publish the results; never put a page in front of visitors that calls the API live.
- **One key at a time.** A new key replaces the old one; never run two keys in parallel to multiply the rate limit.
- **Pace below the limit** (36 of ~40 rpm), honour `Retry-After`, stop after 5 retries, and run one keyed job at a time across x3d.lab and this repo.
- **Credit-spending calls** (TRELLIS, VLM frames, GEPA runs) are opt-in flags with a stated budget.
- **GitHub:** kits open one pull request per change on our own repos; no automated activity on other people's repositories.

## Lanes (who owns what)
| Lane | Owner | Notes |
|---|---|---|
| Splats (PLY ⇄ X3D ⇄ USD ⇄ glTF), `x3dnv.splats` | this repo | ATLAS §1 |
| NVIDIA catalog probes, `x3dnv.nim` / `x3dnv.probe` | this repo | same contract as x3d.lab PR #5's provider |
| X3D → Blender → glTF/USD **meshes** | x3d.lab **Foundry** | don't duplicate; consume its outputs |
| glTF → Unreal | x3d.lab Unreal session | `notebooks/unreal/` there |
| X3D validation (XSD + semantics) | x3d_mcp fork | use it; `x3dnv.x3dcheck` is triage only |
| Rust/wgpu renderer | x3d.wgpu | an engine to grade against, like X_ITE |

## Definition of done for a quest
A receipt in `receipts/`, a row updated in `ATLAS.md` (✅ with the receipt's name), the quest's status in `QUESTS.md`, and, where possible, a page or scene someone can open in a browser.
