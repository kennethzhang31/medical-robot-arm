"""Export only the finished Love retractor material from the existing Blender study.

Run with Blender in background mode and instrument_finish.blend loaded.
The temporary carrier mesh is never included in the runtime material library.
"""
import hashlib
import json
from pathlib import Path

import bpy
from pxr import Sdf, Usd, UsdShade


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'exports/instrument_finish_20261025/instrument_finish.blend'
OUT = ROOT / 'assets/blender_retractor_material'


def main():
    assert Path(bpy.data.filepath).resolve() == SOURCE.resolve(), 'Load instrument_finish.blend first'
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    source = bpy.data.scenes['03 Instrument Finish Comparison'].objects['Object_62.002']
    assert len(source.data.materials) == 1
    material = source.data.materials[0]
    surface = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    assert not any(surface.inputs[key].is_linked for key in ('Base Color', 'Metallic', 'Roughness', 'Normal'))
    values = dict(diffuseColor=list(surface.inputs['Base Color'].default_value[:3]),
                  metallic=surface.inputs['Metallic'].default_value,
                  roughness=surface.inputs['Roughness'].default_value)
    OUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.data.scenes.new('Material export only')
    bpy.context.window.scene = scene
    mesh = bpy.data.meshes.new('Temporary material carrier')
    mesh.from_pydata([(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)], [], [(0, 1, 2)])
    carrier = bpy.data.objects.new('Temporary material carrier', mesh)
    scene.collection.objects.link(carrier)
    mesh.materials.append(material)
    carrier.select_set(True)
    bpy.context.view_layer.objects.active = carrier
    temporary = OUT / '_export.usda'
    bpy.ops.wm.usd_export(filepath=str(temporary), selected_objects_only=True,
                          export_materials=True, generate_preview_surface=True,
                          generate_materialx_network=False, export_animation=False,
                          export_lights=False, export_cameras=False)
    exported = Usd.Stage.Open(str(temporary))
    materials = [UsdShade.Material(prim) for prim in exported.Traverse() if prim.IsA(UsdShade.Material)]
    assert len(materials) == 1
    library = Usd.Stage.CreateInMemory()
    path = Sdf.Path('/LoveRetractorSteel')
    assert Sdf.CopySpec(exported.GetRootLayer(), materials[0].GetPath(), library.GetRootLayer(), path)
    library.SetDefaultPrim(library.GetPrimAtPath(path))
    shader, _, _ = UsdShade.Material(library.GetDefaultPrim()).ComputeSurfaceSource()
    assert shader.GetIdAttr().Get() == 'UsdPreviewSurface'
    for key, expected in values.items():
        actual = shader.GetInput(key).Get()
        components = list(actual) if key == 'diffuseColor' else [actual]
        targets = expected if isinstance(expected, list) else [expected]
        assert all(abs(a-b) < 1e-6 for a, b in zip(components, targets)), key
    assert not any(prim.GetTypeName() == 'Mesh' for prim in library.Traverse())
    destination = OUT / 'love_retractor.usda'
    library.GetRootLayer().Export(str(destination))
    manifest = dict(source_blend=str(SOURCE.relative_to(ROOT)).replace('\\', '/'),
                    source_blend_sha256=source_hash, source_scene='03 Instrument Finish Comparison',
                    source_object=source.name, source_material=material.name,
                    blender_version=bpy.app.version_string, shader='UsdPreviewSurface',
                    settings=values, material_sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='ascii')
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash
    temporary.unlink()
    print('BLENDER_MATERIAL_EXPORTED', json.dumps(manifest), flush=True)


if __name__ == '__main__':
    main()
