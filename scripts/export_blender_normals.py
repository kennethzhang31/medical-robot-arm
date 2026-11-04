"""Transfer the validated Blender retractor normals without exporting geometry."""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector, kdtree
from pxr import Gf, Usd, UsdGeom, Vt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from env.instrument_normals import CONTRACT, MESH_PATH, NORMALS_FILE, geometry_signature


def main():
    source_file = ROOT/'assets/love_centered_root_at_center.usd'
    original_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    source_stage = Usd.Stage.Open(str(source_file))
    source_mesh = UsdGeom.Mesh(source_stage.GetPrimAtPath('/Object/' + MESH_PATH))
    original = next(o for o in bpy.data.scenes['03 Instrument Finish Comparison'].objects
                    if o.name.startswith('Object_62'))
    cleaned_scene = bpy.data.scenes['04 retractor normals']
    cleaned = bpy.data.objects[cleaned_scene['tool_object']]
    points = np.asarray(source_mesh.GetPointsAttr().Get())
    indices = np.asarray(source_mesh.GetFaceVertexIndicesAttr().Get())
    assert np.array_equal(points, np.asarray([tuple(v.co) for v in original.data.vertices]))
    assert np.array_equal(indices, np.asarray([tuple(p.vertices) for p in original.data.polygons]).reshape(-1))
    assert len(cleaned.data.polygons) == len(original.data.polygons) == 272
    assert not cleaned.modifiers, 'Bake the normals-only modifier before export'

    # The study applied object scale, but retained its rotation. Undo only that
    # scale to match copied/welded vertices to the original USD vertex order.
    scale = np.asarray(original.scale)
    tree = kdtree.KDTree(len(cleaned.data.vertices))
    for vertex in cleaned.data.vertices:
        tree.insert(Vector(np.asarray(vertex.co) / scale), vertex.index)
    tree.balance()
    vertex_map = []
    max_error = 0.
    for point in points:
        _, index, error = tree.find(Vector(point))
        assert error < 2e-6, ('Vertex mapping mismatch', error)
        max_error = max(max_error, error)
        vertex_map.append(index)
    face_map = {}
    for face in cleaned.data.polygons:
        key = tuple(sorted(face.vertices))
        assert key not in face_map, 'Ambiguous coincident faces'
        face_map[key] = {cleaned.data.loops[i].vertex_index: cleaned.data.corner_normals[i].vector.copy()
                         for i in face.loop_indices}
    transform = original.matrix_world.to_3x3().transposed() @ cleaned.matrix_world.to_3x3().inverted().transposed()
    values = []
    for face in original.data.polygons:
        mapped = [vertex_map[i] for i in face.vertices]
        normals = face_map[tuple(sorted(mapped))]
        for index in mapped:
            values.append(tuple((transform @ normals[index]).normalized()))
    values = np.asarray(values, dtype=np.float32)
    assert values.shape == (816, 3) and np.isfinite(values).all()
    assert np.allclose(np.linalg.norm(values, axis=1), 1., atol=1e-6)

    NORMALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if NORMALS_FILE.exists():
        raise FileExistsError('Refusing to replace a Blender normals export')
    stage = Usd.Stage.CreateNew(str(NORMALS_FILE))
    root = UsdGeom.Xform.Define(stage, '/BlenderNormals').GetPrim()
    stage.SetDefaultPrim(root)
    mesh = UsdGeom.Mesh.Define(stage, '/BlenderNormals/Normals')
    mesh.CreateNormalsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, v)) for v in values]))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    mesh.GetPrim().SetCustomDataByKey('sourceGeometrySHA256', geometry_signature(source_mesh))
    mesh.GetPrim().SetCustomDataByKey('contract', CONTRACT)
    mesh.GetPrim().SetCustomDataByKey('sourceMeshPath', MESH_PATH)
    mesh.GetPrim().SetCustomDataByKey('sourceFileSHA256', original_hash)
    stage.GetRootLayer().Save()
    assert original_hash == hashlib.sha256(source_file.read_bytes()).hexdigest()
    report = dict(contract=CONTRACT, asset=str(NORMALS_FILE.relative_to(ROOT)),
                  source_sha256=original_hash, source_geometry_sha256=geometry_signature(source_mesh),
                  vertices=206, triangles=272, face_corner_normals=len(values),
                  normal_bytes=values.nbytes, maximum_vertex_mapping_error_local=max_error,
                  scope='Only normals and normals interpolation are applied; no mesh/collision/physics changes')
    (ROOT/'exports/blender_shading_20261026/applied_normals.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('BLENDER_NORMALS_EXPORTED', json.dumps(report))


if __name__ == '__main__':
    main()
