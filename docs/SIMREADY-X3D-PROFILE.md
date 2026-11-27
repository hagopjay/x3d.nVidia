# X3D SimReady profile (Q12, draft 2, 27 Nov 2026)

Plain X3D leaves open what NVIDIA's SimReady Foundation closes: a file may be in centimetres, built of Spheres, carry no
licence and no labels, and still be valid X3D. This profile says **where an X3D file writes each fact SimReady asks for**, so
that three things line up on the same file:

1. **x3d_mcp checks it** (`src/validation/simready_checks.py`, x3d_mcp #40), before any USD exists;
2. **`x3d2usdphysics` carries it** to USD as written, never repaired;
3. **NVIDIA's validator judges the USD** and agrees with the X3D check.

A file **opts in** with any `<meta name="simready:...">` in `<head>`. A file that does not opt in is never reported. A label is
judged wherever one is written.

## Where each fact is written

| Fact | In the X3D file | In the USD the writer makes | SimReady |
|---|---|---|---|
| Author, licence, category, Q-code | `<meta name="creator">`, `<meta name="license">`, `<meta name="simready:category">`, `<meta name="simready:qcode">` (aliases in draft 1 below) | `customLayerData.SimReady_Metadata` | SR.003, SR.004 |
| Thumbnail | `<meta name="Image" content="picture.png"/>`, the Web3D authoring-hints name for a scene's picture; a PNG beside the scene | `.thumbs/256x256/<file>.png`, copied, not resized | SR.002 |
| Length unit | `<unit category="length" conversionFactor="...">` (absent means metres) | `metersPerUnit` = the X3D factor; points are not rescaled | UN.007 |
| Geometry form | `IndexedFaceSet`, `IndexedTriangleSet` (a mesh) or `Box`, `Sphere`, `Cone`, `Cylinder` (not) | `Mesh` or `Cube`, `Sphere`, `Cone`, `Cylinder` | VG.MESH.001, VG.021 |
| Capabilities claimed | `<meta name="simready:features" content="rigid_bodies multibody semantic_labels material_labels"/>` | not written; it scopes the X3D checks | RB.001, RB.MB.001, SL.001, SL.MAT.001 |
| Semantic labels | a `MetadataSet name="semantics:labels"` in a node's `metadata` field; each `MetadataString` in it is one taxonomy (its `name`) and its labels (its `value`) | `SemanticsLabelsAPI:<name>` applied, `token[] semantics:labels:<name>` | SL.001, SL.003, SL.QCODE.001, SL.MAT.001, COCO.001, CITY.001, ADE.001, VOC.001, SUN.001, IN1K.001, AFF.001, AFF.002 |

A label sits on the node it describes: a `RigidBody` (the body's Xform), a `CollidableShape` or `Shape` (the gprim), an
`Appearance` or its material (the USD Material). A label written with no value is carried as applied and empty, because that is what the
X3D says.

```xml
<head>
  <meta name="creator" content="HagopJay"/> <meta name="license" content="CC-BY-4.0"/>
  <meta name="simready:category" content="Furniture"/> <meta name="simready:qcode" content="Q15026"/>
  <meta name="simready:features" content="rigid_bodies semantic_labels material_labels"/>
  <meta name="Image" content="chair.png"/>
</head>
...
<Shape containerField="shape">
  <MetadataSet containerField="metadata" name="semantics:labels">
    <MetadataString containerField="value" name="wikidata_qcode" value='"Q15026"'/>
    <MetadataString containerField="value" name="coco" value='"chair"'/>
  </MetadataSet>
  <Appearance>
    <MetadataSet containerField="metadata" name="semantics:labels">
      <MetadataString containerField="value" name="material" value='"wood"'/>
    </MetadataSet>
    <Material diffuseColor="0.5 0.3 0.1"/>
  </Appearance>
  <IndexedTriangleSet index="..."><Coordinate point="..."/></IndexedTriangleSet>
</Shape>
```

## The crossing: one receipt per rule

`q12/profile_crossing.py` takes the failing and the passing proof scene of every profile rule from x3d_mcp
(`tests/usd_parity.py`), asks x3d_mcp for its verdict, writes both scenes to USD with `x3d2usdphysics` (no `--meta`, nothing
repaired) and runs the SimReady requirement on both. **Confirmed** means all four agree: X3D reports the failing scene and
SimReady fails its USD; X3D passes the passing scene and SimReady passes its USD.

**Measured (Confirmed; usd-validation-nvidia 1.23.0, usd-core 26.11, SimReady tiers
c3bd1d8 2026.10.0, Python 3.12.3; receipt `q12/receipts/profile-crossing-20261127.json`; scenes and USD in
`q12/profile-crossing/`):** 19 of 20 rules confirmed, 1 X3D-only, 0 mismatched.

| SimReady | X3D check | Proof pair | USD of failing scene | USD of passing scene | Crossing | SimReady's words on the failing scene |
|---|---|---|---|---|---|---|
| ADE.001 | `simready-label-not-in-vocabulary` | `sr-vocab-ade20k` | fail | pass | **confirmed** | Unknown ADE20K semantic segmentation 150 label: 'gizmo' is not a member of the 'ade20k' taxonomy. |
| AFF.001 | `simready-label-not-in-vocabulary` | `sr-vocab-affordance` | fail | pass | **confirmed** | /World/A/IndexedFaceSet property semantics:labels:affordance has disallowed token 'gizmo' at time default. All |
| AFF.002 | `simready-label-not-in-vocabulary` | `sr-vocab-affordance_state` | fail | pass | **confirmed** | /World/A/IndexedFaceSet property semantics:labels:affordance_state has disallowed token 'gizmo' at time defaul |
| CITY.001 | `simready-label-not-in-vocabulary` | `sr-vocab-cityscapes` | fail | pass | **confirmed** | Unknown Cityscapes fine semantic labels label: 'gizmo' is not a member of the 'cityscapes' taxonomy. |
| COCO.001 | `simready-label-not-in-vocabulary` | `sr-vocab-coco` | fail | pass | **confirmed** | Unknown COCO Instances label: 'gizmo' is not a member of the 'coco' taxonomy. |
| RB.001 | `simready-no-rigid-body` | `sr-one-body` | fail | pass | **confirmed** | No physics rigid bodies found under the default prim. |
| SL.001 | `simready-shape-unlabelled` | `sr-unlabelled` | fail | pass | **confirmed** | Unlabeled prim: no SemanticsLabelsAPI semantics found on the prim, its ancestors, its bound material, or its G |
| SL.003 | `simready-label-empty` | `sr-label-empty` | fail | pass | **confirmed** | Unusable semantic label: 'SemanticsLabelsAPI:wikidata_qcode' is applied but 'semantics:labels:wikidata_qcode'  |
| SR.002 | `simready-thumbnail-missing` | `sr-thumbnail` | fail | pass | **confirmed** | No thumbnail found at WORK/sr-thumbnail/failing/.thumbs/256x256/sr_thumbnail.usda.png for SimReady asset <WORK |
| SR.003 | `simready-metadata-missing` | `sr-provenance` | fail | pass | **confirmed** | Required metadata fields are missing: author, asset_license. Metadata should be in SimReady_Metadata dictionar |
| SR.004 | `simready-metadata-missing` | `sr-provenance` | fail | pass | **confirmed** | Required metadata fields are missing: author, asset_license. Fields may be authored in root-layer customLayerD |
| SUN.001 | `simready-label-not-in-vocabulary` | `sr-vocab-sunrgbd` | fail | pass | **confirmed** | Unknown SUN RGB-D 3D detection 10 label: 'gizmo' is not a member of the 'sunrgbd' taxonomy. |
| UN.007 | `simready-unit-not-metres` | `sr-unit` | fail | pass | **confirmed** | Stage has metersPerUnit of 0.01, not 1.0. |
| VG.021 | `simready-mesh-not-triangulated` | `sr-triangles` | no-rule | no-rule | **x3d-only** | no executable SimReady rule at c3bd1d8 |
| VOC.001 | `simready-label-not-in-vocabulary` | `sr-vocab-pascal_voc` | fail | pass | **confirmed** | Unknown PASCAL VOC 20 object classes label: 'gizmo' is not a member of the 'pascal_voc' taxonomy. |
| IN1K.001 | `simready-label-not-in-vocabulary` | `sr-vocab-imagenet_1k` | fail | pass | **confirmed** | Unknown ImageNet-1K / ILSVRC2012 classification label: 'gizmo' is not a member of the 'imagenet_1k' taxonomy. |
| VG.MESH.001 | `simready-geometry-not-mesh` | `sr-mesh` | fail | pass | **confirmed** | Stage does not contain any meshes. |
| RB.MB.001 | `simready-single-body` | `sr-two-bodies` | fail | pass | **confirmed** | Not enough physics rigid bodies found under the default prim. Found 1, expected at least 2. |
| SL.MAT.001 | `simready-material-unlabelled` | `sr-material-label` | fail | pass | **confirmed** | Unlabeled material: a Material prim must have 'SemanticsLabelsAPI:material' applied with a non-empty 'semantic |
| SL.QCODE.001 | `simready-qcode-malformed` | `sr-label-qcode` | fail | pass | **confirmed** | Incorrect semantic label format: the label must be a string starting with letter 'Q' followed by one or more n |

How to read it:

- **The ledger moves from 66 to 86 of 340**, kept as two numbers: 66 rules plain X3D states, and 20 more that only this opt-in
  profile states. The 20 are not mistakes in X3D.
- **Nine NVIDIA checker classes were switched on by hand.** The semantic-label checkers and the six dataset-taxonomy checkers
  are registered with their requirement in the core tier but are not in the engine's default rule set (213 rule classes);
  the script enables them with `enable_rule` and lists them in the receipt. NVIDIA's own note calls the taxonomy capability a proof of concept.
- **VG.021 (triangulated meshes) is X3D-only.** No installed rule enforces it at c3bd1d8, so the X3D check has nothing to agree with.
- **Left as policy, on purpose.** SR.001 and NP.006 ask for fields the writer authors itself (asset name, type, source file, date,
  the metadata dictionary), so no X3D file can fail them. NP.001 cannot be met by any writer that also follows the `World` and
  `Looks` conventions: SimReady's checker wants camelCase or snake_case prim names and rejects both (Confirmed in the rule's source,
  `core/naming_paths/validation.py`). SL.TIME.001 (a label animated over time) is not checked.
- **One proof pair per rule is a small sample.** It shows the check and the rule agree on the case the rule was written for,
  not that they agree on every file. The wider test is Q12-style: run both on real files and read the fired pairs.

**Third-party data.** The eight label vocabularies come from NVIDIA/simready-foundation c3bd1d8 (Apache-2.0) and name the public
datasets they list (ADE20K, Cityscapes, COCO, ImageNet-1K, PASCAL VOC, SUN RGB-D); x3d_mcp's `NOTICE-simready-vocab.md` has the
links and a takedown notice. This repository holds none of the lists.

## Draft 1 (26 Nov 2026): provenance metadata

An X3D file carries the facts SimReady asks of an asset in its `<head>` as `<meta>` elements. `x3d2usdphysics` reads them
and writes `customLayerData.SimReady_Metadata`; **a field the X3D does not carry stays absent and is listed in the
report's `meta_missing`. It is never invented.**

| SimReady requirement | What it asks for | X3D `<meta name=...>` (first match wins) | Written as |
|---|---|---|---|
| SR.001 | asset metadata present | any of the below, plus the writer's own provenance | `SimReady_Metadata` dictionary |
| SR.003 / SR.004 | `author`, `asset_license`, `category`, `qcode` | `creator`, `author`, `dc.creator` · `license`, `rights`, `dc.rights` · `simready:category`, `category` · `simready:qcode`, `wikidata`, `qcode` | `author`, `asset_license`, `category`, `qcode` |
| (asset naming) | a name | `title`, else `WorldInfo.title`, else the file stem | `asset_name` |
| (asset kind) | what it is | `simready:asset_type`, `asset_type`; else `articulated` with joints, `prop` without | `asset_type` |

- `qcode` must be a Wikidata Q-code (`^Q[0-9]+$`); anything else is dropped and reported.
- The writer adds `source_file`, `usd_date_generated`, `rigid_body_count`, `mass` and `asset_extents` itself, from the scene.
- `--meta key=value` adds or overrides a field for one run.

```xml
<head>
  <meta name="title"            content="Pendulum"/>
  <meta name="creator"          content="HagopJay"/>
  <meta name="license"          content="CC-BY-4.0"/>
  <meta name="simready:category" content="Toys"/>
  <meta name="simready:qcode"    content="Q111"/>
</head>
```

**Measured (Confirmed; SimReady tiers c3bd1d8, usd-validation-nvidia 1.23.0, Python 3.12):** the 21 PhysX-bridge scenes
carry none of `author`, `asset_license`, `category`, `qcode`, so SR.003 and SR.004 fail on all 21 (by design). The pendulum
re-converted with the four fields set (`--meta`) passes SR.001, SR.003, SR.004 and NP.006.

**Not claimed in draft 1** (draft 2 above adds SR.002 through `<meta name="Image">`)**:** the assembly/connection requirements (CN, CP, GSP, AM), naming
(NP.001 wants camelCase/snake_case for `World`), and the engine requirements (ISA, RC, RV.* beyond what
`--runtimes` writes, ROS). x3d_mcp's `usd-parity` already reports the ones X3D can state.

**Next (done in draft 2):** a check in x3d_mcp that reports a missing field on a scene bound for USD.
