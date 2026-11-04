# Blender and Isaac Sim Material Improvements

Updated: 2026-10-28

## Current Result

The original and incoming surgical tools share neutral steel colour
`(0.48, 0.50, 0.52)` and metallic strength `0.95`, with the softer satin finish
retained. The Love retractor also uses
Blender-cleaned shading normals. The existing hospital now uses the green woven
drape and blue-pad materials from `new-env/hospital_isaac_room_v3_2.usdz`.
The previous photo-derived microfiber material remains available as a comparison.

Eight incoming instruments are transferred as satin display assets on background
Table_03. The original five recording targets and the existing Franka remain in
use. There is no robot or articulation in the new room package. See
[New environment transfer](NEW_ENVIRONMENT_TRANSFER.md) for the inspection,
preview files, validation and remaining simulation checks.

Production cameras remain at 448 x 448. No subdivision, bevel geometry, physical
cloth simulation or geometric fibres were added to the production assets.

| Area | Applied change | Status |
| --- | --- | --- |
| Surgical tools | Satin material tuning and source-material repairs | Applied |
| Love retractor | Blender weighted normals on the original mesh | Applied |
| Scissors | Existing normals and geometry retained | Unchanged after comparison |
| Table drape and blue pads | Incoming woven/reference cloth material graphs | Applied to existing cloth meshes |
| Incoming instruments | Eight satin display tools on background Table_03 | Applied; not new recording targets |
| Cloth folds | Original mesh folds and crease-normal texture retained | Preserved |
| Camera resolution | Original 448/224 modes | Restored after the resolution experiment |
| Cloth sheen | Discussed as a further improvement | Not applied |

## 1. Surgical Tool Materials

Adjusted the steel finishes to soften sharp reflections:

| Surface | Current finish |
| --- | --- |
| Original and incoming steel tools | Neutral colour (0.48, 0.50, 0.52), metallic 0.95 |
| Most steel tool surfaces | Roughness at least 0.52 |
| Scalpel handle | Roughness 0.52 |
| Scalpel blade | Roughness 0.40 |
| Love retractor | Roughness 0.52, metallic 0.95 |
| Surgical tray | Minimum metallic-surface roughness 0.40 |

Separate blade, handle and recessed material regions remain separate. The earlier
source-colour preservation was replaced with the shared neutral steel values to
remove the mismatched warm and dark finishes. The tray retains its earlier
material treatment. The scalpel's invalid unconnected shader normal `(1, 1, 1)`
was corrected to `(0, 0, 1)`. The Love retractor's missing colour texture was
replaced with a neutral steel fallback.

Implementation: [instrument_materials.py](../env/instrument_materials.py).

## 2. Blender Normal Cleanup

Compared imported normals, cleaned weighted normals and small bevels in Blender.
The retractor benefited from more even surface highlights; the scissors showed
little benefit from normal cleanup. Bevels were not selected for production.

The selected retractor normals were transferred back onto its original USD mesh:

- Original geometry remains at 206 vertices and 272 triangles.
- All four runtime retractor instances receive the cleaned normals.
- UVs, transforms, material bindings, collision geometry and physics stay intact.
- The normal payload increases by 7,320 bytes, approximately 7.1 KiB per instance.
- No subdivision or bevel geometry is applied.

Implementation: [instrument_normals.py](../env/instrument_normals.py).
Derived asset: [love_retractor.usda](../assets/blender_normals/love_retractor.usda).
Blender project: [shading_applied.blend](../exports/blender_shading_20261026/shading_applied.blend).

## 3. Initial Woven Cloth Material

Created a procedural interlaced yarn pattern with small fibre variations, using
two repeating 512 x 512 colour and roughness textures. Estimated yarn spacing was
0.65 mm. The green colour and original crease normals were retained.

An earlier regular pattern with replacement detail normals was rejected because
Isaac showed moire bands and the original crease shading was lost. Reducing the
pattern's regularity and contrast, and retaining the crease map, improved the
wide views.

This flat weave is now the comparison baseline, superseded by the microfiber
version below. Its assets remain in [blender_cloth](../assets/blender_cloth/), and
its Blender project is [cloth_fibres.blend](../exports/blender_cloth_20261027/cloth_fibres.blend).

## 4. Previous Photo-Derived Microfiber Material

The supplied `cloth.jpg` clarified that the desired surface has irregular raised
microfiber pile. A patch of the blue cloth was used to derive the new detail:

1. Extracted a cloth-only patch from the reference photograph.
2. Removed broad lighting variation and normalized local contrast.
3. Made the patch repeatable without a strong bright/dark tile boundary.
4. Used image luminance as an approximate height field.
5. Recoloured the texture using the original drape's mean green.
6. Exported colour, roughness and tangent-space tuft-normal textures.

The reference copy, crop coordinates and source/texture hashes are recorded in
the study and asset metadata. The original photograph and hospital USD package
were not overwritten.

### Applied Settings

| Setting | Current value |
| --- | --- |
| New colour, roughness and tuft-normal textures | 512 x 512 each |
| Estimated tile span | 12 mm |
| Height amplitude used to derive bump detail | 0.12 mm |
| Bump/normal strength | 0.65 |
| Tabletop UV repeats | Approximately 272.26 x 173.17 |
| Original crease-normal atlas | 4096 x 2048, retained |
| Episode mean roughness | Existing sampled range of 0.76-0.88 |
| Roughness texture blend | 30%, adjusted to preserve the sampled mean |
| Specular level | 0.35 |

In Blender, a Bump node layers the photo-derived height over the original crease
normal. In Isaac, an OmniPBR material combines the tiled tuft normals with the
original crease map through independent UV transforms. Normal-map roughness
filtering is enabled, and the OpenGL tangent convention is explicit.

The crease PNG was extracted byte for byte from the hospital USD package because
the MDL texture loader could not read its package-member path. Both rendering
paths share that extracted file. The universal USD preview surface remains as
a fallback with the colour/roughness maps and original crease normals.

Only the selected drape material changes. Other tables, blue pads and tool
materials retain their existing appearance. The cloth mesh, UVs, transforms,
collision geometry, physical parameters, lights and production cameras remain
unchanged by this cloth pass.

### Main Files

| File or directory | Purpose |
| --- | --- |
| [microfiber.blend](../exports/blender_microfiber_20261027/microfiber.blend) | Blender study; active scene is `07 Reference Microfiber` |
| [blender_microfiber](../assets/blender_microfiber/) | Runtime textures and material metadata |
| [material.json](../assets/blender_microfiber/material.json) | Parameters, reference provenance and asset hashes |
| [blender_microfiber_material.py](../scripts/blender_microfiber_material.py) | Recreates the photo-derived maps and Blender study |
| [cloth_materials.py](../env/cloth_materials.py) | Applies texture tiling and the layered Isaac material |
| [domain_randomization.py](../src/recorder/domain_randomization.py) | Retains episode colour and mean-roughness variation |
| [phase4_scene.py](../env/phase4_scene.py) | Records active material contracts and asset hashes |

Previous contracts: `blender_microfiber_v2` for the cloth and
`satin_steel_microfiber_drape_v4` for the overall material pass. The current
contracts are `new_env_reference_cloth_v1` and `matched_satin_steel_new_env_cloth_v6`.

## 5. Validation Completed

Ten targeted offline material/normal tests passed. They cover unchanged source
assets and geometry, isolation from other tables, repeat application, texture
hashes, valid decoded tuft normals, independent tuft/crease UV scales, correct
normal colour space, byte-identical crease extraction and preserved sampled
mean roughness.

Blender comparisons use matched geometry, lighting and camera settings, rendered
directly at 448 pixels. Isaac comparisons include all six unchanged production
camera views and one separate temporary 448 x 448 macro camera.

The final Isaac comparison switches the drape between two separate, immutable
material graphs. This avoids a renderer cache issue encountered when changing
the render context of an existing material. Scene hashes verify that geometry,
transforms, body/joint states, cameras, lights and shader graphs remain fixed;
only the selected cloth's material binding changes between captures.

The macro-view mean absolute RGB difference is 5.257 out of 255, compared with
0.574 for repeated captures of the new material. This confirms a visible change
beyond repeated-frame rendering noise; it does not measure physical realism.

- [Isaac close-up comparison](../exports/blender_microfiber_20261027/isaac_comparison/comparison_cloth_closeup.png)
- [Isaac right-camera comparison](../exports/blender_microfiber_20261027/isaac_comparison/comparison_cam_right.png)
- [Isaac comparison manifest](../exports/blender_microfiber_20261027/isaac_comparison/manifest.json)
- [Material tests](../tests/test_scene_materials.py)

The successful preview provides `Previous weave` and `Photo microfiber` buttons
and leaves the microfiber material selected. Rejected draft and failed diagnostic
directories are retained separately and do not represent the applied material.

## 6. Resolution and Memory

The earlier 896-pixel rendering experiment was reverted at the user's request.
Production uses the original 448/224 modes. Earlier downsampled comparison images
remain as diagnostics; downsampling after rendering does not eliminate the cost
of larger render buffers.

The current cloth uses three small new maps plus its original crease atlas.
At RGBA8 base level, this is approximately 35 MiB, versus 34 MiB for the preceding
weave and 96 MiB for the original three large atlases. These are texture-size
estimates, excluding mipmaps, compression, format conversion and caching.
Total application RAM/VRAM and performance have not been benchmarked.

## 7. Discussed but Not Applied

The online microfiber guide was reviewed. Its sheen recommendation addresses
soft fibre scattering that the current bump-based material does not reproduce.
Suggested next comparisons are:

- Principled Sheen Weight at 0.25, 0.5 and 1.0 under identical lighting.
- Sheen Roughness around 0.7-0.9.
- A much weaker noise-driven bump layer for fine loose-fibre variation.
- Subtle wave detail only if it improves the reference match without moire.

These sheen and additional procedural layers have not been applied. Blender
Principled sheen also needs explicit translation to a suitable Isaac material;
the current OmniPBR surface does not reproduce that cloth-sheen component.
Noise belongs in a Bump node's Height input; an RGB tangent-space normal texture
belongs in a Normal Map node. Procedural scale must be chosen in relation to
physical size rather than copied directly from a guide.

Adaptive subdivision and displacement were not selected for this pass because
the mesh already supplies folds and the goal was to limit geometry and memory
cost. Individual fibre geometry and fuzzy silhouettes are not implemented.

## Limits

The reference has no ruler, so fibre scale and relief are estimated. Photograph
brightness approximates height and is not a measured surface scan. Bump maps do
not reproduce individual hair silhouettes or true fuzz scattering. Fine detail
softens in wide views. Validation is for RGB appearance; no complete training
episode or semantic-capture validation was performed in these material previews.

For the longer technical history, see [SIMULATION_REALISM.md](SIMULATION_REALISM.md).
