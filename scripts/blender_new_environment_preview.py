"""Render the transferred materials on the previous study's exact drape mesh."""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.blender_cloth_material import study_scene, frame

OUT = ROOT / 'exports/new_env_transfer_20261028'


def main():
    source = bpy.data.scenes['07 Reference Microfiber']
    drape = next(o for o in source.objects if o.type == 'MESH')
    imported = bpy.data.scenes.new('08 Imported cloth graphs')
    bpy.context.window.scene = imported
    bpy.ops.wm.usd_import(filepath=str(OUT / 'cloth_preview.usda'))
    green = next(o for o in imported.objects if o.type == 'MESH' and 'Green_Drape' in o.name)
    scenes = []
    for label, material, name in [('08 Previous microfiber', drape.data.materials[0], 'previous'),
                                   ('08 Incoming woven cloth', green.data.materials[0], 'incoming')]:
        scene = study_scene(source, drape, label, material)
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 32
        scenes.append(scene)
        for close in (False, True):
            frame(scene, close)
            scene.render.filepath = str(OUT / (name + ('_close.png' if close else '_context.png')))
            bpy.ops.render.render(scene=scene.name, write_still=True)

    tools = bpy.data.scenes.new('09 Transferred satin tools')
    bpy.context.window.scene = tools
    bpy.ops.wm.usd_import(filepath=str(ROOT / 'assets/new_environment/instruments.usda'))
    tools.world = source.world
    tools.render.engine = source.render.engine
    tools.cycles.device = 'CPU'
    tools.cycles.samples = 32
    tools.cycles.use_denoising = True
    tools.render.resolution_x = tools.render.resolution_y = 896
    tools.render.resolution_percentage = 100
    tools.view_settings.view_transform = source.view_settings.view_transform
    for obj in source.objects:
        if obj.type == 'LIGHT':
            light = obj.copy()
            light.location += Vector((-2.45, 3.55, .9055))
            tools.collection.objects.link(light)
    plane = bpy.data.meshes.new('Display backing')
    plane.from_pydata([(-3.,3.25,.909),(-1.6,3.25,.909),(-1.6,3.85,.909),(-3.,3.85,.909)], [], [(0,1,2,3)])
    backing = bpy.data.objects.new('Display backing', plane)
    tools.collection.objects.link(backing)
    mat = bpy.data.materials.new('Display muted green')
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (.045,.15,.10,1.)
    bsdf.inputs['Roughness'].default_value = .85
    plane.materials.append(mat)
    camera = bpy.data.objects.new('Tools review camera', bpy.data.cameras.new('Tools review camera'))
    tools.collection.objects.link(camera)
    target = Vector((-2.3,3.55,.910))
    camera.location = target + Vector((0.,-.16,1.8))
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 1.4
    tools.camera = camera
    tools.render.filepath = str(OUT / 'satin_tools.png')
    bpy.ops.render.render(scene=tools.name, write_still=True)
    bpy.data.libraries.write(str(OUT / 'material_transfer.blend'), set(scenes + [tools]), fake_user=True)
    bpy.context.window.scene = scenes[1]
    print('TRANSFER_PREVIEW_COMPLETE', OUT)


if __name__ == '__main__':
    main()
