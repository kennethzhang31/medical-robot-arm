"""Create portable fibre maps and a matched study on the real Blender drape.

Run in Blender with the existing instrument material study loaded.
"""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports/blender_cloth_20261027'
ASSETS = ROOT / 'assets/blender_cloth'
TILE_METRES = .0104
UV_METRES = (3.26709, 2.07803)
REPEATS = tuple(length / TILE_METRES for length in UV_METRES)


def fibre_maps(source):
    size, yarns = 512, 16
    v, u = np.mgrid[:size, :size].astype(np.float32) * (yarns / size)
    # Uneven yarn spacing avoids a mechanically regular screen-door pattern.
    u, v = (u + .14 * np.sin(6 * np.pi * u / yarns) + .09 * np.sin(10 * np.pi * u / yarns)
            + .05 * np.sin(4 * np.pi * v / yarns),
            v + .17 * np.sin(8 * np.pi * v / yarns) + .08 * np.sin(14 * np.pi * v / yarns)
            + .06 * np.sin(6 * np.pi * u / yarns))
    # Alternating warp/weft crowns, with much smaller longitudinal filaments.
    warp = (.5 + .5 * np.cos(2 * np.pi * u)) ** 1.3
    weft = (.5 + .5 * np.cos(2 * np.pi * v)) ** 1.3
    over = .5 + .5 * np.cos(np.pi * u) * np.cos(np.pi * v)
    height = .000032 * (warp * (.35 + .65 * over) + weft * (1 - .65 * over))
    fibres = (np.cos(2 * np.pi * (5 * u + .07 * np.sin(2 * np.pi * v / yarns))) * warp * over
              + np.cos(2 * np.pi * (5 * v + .07 * np.sin(2 * np.pi * u / yarns))) * weft * (1 - over))
    height += .0000007 * fibres
    height *= 1 + .06 * np.sin(2 * np.pi * u / yarns) * np.cos(4 * np.pi * v / yarns)
    relief = height / .000032
    roughness = np.clip(.5 + .14 * (relief - .7) + .04 * fibres, 0, 1)
    assert np.isfinite(roughness).all()
    # The analytic pattern is periodic; boundary gradients must be ordinary.
    for axis in (0, 1):
        seam = np.abs(np.take(roughness, 0, axis) - np.take(roughness, -1, axis)).max()
        assert seam <= np.abs(np.diff(roughness, axis=axis)).max() * 1.1
    images = {}
    data_space = next(n.image.colorspace_settings.name for n in source.node_tree.nodes
                      if n.type == 'TEX_IMAGE' and 'normal' in n.image.name)
    base = next(n.image for n in source.node_tree.nodes if n.type == 'TEX_IMAGE' and 'basecolor' in n.image.name)
    pixels = np.empty(base.size[0] * base.size[1] * 4, dtype=np.float32)
    base.pixels.foreach_get(pixels)
    green = pixels.reshape(-1, 4)[:, :3].mean(axis=0, dtype=np.float64)
    shade = 1 + .045 * (relief - relief.mean()) + .010 * fibres
    for name, rgb in [('basecolor', np.clip(green * shade[:, :, None], 0, 1)),
                      ('roughness', np.repeat(roughness[:, :, None], 3, axis=2))]:
        image = bpy.data.images.new('Cloth fibres ' + name, width=size, height=size, alpha=False)
        image.colorspace_settings.name = base.colorspace_settings.name if name == 'basecolor' else data_space
        rgba = np.ones((size, size, 4), dtype=np.float32)
        rgba[:, :, :3] = rgb
        image.pixels.foreach_set(rgba.ravel())
        image.filepath_raw = str(ASSETS / (name + '.png'))
        image.file_format = next(i.identifier for i in image.bl_rna.properties['file_format'].enum_items
                                 if i.name.startswith('PNG'))
        image.save()
        image.pack()
        images[name] = image
    return images


def material(source, label, images=None):
    mat = source.copy()
    mat.name = label
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    uv = next(n for n in nodes if n.type == 'UVMAP')
    color = next(n for n in nodes if n.type == 'TEX_IMAGE' and 'basecolor' in n.image.name)
    rough = next(n for n in nodes if n.type == 'TEX_IMAGE' and 'roughness' in n.image.name)
    # Match the runtime material, without the earlier Blender-only green tint.
    links.new(color.outputs['Color'], surface.inputs['Base Color'])
    next(n for n in nodes if n.type == 'NORMAL_MAP').inputs['Strength'].default_value = 1
    ramp = nodes.new('ShaderNodeMath')
    ramp.operation = next(i.identifier for i in ramp.bl_rna.properties['operation'].enum_items
                          if i.name == 'Multiply Add')
    links.new(rough.outputs['Color'], ramp.inputs[0])
    ramp.inputs[1].default_value = .12
    ramp.inputs[2].default_value = .76
    links.new(ramp.outputs[0], surface.inputs['Roughness'])
    if images:
        mapping = nodes.new('ShaderNodeVectorMath')
        mapping.operation = next(i.identifier for i in mapping.bl_rna.properties['operation'].enum_items
                                 if i.name == 'Multiply')
        mapping.label = 'Measured tabletop UV density: 0.65 mm yarn pitch'
        mapping.inputs[1].default_value = (*REPEATS, 1)
        links.new(uv.outputs['UV'], mapping.inputs[0])
        for node, name in ((color, 'basecolor'), (rough, 'roughness')):
            node.image = images[name]
            node.extension = next(i.identifier for i in node.bl_rna.properties['extension'].enum_items
                                  if i.name == 'Repeat')
            links.new(mapping.outputs['Vector'], node.inputs['Vector'])
    return mat


def study_scene(source, drape, label, mat):
    scene = bpy.data.scenes.new(label)
    obj = drape.copy()
    obj.data = drape.data.copy()
    obj.parent = None
    obj.matrix_world = drape.matrix_world.copy()
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    scene.collection.objects.link(obj)
    for light in source.objects:
        if light.type == 'LIGHT':
            scene.collection.objects.link(light.copy())
    data = bpy.data.cameras.new(label + ' Camera')
    data.clip_start = .001
    data.lens = 60
    cam = bpy.data.objects.new(label + ' Camera', data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.world = source.world
    scene.render.engine = source.render.engine
    scene.cycles.device = source.cycles.device
    scene.cycles.samples = 96
    scene.cycles.seed = 17
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = 448
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = source.view_settings.view_transform
    scene.view_settings.exposure = source.view_settings.exposure
    scene.view_settings.gamma = source.view_settings.gamma
    return scene


def frame(scene, close):
    target = Vector((.15, -.42, -.004))
    scene.camera.location = target + Vector((.012, -.026, .045) if close else (.17, -.28, .42))
    scene.camera.rotation_euler = (target - scene.camera.location).to_track_quat('-Z', 'Y').to_euler()


def main():
    assert not (OUT / 'cloth_fibres.blend').exists(), 'Use a new version; do not overwrite an edited study'
    assert not ASSETS.exists(), 'Do not overwrite exported materials'
    source = bpy.data.scenes['03 Instrument Finish Comparison']
    drape = next(o for o in source.objects if o.type == 'MESH' and o.name.startswith('Green_Drape'))
    original_file = bpy.data.filepath
    source_hash = hashlib.sha256((ROOT / 'assets/hospital_isaac.usdz').read_bytes()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True)
    images = fibre_maps(drape.data.materials[0])
    scenes = [study_scene(source, drape, '06 Cloth Original', material(drape.data.materials[0], 'Cloth Original')),
              study_scene(source, drape, '06 Cloth Fibres', material(drape.data.materials[0], 'Cloth Fibres', images))]
    for scene, name in zip(scenes, ('original', 'fibres')):
        obj = next(o for o in scene.objects if o.type == 'MESH')
        assert obj.matrix_world == drape.matrix_world
        assert [v.co[:] for v in obj.data.vertices] == [v.co[:] for v in drape.data.vertices]
        assert [p.vertices[:] for p in obj.data.polygons] == [p.vertices[:] for p in drape.data.polygons]
        assert [v.uv[:] for v in obj.data.uv_layers.active.data] == [v.uv[:] for v in drape.data.uv_layers.active.data]
        for close in (False, True):
            frame(scene, close)
            scene.render.filepath = str(OUT / (name + ('_close.png' if close else '_context.png')))
            bpy.ops.render.render(scene=scene.name, write_still=True)
    assert hashlib.sha256((ROOT / 'assets/hospital_isaac.usdz').read_bytes()).hexdigest() == source_hash
    manifest = dict(contract='blender_cloth_fibres_v1', tile_metres=TILE_METRES,
                    yarn_pitch_mm=.65, yarns_per_tile=16, texture_size=[512, 512],
                    uv_metres=UV_METRES, uv_repeats=REPEATS,
                    source_file=original_file, source_hospital_sha256=source_hash,
                    geometry='Unchanged points, faces, UVs, transforms; no displacement or subdivision',
                    material='Source mean green and crease normal map retained; tiled fibre colour and roughness',
                    limitations='Fine fibres soften under minification. Not photo calibrated.',
                    asset_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS.glob('*.png')})
    (ASSETS / 'material.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    bpy.context.window.scene = scenes[1]
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            region = area.spaces.active.region_3d
            region.view_perspective = next(i.identifier for i in region.bl_rna.properties['view_perspective'].enum_items
                                           if i.name == 'Camera')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'cloth_fibres.blend'))
    print('CLOTH_FIBRES_PASSED', json.dumps(manifest))


if __name__ == '__main__':
    main()
