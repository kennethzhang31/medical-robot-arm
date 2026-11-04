"""Compare portable steel finishes using the real meshes in the Blender study.

Run in Blender with the existing material_study.blend open. A separate scene,
blend file and USD overlays retain the source assets and existing study.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

import bpy
import numpy as np
from pxr import Gf, Sdf, Usd, UsdShade

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports' / 'instrument_finish_20261025'
PROMPT = 'Portable satin steel; no procedural bump, anisotropy or geometry changes'


def export_usd():
    """Reference source physics/geometry and author only portable material inputs."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'compat'))
    from env.instrument_materials import INSTRUMENT_MATERIAL_OVERRIDES, tune_steel_materials
    from phase3_shared_env_cfg import INSTRUMENTS
    from pxr import UsdGeom

    output = OUT / 'usd'
    output.mkdir(parents=True, exist_ok=True)
    for name, spec in INSTRUMENTS.items():
        source = ROOT / 'assets' / spec.usd
        original = Usd.Stage.Open(str(source))
        source_root = original.GetDefaultPrim()
        destination = output / (name + '.usda')
        stage = Usd.Stage.CreateInMemory()
        root = stage.DefinePrim(str(source_root.GetPath()))
        root.GetReferences().AddReference(str(source))
        stage.SetDefaultPrim(root)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.GetStageUpAxis(original))
        UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.GetStageMetersPerUnit(original))
        tune_steel_materials(root, retractor=name == 'love_retractor', normalize_steel=True)
        if name in INSTRUMENT_MATERIAL_OVERRIDES:
            finish = INSTRUMENT_MATERIAL_OVERRIDES[name]
            material = UsdShade.Material.Define(stage, str(root.GetPath()) + '/Finish/Steel')
            shader = UsdShade.Shader.Define(stage, str(material.GetPath()) + '/Surface')
            shader.CreateIdAttr('UsdPreviewSurface')
            shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*finish.diffuse_color))
            shader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(finish.metallic)
            shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(finish.roughness)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
            UsdShade.MaterialBindingAPI.Apply(root).Bind(material)
        stage.GetRootLayer().UpdateCompositionAssetDependency(
            str(source), Path(os.path.relpath(source, output)).as_posix())
        stage.GetRootLayer().Export(str(destination))
        # An overlay must preserve source topology, normals, transforms and physics.
        reopened = Usd.Stage.Open(str(destination))
        for prim in Usd.PrimRange(source_root):
            composed = reopened.GetPrimAtPath(prim.GetPath())
            assert composed, str(prim.GetPath())
            schemas = lambda p: [s for s in p.GetAppliedSchemas() if s != 'MaterialBindingAPI']
            assert schemas(prim) == schemas(composed), str(prim.GetPath())
            for attr in prim.GetAttributes():
                if attr.GetName().startswith(('inputs:', 'outputs:')):
                    continue
                actual = composed.GetAttribute(attr.GetName())
                assert actual.Get() == attr.Get(), str(attr.GetPath())
                assert actual.GetConnections() == attr.GetConnections(), str(attr.GetPath())
                for time in attr.GetTimeSamples():
                    assert actual.Get(time) == attr.Get(time), str(attr.GetPath())
            for rel in prim.GetRelationships():
                assert composed.GetRelationship(rel.GetName()).GetTargets() == rel.GetTargets(), str(rel.GetPath())
            if prim.IsA(UsdGeom.Mesh):
                material, _ = UsdShade.MaterialBindingAPI(composed).ComputeBoundMaterial()
                assert material, str(prim.GetPath())
                surface, _, _ = material.ComputeSurfaceSource()
                assert surface, str(material.GetPath())
                minimum = .40 if 'Blade' in str(surface.GetPath()) else .52
                assert surface.GetInput('roughness').Get() >= minimum - 1e-6, str(surface.GetPath())
        print('USD_VALIDATED', destination.name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'instrument_finish.blend').exists():
        raise FileExistsError('Refusing to overwrite an existing Blender edit')
    source = bpy.data.scenes['02 Satin Study']
    scene = bpy.data.scenes.new('03 Instrument Finish Comparison')
    bpy.context.window.scene = scene
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT / 'assets').glob('*.usd*')}
    for obj in source.objects:
        if obj.type not in {'MESH', 'LIGHT', 'CAMERA'}:
            continue
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.parent = None
        copy.matrix_world = obj.matrix_world.copy()
        scene.collection.objects.link(copy)
        if obj == source.camera:
            scene.camera = copy
        if obj.type == 'MESH':
            for i, material in enumerate(copy.data.materials):
                if not material:
                    continue
                material = material.copy()
                copy.data.materials[i] = material
                for node in material.node_tree.nodes if material.node_tree else []:
                    if node.type == 'BSDF_PRINCIPLED':
                        anisotropy = node.inputs.get('Anisotropic') or node.inputs.get('Anisotropic IOR Level')
                        if anisotropy:
                            anisotropy.default_value = 0.
            a = np.array([tuple(v.co) for v in obj.data.vertices])
            b = np.array([tuple(v.co) for v in copy.data.vertices])
            assert np.array_equal(a, b), obj.name
            assert obj.matrix_world == copy.matrix_world, obj.name
    scene.world = source.world.copy()
    scene.render.engine = source.render.engine
    scene.cycles.samples = 96
    scene.cycles.seed = 17
    scene.cycles.use_denoising = True
    scene.cycles.device = source.cycles.device
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = source.render.image_settings.file_format
    scene.view_settings.view_transform = source.view_settings.view_transform
    scene.view_settings.look = source.view_settings.look
    scene.view_settings.exposure = source.view_settings.exposure
    scene.view_settings.gamma = source.view_settings.gamma
    # Same camera, lights, geometry, seed and color management for both renders.
    scene.render.filepath = str(OUT / 'before.png')
    bpy.ops.render.render(write_still=True)
    changes = []
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.name.startswith(('Cube_259', 'FOF_', 'Green_', 'Left_')):
            continue
        for material in obj.data.materials:
            for node in material.node_tree.nodes if material and material.node_tree else []:
                if node.type != 'BSDF_PRINCIPLED' or node.inputs['Metallic'].default_value < .5:
                    continue
                roughness = node.inputs['Roughness']
                if roughness.is_linked:
                    continue
                value = .40 if material.name.startswith('Blade') else .52
                changes.append(dict(object=obj.name, material=material.name,
                                    before=roughness.default_value, after=value))
                roughness.default_value = max(roughness.default_value, value)
    scene.render.filepath = str(OUT / 'after.png')
    bpy.ops.render.render(write_still=True)
    scene['finish_notes'] = PROMPT
    scene['validation'] = 'Matched Blender comparison; not an Isaac sensor capture'
    assert source_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (ROOT / 'assets').glob('*.usd*')}
    (OUT / 'manifest.json').write_text(json.dumps(dict(
        source_sha256=source_hashes, changes=changes, validation=scene['validation'],
        geometry='Identical vertices, topology, imported normals and world transforms',
        comparison='Both images disable Blender-only anisotropy; roughness is the only difference',
    ), indent=2) + '\n', encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'instrument_finish.blend'))
    export_usd()
    print('FINISH_READY', str(OUT), len(changes), 'material updates')


if __name__ == '__main__':
    main()
