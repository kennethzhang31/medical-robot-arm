# Simulation material realism

The 2026-10-20 material pass uses the existing surgical meshes and the active
hospital table (`Table_04`). It is a provisional finish adjustment, pending
comparison with photographs of the actual workspace.

## Models and finishes

| Scene label | Source asset | Runtime finish |
| --- | --- | --- |
| Scalpel / knife | `knife_centered.usd` | Metallic 1; handle roughness 0.52, blade 0.40 |
| Scissors | `my_scissor_clean.usd` | Steel fallback: metallic 0.95, roughness 0.52 |
| Love retractor | `love_centered_root_at_center.usd` | Steel: metallic 0.95, roughness 0.52 |
| Kelly | `kelly_root_at_center.usd` | Existing metal colors; roughness at least 0.52 |
| Second scalpel | `scalpel_type2_root.usd` | Existing metal colors; roughness at least 0.52 |
| Tray | `SurgicalTray.usd` | Existing metal colors; roughness at least 0.40 |

The scalpel source has unconnected surface normals of `(1, 1, 1)`. These are
corrected to the neutral tangent-space normal `(0, 0, 1)`. Connected normal maps
remain in place. The retractor source is nonmetallic and its color atlas refers
to a missing `Surgical_instruments.usdz`; its surface now uses a neutral steel
color instead of that unresolved connection.

`env/instrument_materials.py` owns these changes. The common spawn factory
applies them to targets and duplicate instruments before cloning. Separate
handle/blade materials remain separate. Source USD files are never saved over.

## Tabletop detail

The hospital table already includes woven base color, a roughness map, and a
crease normal map. The old episode randomizer replaced these with a constant
green shader. `src/recorder/domain_randomization.py` now adjusts the source
texture scale/bias and keeps those texture connections and material bindings.

The selected drape now uses the Blender fibre maps described below and a roughness
range of 0.76-0.88, with metallic and clearcoat set to zero and IOR set to 1.35.
Episode variation tints the colour texture and samples a mean roughness
of 0.76-0.88; the map varies by up to 0.06 around that mean. Every episode sets
absolute values so repeated variations do not accumulate. Other tables and the
blue pads keep their source materials.

`env/phase4_scene.py` applies the default drape even when randomization is off,
tunes the tray at spawn, and records
`material_contract=satin_steel_microfiber_drape_v4` in new scene manifests.
Geometry, collision, mass, scale, camera calibration, and light intensities are
unchanged by this pass. Use a new recording session for the new appearance;
existing datasets represent their original material distribution.

## Reference microfiber, 2026-10-27

The supplied `cloth.jpg` shows raised microfiber pile. The active material now
uses `assets/blender_microfiber/` and `cloth_material_contract=blender_microfiber_v2`.
The earlier flat weave is retained in `assets/blender_cloth/` for comparison.

`scripts/blender_microfiber_material.py` extracts a blue-cloth patch from the
reference photo, removes broad lighting variation, makes the patch periodic,
and normalizes local contrast to prevent a repeated bright/dark tile. Its
luminance supplies an approximate height field, recoloured using the original
drape's mean green. This is an appearance approximation: the photo has no ruler,
and image brightness is not a measurement of height. The assumed tile spans
12 mm; shader relief is 0.12 mm with strength 0.65. No fibre geometry, physical
cloth simulation, subdivision or displacement is added.

Three 512 x 512 textures provide colour, roughness and tangent-space tuft normals.
The existing crease-normal atlas and the folds in the mesh stay in place.
`env/cloth_materials.py` adds an Isaac OmniPBR surface: its main UV transform
tiles the tuft textures, while the independently transformed detail normal uses
the original crease map at 1x. Normal-map roughness filtering is enabled and the
OpenGL tangent convention is explicit. The existing universal USD preview surface
keeps the colour/roughness maps and original creases as a fallback. Blender uses
the same photo height as a bump layer over its original crease normal.
The crease PNG is extracted byte for byte from `hospital_isaac.usdz` because MDL
texture loading does not support USD package-member paths. Both surfaces share
that extracted file, and the source package stays unchanged.

Episode colour tints and mean roughness remain controlled by the existing
randomizer. Both surfaces blend 30 percent of the authored roughness map, with
the constant adjusted to preserve the sampled mean. Only the selected drape
material changes. Other tables, blue pads, instruments, camera calibration,
448 sensor resolution, lighting, mesh geometry and physics are unchanged.

The new normal tile adds about 1 MiB at RGBA8 base level versus the prior weave,
for roughly 35 MiB including the original crease atlas and all three tiles.
This excludes mipmaps, format conversion and caching; total RAM/VRAM has not been
benchmarked. The height image is a Blender study asset, not another runtime map.

`exports/blender_microfiber_20261027/microfiber.blend` contains matched previous
weave and microfiber scenes. Source photo and hospital bytes are checked unchanged;
texture periodicity, finite unit normals and identical points/topology/UVs/transforms
are checked during generation. The copied reference and its SHA256/crop provenance
are retained. Ten offline material/normal tests pass, including separate tuft/crease
UV scales, correct normal colour space, preserved sampled roughness, repeated seeds,
texture hashes, decoded unit normals, byte-identical crease extraction and isolation
from the other tables. Individual fibre silhouettes
and true fuzz scattering are not represented by these bump maps.

## Initial Blender cloth fibres, 2026-10-27

`scripts/blender_cloth_material.py` creates an interlaced warp/weft pattern with
small longitudinal filament variations and uneven yarn spacing. The portable
colour and roughness maps in `assets/blender_cloth/` are each 512 x 512. A tile spans 10.4 mm
with 16 yarns, giving an approximately 0.65 mm yarn pitch on the tabletop.
The UV repeats use the measured median tabletop density of 3.26709 / 2.07803
metres per UV unit. The drape's existing UV stretch also stretches the pattern.
The source texture's mean green is retained, with low-contrast yarn colour variations.

`env/cloth_materials.py` applies these maps to the selected table through the
existing USD texture nodes and a shared `UsdTransform2d`. It sets repeat wrapping
and raw colour space for roughness. The original crease normal atlas and its
2*x-1 decoding stay intact, as do the existing episode tint/roughness controls.
Other tables, blue pads, lights, camera resolution, mesh points, faces, UVs,
transforms and physics remain unchanged. Source USD packages are not overwritten.
The runtime uses the portable maps; Blender procedural nodes are not required.

The two small maps replace the 4096 x 2048 colour and roughness atlases, while
the original 4096 x 2048 crease normal stays in use. At equal decoded format this
uses about 34 MiB versus 96 MiB for all three RGBA8 maps, excluding mipmaps,
caching and compression. Actual total RAM/VRAM has not been benchmarked.
Both the painted crease shading and the folds in the mesh remain. No displacement, subdivision, fibres as
geometry, or camera supersampling is introduced.

`exports/blender_cloth_20261027/cloth_fibres.blend` contains the matched original
and new material scenes, rendered directly at 448 with identical camera, broad
area lights and Cycles settings. The new scene opens on a close-up. Context
renders demonstrate that fine weave softens under minification. Geometry/UV
equality, periodic-map boundaries, finite texture values and unchanged source
hospital bytes are checked during creation. Nine offline asset/material tests
pass, including texture hashes, normal decoding, correct tiling, repeated seed
stability, unchanged geometry and isolation from other tables. This is a
provisional woven surgical-cloth appearance, not calibrated to a cloth photograph.

The first regular weave/detail-normal trial was rejected after Isaac showed
moire bands in the wide cameras and loss of the original painted crease shading.
Its diagnostic images remain in `isaac_comparison_rejected_regular_weave/` under
the export directory. They do not represent the applied material.

The final matched Isaac comparison in `isaac_comparison/` passes for all six
native 448 cameras and a separate temporary 448 macro camera. Only the drape's
colour/roughness texture files, UV connections and wrapping change between modes;
mesh geometry/transforms, body/joint states, camera calibration, lighting and
other materials are hash-checked unchanged. No physics steps occur between
captures. The close-up shows the fibre pattern; wide views retain the painted
creases without the strong moire bands seen in the rejected trial. The preview
remains on the final material and includes previous/new buttons. This is RGB
inspection only; it does not certify semantic capture or training collection.

## Blender finish comparison, 2026-10-25

The latest finish increases tool roughness from 0.40 to 0.52 and blade roughness
from 0.32 to 0.40. This broadens highlights on thin steel; the tray retains its
previous finish. The supplied screenshot also shows jagged silhouettes, which
this material change cannot guarantee to remove at small sensor resolutions.
The scissors already have 31,500 triangles and unit-length imported normals;
no mesh subdivision or normal replacement was applied.

`exports/instrument_finish_20261025/comparison.png` shows matched Blender Cycles
renders at 96 samples with identical cameras, lighting, geometry and color
management. Both images disable the earlier study's Blender-only anisotropy.
The softer finish is in `instrument_finish.blend`, scene
`03 Instrument Finish Comparison`. The original study scenes remain available.

The `usd/` subdirectory contains five reference-based USDA assets with the
same portable material inputs used at runtime. References retain the source
geometry, imported normals, transforms, physics schemas and relationships;
the exporter checks these after reopening each asset. These files depend on
this repository's `assets/` directory and retain each source asset's units.
Keep the existing instrument spawn scales when substituting them manually.
The recorder uses the shared material function directly and needs no USD path
changes. Restart the recorder to load the new finish.

`scripts/blender_instrument_finish.py` reproduces the comparison from the
existing Blender study and exports the USD overlays. It refuses to overwrite
an existing blend file. The source USD hashes remain unchanged, and all six
offline material tests pass. An Isaac 4.5 preview was attempted again on
2026-10-25 but crashed with a Windows access violation during Hydra viewport
initialization, before scene construction. The screenshot's specific artifacts
initially remained unverified in Isaac; `isaac_preview.log` records that failure.

A later inspection rendered all six native 448 x 448 sensor views successfully
using a process-local DirectX 12 override and the existing USD 4.5 text wrappers.
Images are in `exports/instrument_finish_20261025/isaac_preview_settled/`.
Physics settling ran before capture, and the bound-material audit confirmed the
new roughness values. Thin silhouettes and highlights still show pixel breakup:
the finish alone does not eliminate it. The semantic annotator fails on this
runtime, so this inspection uses RGB/depth only and skips the semantic audit;
it does not validate training-data collection. The app crashed on shutdown after
all six captures were written. The preview launcher, material audit and capture
log are in `logs/isaac_finish_preview_20261025/`.

A matched 448 versus 896 RGB inspection on 2026-10-26 captured all six cameras
using temporary render products on the same camera prims. Images and the
unchanged-scene validation manifest are in
`exports/instrument_finish_20261025/isaac_resolution_comparison/`. Ring outlines
and diagonal blade edges improve visibly in the right-camera view; rendering
896 and reducing to 448 also produces cleaner edges than direct 448 rendering.
This adds four times the output pixels, with no runtime benchmark yet. It does
not add a production 896 recording mode. No training episodes were captured;
the final settling pass reported failure, and semantic inspection remains
disabled. The captures hold body/joint states, cameras, lights and shader inputs
fixed and are suitable for comparing appearance only.

A subsequent diagnostic verified nonblank native 896 RGB and aligned depth on
all six actual sensors. Its captures remain in
`exports/instrument_finish_20261025/isaac_hd_preview/`. The temporary 896
recording implementation passed 19 focused checks, but was removed at the
user's request to constrain further improvements to Blender. Recording is back
to the original 448/224 modes, defaults, audits and exports. Downsampling after
rendering does not remove the larger render-target memory requirement. No full
training episode or semantic capture was validated in that diagnostic.

The Blender-only follow-up is in `exports/blender_shading_20261026/`. Separate
mesh copies compare imported normals, welded seams with angle/area-weighted
normals, and optional 0.075 mm two-segment bevels. All six comparison images
render directly at 448 with matched Cycles settings. Normals-only cleanup keeps
triangle counts at 31,500 for the scissors and 272 for the low-poly retractor,
while reducing duplicate vertices. Scissors look almost unchanged; the
retractor's planar shading becomes more even. Bevels add little visible benefit
at this size. Original mesh signatures are verified, source USDs are untouched,
and the candidates have not been applied to Isaac geometry or physics.

The selected retractor normals were then transferred onto its original USD mesh
without replacing its geometry. The runtime spawner reads
`assets/blender_normals/love_retractor.usda`, checks the source points/topology
hash, and applies 816 face-corner normals to all retractor instances. The
original 206 vertices / 272 triangles, UVs, collision geometry, physics settings,
transforms and material bindings remain intact. Scissors keep their original
normals; bevel and subdivision studies remain unapplied. The normal payload
adds 7,320 bytes per instance, with no higher-resolution render targets.

`exports/blender_shading_20261026/shading_applied.blend` demonstrates the transfer
on the original mesh. Its 448 render matches the welded normal study to a mean
absolute pixel difference of 0.000253/255. Eight targeted USD/material tests
pass, including unchanged non-normal attributes, schemas and relationships,
idempotence, source-byte preservation and rejection of geometry mismatches.
Run manifests include the normals contract and the derived normal asset hash.
The matched Isaac RGB comparison verifies all four retractor instances at
448 with fixed geometry, body/joint states, cameras, lights and shader inputs.
Its images are in `exports/blender_shading_20261026/isaac_comparison/`. Equivalent
face-corner data is used for the original-normal baseline so Hydra never changes
interpolation during capture. The final run has no normal-layout fallback
warning. Shaft shading is more even in the wrist view; the wide-view effect is
subtle and does not eliminate undersampled silhouette edges. No training
episode was recorded; the existing semantic-annotator limitation remains.

## Match the real workspace

No identified photographs of the actual workspace were available for this pass.
Use an overall workspace photo and close-ups of the instruments, table covering,
and tray under normal room lighting. Match the camera viewpoint first, then the
table color, steel finish, and light positions. Keep the scalpel blade smoother
than its handle unless the photographs show a different finish. These roughness
values are starting points, not measurements from photographs.

Compare the six recorded sensor views as well as the main viewport. Use the
same poses, light levels, exposure, and randomization seed for each comparison.
Inspect instrument-only highlights; white robot pixels are not steel glare.

## Validation

Six material tests pass using the project's USD 4.5 reader. They cover the
scalpel's separate finishes and corrected normals, the retractor repair, the
other tools/tray, texture retention across repeated seeds, unchanged tabletop
geometry, isolation from other tables, and unchanged source-asset bytes.
Twelve related scene-clutter, RGB, and seeded-lighting regression tests also
pass. A broader training-readiness run has an unrelated missing `diffusers`
dependency in its perception-policy test.

Run the USD checks without starting Kit:

```powershell
& C:/isaac-sim-450/python.bat -c "import sys; sys.path.insert(0,'.'); from scripts.convert_aspire_assets import usd_bindings; bindings,handles=usd_bindings(); import unittest; result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(['tests.test_scene_materials','tests.test_instrument_materials'])); sys.exit(not result.wasSuccessful())"
```

The renderer crashed during Kit stage/viewport initialization in both the direct
launch and the normal IsaacLab headless launcher, before scene construction.
There are no verified rendered before/after images from this pass. Logs and the
read-only source-material audit are in `logs/material_realism_20261020/`.
