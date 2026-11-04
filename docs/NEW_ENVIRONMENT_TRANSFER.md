# New Environment Asset Transfer

Updated: 2026-10-28

The current hospital keeps its layout and meshes, receives the incoming cloth
materials, and displays eight additional satin instruments on background
Table_03. The updated environment was launched and rendered in Isaac Sim 4.5 on
2026-10-28. The inspection GUI provides work-table, cloth-close-up and new-tool
camera buttons.

## Incoming Assets

Inspected `new-env/hospital_isaac_room_v3_2.usdz` and all eight standalone files
under `new-env/instruments`. Both hospitals are Z-up and use metres; their room
bounds agree. No robot name, articulation root or joint was found in the incoming
room. The current IsaacLab Franka remains the robot.

The incoming package places four distinct instrument types, with one duplicate.
The separate instrument directory supplies eight distinct types:

| Instrument | Length | Transfer |
| --- | --- | --- |
| Allis tissue forceps | 152 mm | Satin display |
| Brown tissue forceps | 152 mm | Satin display |
| Crile-Wood needle holder, closed | 150 mm | Satin display |
| Derf needle holder, closed | 121 mm | Satin display |
| Mayo scissors, straight | 150 mm | Satin display |
| Metzenbaum scissors, curved | 178 mm | Satin display |
| Ragnell retractor | 140 mm | Satin display |
| No. 3 scalpel handle | 120 mm | Satin display; handle only |

Standalone instruments contain rigid-body and mass APIs, and collision meshes
nested inside USD instances. The transfer expands those instances in its local
override layers so the satin tuning reaches all three metal surfaces per tool.
Their source geometry, materials, UVs, transforms and mass settings are retained
in local source copies. Small USD override layers apply the existing
`tune_steel_materials` function: metallic finishes have roughness at least 0.52,
neutral steel colour `(0.48, 0.50, 0.52)` and metallic strength `0.95`, matching
the five original tools. Separate polished/body/recess bindings remain intact.
The original scalpel blade keeps roughness 0.40. Mesh normals, normal textures,
and the Love retractor's Blender weighted normals retain the prior smoothing
fixes. This supersedes the initial transfer's original metal colours and
metallic strengths. The tray's treatment is unchanged.
Dynamics and collisions are disabled on the eight background display
instances.

These types do not replace Kelly, Love or the existing scalpels/scissors. New
recording targets would require collision validation, semantic/instance mappings,
grasp calibration, object handlers and placement validation.

## Cloth Replacement

Six material graphs from incoming Table_04 are copied onto the corresponding
cloth materials on all seven existing hospital tables: green drape, two blue-pad
surfaces, blue bound edge, stitching and cut edge. All 42 materials receive the
transfer; meshes and bindings stay in place.

Eight PNG dependencies are extracted byte for byte into
`assets/new_environment/textures`. This avoids package-member texture-loading
issues. The transfer preserves the incoming graph's colour scale/bias, UV scale,
roughness atlas, crease normal decoding, IOR and colour-space settings. The green
colour texture repeats at 8.3 x 5.225; roughness and crease maps remain at their
source UV scale. The unused refined-normal images in the incoming package are
not connected or combined with its authored crease graph.

The selected Table_04 still receives seeded episode colour variation, relative
to the incoming colour scale/bias. Roughness varies by an offset from the
canonical configuration value of 0.82; a canonical configuration reproduces the
incoming roughness atlas. This offset is not a guarantee of mean roughness 0.82.
Other tables keep the exact incoming appearance. The old microfiber MDL graph
is not applied over the new cloth.

## Implementation And Review

| File | Purpose |
| --- | --- |
| `env/new_environment.py` | Transfer cloth graphs and vary the selected drape |
| `env/scene_layout.json` | Enables incoming cloth and background display |
| `env/phase4_scene.py` | Loads transfers and hashes their dependencies in run manifests |
| `assets/new_environment/manifest.json` | Source and extracted texture provenance |
| `scripts/inspect_new_environment.py` | Read-only USD inventory |
| `scripts/transfer_new_environment.py` | Rebuild transferred materials and satin overrides |
| `scripts/blender_new_environment_preview.py` | Matched Blender cloth and tool previews |
| `tests/test_new_environment.py` | Geometry, texture, finish and repeatability checks |

Review assets under `exports/new_env_transfer_20261028`:

- [Cloth comparison sheet](../exports/new_env_transfer_20261028/cloth_comparison.png)
- [Incoming cloth, context](../exports/new_env_transfer_20261028/incoming_context.png)
- [Incoming cloth, close view](../exports/new_env_transfer_20261028/incoming_close.png)
- [Previous microfiber, context](../exports/new_env_transfer_20261028/previous_context.png)
- [Previous microfiber, close view](../exports/new_env_transfer_20261028/previous_close.png)
- [Eight satin tools](../exports/new_env_transfer_20261028/satin_tools.png)
- [Blender study](../exports/new_env_transfer_20261028/material_transfer.blend)
- [Merged room and display USD](../exports/new_env_transfer_20261028/current_environment.usda)
- [Full source inventory](../exports/new_env_transfer_20261028/inventory.json)

The merged room USD is an inspection asset; IsaacLab supplies the current robot,
task objects, cameras and runtime room alignment separately. The Blender study
uses the previous drape's identical mesh, UVs, lighting and framing for its
before/after views. Cloth comparisons render directly at 448 x 448. The separate
896 x 896 tool sheet does not change production camera resolution.

## Validation And Limits

The latest steel-match captures are in
`exports/new_env_transfer_20261028/isaac_matched_steel`. They supersede the earlier
RGB captures for judging instrument colour and metallic strength:

- [Updated hospital camera sheet](../exports/new_env_transfer_20261028/isaac_matched_steel/camera_views.png)
- [All 13 tools under the same lighting](../exports/new_env_transfer_20261028/isaac_matched_steel/matched_lighting_tools.png)

The inspection GUI adds a `Same-light view` camera with `Previous tool` and
`Next tool` controls. Each tool is shown at its physical size on the same neutral
backing, with fixed white lights, exposure and camera. A small enclosure blocks
the hospital's dome light from washing out this diagnostic setup. Only its
temporary diagnostic copies are repositioned; production geometry and lights
retain their existing setup. The earlier Blender tool preview predates the
colour/metallic match.

All 15 targeted material, normal and transfer tests pass with Isaac Sim 4.5's
USD 22.11 libraries. Source hospital packages are
not overwritten. Tests verify unchanged old-room geometry, valid graph
connections, extracted texture hashes, repeatable randomization, original tool
geometry/bindings, matching steel colour and metallic strength, satin roughness,
unchanged smoothing normals, repeat application and disabled display dynamics.

Blender and Isaac RGB renders were visually inspected. Isaac captures include
the six production cameras and two temporary inspection cameras, all at native
448 x 448. The live scene verifies all 42 cloth materials, all 24 incoming satin
surfaces, and disabled dynamics/collisions on the display instruments. The
background tool table renders much darker than the active workspace under the
existing lighting; no production lights were changed for this preview.

- [Isaac production camera sheet](../exports/new_env_transfer_20261028/isaac_render/camera_views.png)
- [Isaac cloth close-up](../exports/new_env_transfer_20261028/isaac_render/cloth_closeup.png)
- [Isaac background tools](../exports/new_env_transfer_20261028/isaac_render/new_tools.png)
- [Isaac capture manifest](../exports/new_env_transfer_20261028/isaac_render/manifest.json)

Semantic capture and a full training episode remain unvalidated. The installed
semantic annotator is disabled only in this RGB inspection launcher, matching
the previous material previews. The existing repository
structure check stops on pre-existing root files, including `.env`, `.gitmodules`
and the ASPIRE/experiment documents; those unrelated files were retained.
