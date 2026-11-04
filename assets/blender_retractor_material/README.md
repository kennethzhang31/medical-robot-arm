# Blender Love Retractor Material

`love_retractor.usda` is the actual UsdPreviewSurface material exported by
Blender from `exports/instrument_finish_20261025/instrument_finish.blend`,
scene `03 Instrument Finish Comparison`, material `instrumenty.008`.
The library contains no mesh, transforms, lights, cameras or physics.

`env/instrument_materials.py` references this library and binds it to every
spawned Love retractor, including clutter copies. Generic steel tuning is
bypassed for these tools, so it cannot overwrite the Blender values.
Other instruments retain their existing material handling.

The source is a constant steel shader: color `(0.48, 0.50, 0.52)`, metallic
`0.95`, roughness `0.52`, IOR `1.5`. These match the previous runtime steel
values; importing them does not establish a fix for real-time reflection
rippling. Rendering remains real-time RTX. Original geometry, mesh normals,
physics, tool placement and source assets are preserved.

Re-export after editing the finished Blender material:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup exports/instrument_finish_20261025/instrument_finish.blend --python scripts/export_blender_retractor_material.py
```

`manifest.json` records the source file and material hashes and exported
values. The export script verifies Blender and USD values agree and never
saves over the source `.blend` file.

Isaac Sim verification completed on 2026-11-04: all three retractors bind the
exported shader with identical input values, original mesh points/topology and
authored normals. The renderer remains `RaytracedLighting`. Nine offline
material tests and the 600-step UR5/hand/tool-placement check pass.
The runtime report and closeup are in
`exports/blender_retractor_material_20261029/`. The closeup still shows rippled
reflections, so this material transfer does not resolve that visual symptom.
