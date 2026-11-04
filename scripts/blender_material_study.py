"""Build a separate Blender material study from the real simulation assets.

Run inside Blender's Python console or through Blender MCP:
    exec(compile(open(script_path).read(), script_path, 'exec'))

The original Blender scene and source USD files are retained. Generated USDs
contain the portable runtime finishes; Blender adds a small anisotropy study.
"""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports' / 'blender_material_study_20261021'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'compat'))
from env.instrument_materials import INSTRUMENT_MATERIAL_OVERRIDES, tune_steel_materials
from phase3_shared_env_cfg import INSTRUMENTS
from src.recorder.domain_randomization import apply_background


def bounds(prim):
    # Some authored extents are stale; seat the actual vertices above the cloth.
    low, high = np.full(3, np.inf), np.full(3, -np.inf)
    for child in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()):
        if not child.IsA(UsdGeom.Mesh):
            continue
        points = np.asarray(UsdGeom.Mesh(child).GetPointsAttr().Get(), dtype=float)
        if not len(points):
            continue
        matrix = np.asarray(UsdGeom.Xformable(child).ComputeLocalToWorldTransform(0))
        world = points @ matrix[:3, :3] + matrix[3, :3]
        low, high = np.minimum(low, world.min(axis=0)), np.maximum(high, world.max(axis=0))
    assert np.isfinite(low).all(), 'No mesh points under ' + str(prim.GetPath())
    return Gf.Range3d(Gf.Vec3d(*low), Gf.Vec3d(*high))


def make_stage(path, tuned):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    root = UsdGeom.Xform.Define(stage, '/Study').GetPrim()
    stage.SetDefaultPrim(root)
    table = UsdGeom.Xform.Define(stage, '/Study/Furniture/Table_04')
    table.GetPrim().GetReferences().AddReference(
        str(ROOT / 'assets/hospital_isaac.usdz'), '/HospitalScene/Furniture/Table_04')
    # Replace the hospital placement with the runtime table-relative frame.
    xf = UsdGeom.Xformable(table)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(.15, 0., -.9055))
    xf.AddRotateZOp().Set(90.)
    stage.OverridePrim('/Study/Furniture/Table_04/Collisions').SetActive(False)
    while True:
        instance = next((p for p in Usd.PrimRange(table.GetPrim(), Usd.TraverseInstanceProxies())
                         if p.IsInstance()), None)
        if instance is None:
            break
        instance.SetInstanceable(False)
    if tuned:
        apply_background(stage, {'selected_table': 'Table_04'},
                         {'color': [.045, .24, .13], 'roughness': .82}, root=root)
    for index, (name, spec) in enumerate(INSTRUMENTS.items()):
        parent = UsdGeom.Xform.Define(stage, '/Study/Tools/' + name)
        translation = parent.AddTranslateOp()
        translation.Set(Gf.Vec3d(0.))
        parent.AddRotateXYZOp().Set(Gf.Vec3f(90., 0., 90. if name == 'scalpel_type2' else 0.))
        parent.AddScaleOp().Set(Gf.Vec3f(*spec.scale))
        asset = stage.DefinePrim(str(parent.GetPath()) + '/Asset')
        asset.GetReferences().AddReference(str(ROOT / 'assets' / spec.usd))
        if tuned:
            tune_steel_materials(asset, retractor=name == 'love_retractor', normalize_steel=True)
        # Scissors are unbound in the source; use the recorder fallback in both scenes.
        if name in INSTRUMENT_MATERIAL_OVERRIDES:
            spec_mat = INSTRUMENT_MATERIAL_OVERRIDES[name]
            mat = UsdShade.Material.Define(stage, '/Study/Looks/ScissorSteel')
            shader = UsdShade.Shader.Define(stage, '/Study/Looks/ScissorSteel/Surface')
            shader.CreateIdAttr('UsdPreviewSurface')
            shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*spec_mat.diffuse_color))
            shader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(spec_mat.metallic)
            shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(spec_mat.roughness)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
            UsdShade.MaterialBindingAPI.Apply(asset).Bind(mat)
        box = bounds(parent.GetPrim())
        center = (box.GetMin() + box.GetMax()) / 2
        translation.Set(Gf.Vec3d(-.13 + index * .14 - center[0], -.18 - center[1], .0005 - box.GetMin()[2]))
        size = bounds(parent.GetPrim()).GetSize()
        assert .10 < max(size) < .20, (name, size)
    tray = UsdGeom.Xform.Define(stage, '/Study/Tray')
    tray_pos = tray.AddTranslateOp()
    tray_pos.Set(Gf.Vec3d(0.))
    tray.AddRotateZOp().Set(90.)
    tray_asset = stage.DefinePrim('/Study/Tray/Asset')
    tray_asset.GetReferences().AddReference(str(ROOT / 'assets/SurgicalTray.usd'))
    source_tray = Usd.Stage.Open(str(ROOT / 'assets/SurgicalTray.usd'))
    original = bounds(source_tray.GetDefaultPrim())
    tray.AddScaleOp().Set(Gf.Vec3f(.22 / original.GetSize()[0], .55 / original.GetSize()[1], .0025))
    if tuned:
        tune_steel_materials(tray_asset, minimum_roughness=0.40)
    box = bounds(tray.GetPrim())
    center = (box.GetMin() + box.GetMax()) / 2
    tray_pos.Set(Gf.Vec3d(.15 - center[0], -.89 - center[1], .001 - box.GetMin()[2]))
    # A missing source atlas otherwise makes Blender abort the entire import.
    for prim in stage.Traverse():
        if prim.IsA(UsdShade.Shader) and prim.GetAttribute('info:id').Get() == 'UsdUVTexture':
            texture = UsdShade.Shader(prim).GetInput('file')
            asset_path = texture.Get() if texture else None
            if asset_path and asset_path.path and not asset_path.resolvedPath:
                print('MISSING_TEXTURE_FALLBACK', str(prim.GetPath()), asset_path.path)
                texture.Set(Sdf.AssetPath(''))
    stage.GetRootLayer().Save()
    return stage


def camera(scene, name, position, target, lens):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = .001
    data.clip_end = 50.
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    return obj


def area(scene, name, position, target, power, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.shape = next(i.identifier for i in data.bl_rna.properties['shape'].enum_items if i.name == 'Rectangle')
    data.size = size
    data.size_y = size * .6
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def import_scene(path, label, tuned):
    scene = bpy.data.scenes.new(label)
    bpy.context.window.scene = scene
    props = bpy.ops.wm.usd_import.get_rna_type().properties
    packed = next(item.identifier for item in props['import_textures_mode'].enum_items if item.name == 'Packed')
    unique = next(item.identifier for item in props['mtl_name_collision_mode'].enum_items if item.name == 'Make Unique')
    bpy.ops.wm.usd_import(filepath=str(path), import_cameras=False, import_lights=False,
                         import_shapes=False, import_textures_mode=packed,
                         mtl_name_collision_mode=unique, support_scene_instancing=False)
    meshes = [o for o in scene.objects if o.type == 'MESH']
    assert len(meshes) >= 10, 'Expected actual table, tray and all five tools'
    if tuned:
        for mat in {m for obj in meshes for m in obj.data.materials if m}:
            if not mat.node_tree:
                continue
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            if mat.name.startswith('Drape_Green_Woven_PBR'):
                surface = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
                color = surface.inputs['Base Color']
                source = color.links[0].from_socket
                tint = nodes.new('ShaderNodeHueSaturation')
                tint.label = 'Provisional cloth color; match to workspace photos'
                tint.inputs['Saturation'].default_value = .65
                tint.inputs['Value'].default_value = .72
                links.new(source, tint.inputs['Color'])
                links.new(tint.outputs['Color'], color)
                for node in nodes:
                    if node.type == 'NORMAL_MAP':
                        node.inputs['Strength'].default_value = .45
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED' and node.inputs['Metallic'].default_value >= .5:
                    # Blender-only experiment; UsdPreviewSurface has no anisotropy input.
                    socket = node.inputs.get('Anisotropic') or node.inputs.get('Anisotropic IOR Level')
                    if socket is None:
                        raise RuntimeError('Principled shader has no anisotropy input')
                    socket.default_value = .18
    world = bpy.data.worlds.new(label + ' World')
    world.use_nodes = True
    background = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    background.inputs['Color'].default_value = (.48, .52, .55, 1.)
    background.inputs['Strength'].default_value = .20
    scene.world = world
    area(scene, 'Ceiling panel', (.25, -.05, 1.4), (.15, -.3, 0.), 18., 1.1, (1., .97, .92))
    area(scene, 'Ceiling fill', (-.45, -.9, 1.1), (.15, -.3, 0.), 9., .8, (.91, .95, 1.))
    area(scene, 'Side reflection', (.85, .25, .8), (.15, -.3, 0.), 5., .6, (1., 1., 1.))
    scene.camera = camera(scene, 'Instrument close-up', (.15, -.65, .9), (.15, -.18, 0.), 45.)
    camera(scene, 'Table overview', (1.55, -2.1, 1.7), (.15, -.15, -.18), 47.)
    try:
        scene.render.engine = 'CYCLES'
    except TypeError as exc:
        raise RuntimeError('This study needs Cycles for steel reflections: ' + str(exc)) from exc
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.cycles.seed = 17
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.get_devices()
    backends = list(dict.fromkeys(d.type for d in prefs.devices if d.type != 'CPU'))
    for backend in reversed(backends):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == backend
        if any(d.use for d in prefs.devices):
            scene.cycles.device = 'GPU'
            break
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    formats = scene.render.image_settings.bl_rna.properties['file_format'].enum_items
    scene.render.image_settings.file_format = next(i.identifier for i in formats if i.name.startswith('PNG'))
    scene.view_settings.exposure = 0.
    scene.view_settings.gamma = 1.
    scene['study_scope'] = 'Actual meshes and runtime scales; arranged for material inspection, no physics or calibrated sensor reproduction.'
    scene['material_source'] = 'Runtime finishes + Blender anisotropy .18; drape saturation .65, value .72, normal strength .45' if tuned else 'Source USD materials; recorder steel fallback for unbound scissors'
    scene['reference_photos'] = 'Pending; provisional appearance, not photograph calibrated'
    scene.view_layers[0].update()
    return scene


def validate_scenes(source, satin):
    def meshes(scene):
        return sorted((o for o in scene.objects if o.type == 'MESH'), key=lambda o: o.name)
    before, after = meshes(source), meshes(satin)
    assert len(before) == len(after)
    for a, b in zip(before, after):
        assert a.name.split('.')[0] == b.name.split('.')[0]
        assert np.allclose(a.matrix_world, b.matrix_world, atol=1e-6), a.name
        assert len(a.data.vertices) == len(b.data.vertices), a.name
        assert len(a.data.polygons) == len(b.data.polygons), a.name
        av = np.empty(len(a.data.vertices) * 3, dtype=np.float32)
        bv = np.empty_like(av)
        a.data.vertices.foreach_get('co', av)
        b.data.vertices.foreach_get('co', bv)
        assert np.array_equal(av, bv), a.name
    assert source.camera.matrix_world == satin.camera.matrix_world
    lights = lambda s: sorted((tuple(o.location), o.data.energy, o.data.size, tuple(o.data.color))
                              for o in s.objects if o.type == 'LIGHT')
    assert lights(source) == lights(satin)
    print('STUDY_CHECKS_PASSED: matching mesh vertices, transforms, cameras and lights')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'material_study.blend').exists():
        raise FileExistsError('Study already exists; use a new output directory rather than overwrite edits.')
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    original_scene = bpy.context.scene
    sources = sorted((ROOT / 'assets').glob('*.usd*'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    scenes = []
    for tuned, name, label in [(False, 'source', '01 Source Materials'), (True, 'satin', '02 Satin Study')]:
        path = OUT / (name + '.usda')
        make_stage(path, tuned)
        scenes.append(import_scene(path, label, tuned))
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    assert original_scene.name in bpy.data.scenes
    validate_scenes(*scenes)
    manifest = dict(source_sha256=hashes, scenes=[s.name for s in scenes],
                    comparison='Source asset finishes vs runtime material pass with provisional Blender cloth/steel refinements',
                    references='No real workspace photographs supplied yet',
                    original_scene=original_scene.name,
                    lighting='Identical broad area lights in both scenes; Blender watts, not Isaac intensity units',
                    limitations=['Material inspection layout, not an Isaac rollout',
                                 'Anisotropy and cloth saturation/value/normal strength are Blender-only; USDs use existing runtime finishes'])
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    text = bpy.data.texts.new('Material Study Notes')
    text.write('Switch scenes: 01 Source Materials / 02 Satin Study.\n'
               'Both use identical lights, camera and geometry.\n'
               'Source = asset materials, not a screenshot of the previous Isaac runtime.\n'
               'Satin = runtime finishes + anisotropy .18; cloth saturation .65, value .72, normal strength .45.\n'
               'Reference photos pending. Source assets and original scene retained.\n')
    for area_ui in bpy.context.screen.areas:
        if area_ui.type == 'VIEW_3D':
            area_ui.spaces.active.region_3d.view_perspective = 'CAMERA'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'material_study.blend'))
    print('STUDY_READY', str(OUT), 'scenes', [s.name for s in scenes])


if __name__ == '__main__':
    main()
