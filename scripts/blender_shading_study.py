"""Asset-only shading study; fixed 448 renders, original meshes remain intact."""
import hashlib
import json
import math
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports/blender_shading_20261026'


def signature(obj):
    mesh = obj.data
    digest = hashlib.sha256()
    digest.update(np.asarray([tuple(v.co) for v in mesh.vertices], dtype=np.float32).tobytes())
    digest.update(str([tuple(p.vertices) for p in mesh.polygons]).encode())
    digest.update(np.asarray([tuple(n.vector) for n in mesh.corner_normals], dtype=np.float32).tobytes())
    return digest.hexdigest()


def activate(scene, obj):
    bpy.context.window.scene = scene
    for other in scene.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def make_scene(source, original, label, corrected=False, bevel=False):
    scene = bpy.data.scenes.new(label)
    bpy.context.window.scene = scene
    obj = original.copy()
    obj.data = original.data.copy()
    obj.parent = None
    obj.matrix_world = original.matrix_world.copy()
    scene.collection.objects.link(obj)
    corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    center = sum(corners, Vector()) / 8
    obj.location.x -= center.x
    obj.location.y -= center.y
    obj.location.z -= min(v.z for v in corners)
    activate(scene, obj)
    before = dict(vertices=len(obj.data.vertices), triangles=len(obj.data.polygons))
    bounds_before = list(obj.dimensions)
    if corrected:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        custom = obj.data.attributes.get('custom_normal')
        if custom:
            obj.data.attributes.remove(custom)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        # Weld coincident export seams only; the tolerance is ten nanometres.
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-8)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = edge.is_manifold and edge.calc_face_angle(0.) < math.radians(45.)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        if bevel:
            modifier = obj.modifiers.new('Small manufactured edge radius', 'BEVEL')
            modifier.width = .000075
            modifier.segments = 2
            modifier.limit_method = next(i.identifier for i in modifier.bl_rna.properties['limit_method'].enum_items
                                         if i.name == 'Angle')
            modifier.angle_limit = math.radians(45.)
            modifier.use_clamp_overlap = True
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        modifier = obj.modifiers.new('Area weighted corner normals', 'WEIGHTED_NORMAL')
        modifier.keep_sharp = True
        modifier.weight = 50
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        if not bevel:
            assert len(obj.data.polygons) == before['triangles'], 'Normal cleanup changed face count'
        assert np.allclose(obj.dimensions, bounds_before, atol=.00016), 'Unexpected silhouette-size change'
    obj.data.calc_loop_triangles()
    after = dict(vertices=len(obj.data.vertices), faces=len(obj.data.polygons),
                 triangles=len(obj.data.loop_triangles))
    for light in source.objects:
        if light.type == 'LIGHT':
            copy = light.copy()
            copy.data = light.data.copy()
            scene.collection.objects.link(copy)
    camera_data = bpy.data.cameras.new(label + ' Camera')
    camera_data.type = next(i.identifier for i in camera_data.bl_rna.properties['type'].enum_items if i.name == 'Orthographic')
    camera_data.ortho_scale = .175
    camera_data.clip_start = .001
    camera_obj = bpy.data.objects.new(label + ' Camera', camera_data)
    scene.collection.objects.link(camera_obj)
    camera_obj.location = (0., -.055, .36)
    camera_obj.rotation_euler = (Vector((0., 0., .003)) - camera_obj.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera_obj
    mesh = bpy.data.meshes.new(label + ' Background')
    mesh.from_pydata([(-1.,-1.,-.0005),(1.,-1.,-.0005),(1.,1.,-.0005),(-1.,1.,-.0005)], [], [(0,1,2,3)])
    background = bpy.data.objects.new(label + ' Background', mesh)
    scene.collection.objects.link(background)
    material = bpy.data.materials.new(label + ' Matte green')
    material.use_nodes = True
    node = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    node.inputs['Base Color'].default_value = (.025, .14, .065, 1.)
    node.inputs['Roughness'].default_value = .85
    mesh.materials.append(material)
    scene.world = source.world
    scene.render.engine = source.render.engine
    scene.cycles.device = source.cycles.device
    scene.cycles.samples = 128
    scene.cycles.seed = 17
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = 448
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = source.render.image_settings.file_format
    scene.view_settings.view_transform = source.view_settings.view_transform
    scene.view_settings.look = source.view_settings.look
    scene.view_settings.exposure = source.view_settings.exposure
    scene.view_settings.gamma = source.view_settings.gamma
    scene['scope'] = 'Blender-only visual study. No camera/recorder/physics changes or source asset replacement.'
    scene['tool_object'] = obj.name
    return scene, dict(before=before, after=after, corrected_normals=corrected,
                       bevel_m=.000075 if bevel else 0., dimensions_before=bounds_before,
                       dimensions_after=list(obj.dimensions))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'shading_study.blend').exists():
        raise FileExistsError('Refusing to replace an existing study')
    source = bpy.data.scenes['03 Instrument Finish Comparison']
    tools = dict(scissor=next(o for o in source.objects if o.name.startswith('Surgical_scissors')),
                 retractor=next(o for o in source.objects if o.name.startswith('Object_62')))
    signatures = {name:signature(obj) for name,obj in tools.items()}
    results = {}
    for name, obj in tools.items():
        for variant, corrected, bevel in (('imported',False,False), ('normals',True,False), ('bevel',True,True)):
            scene, report = make_scene(source,obj,'04 ' + name + ' ' + variant,corrected,bevel)
            results[name + '_' + variant] = report
            scene.render.filepath = str(OUT/(name + '_' + variant + '.png'))
    assert signatures == {name:signature(obj) for name,obj in tools.items()}, 'Original study changed'
    (OUT/'manifest.json').write_text(json.dumps(dict(source_signatures=signatures,variants=results,
        resolution=[448,448],samples=128,seed=17,scope='Visual mesh copies in Blender only'),indent=2),encoding='utf-8')
    bpy.context.window.scene = bpy.data.scenes['04 scissor normals']
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shading_study.blend'))
    print('BLENDER_SHADING_STUDY_READY', json.dumps(results))


if __name__ == '__main__':
    main()
