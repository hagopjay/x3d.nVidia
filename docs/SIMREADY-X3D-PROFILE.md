# X3D SimReady metadata profile (Q12, draft 1)

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

**Not defined by X3D, so not claimed:** SR.002 (thumbnail), the assembly/connection requirements (CN, CP, GSP, AM), naming
(NP.001 wants camelCase/snake_case for `World`), and the engine requirements (ISA, RC, RV.* beyond what
`--runtimes` writes, ROS). x3d_mcp's `usd-parity` already reports the ones X3D can state.

**Next:** a check in x3d_mcp that reports a missing `simready:*` field as info on any scene bound for USD (not written here: it
is x3d_mcp's contract surface and wants its own PR).
