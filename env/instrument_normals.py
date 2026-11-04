"""Blender-derived shading normals; original USD geometry and physics are retained."""
import hashlib
from pathlib import Path

NORMALS_FILE = Path(__file__).resolve().parents[1] / 'assets/blender_normals/love_retractor.usda'
MESH_PATH = 'Geom/center/Cylinder_074_59/Object_125/Object_62'
CONTRACT = 'blender_weighted_retractor_normals_v1'
_stage = None


def geometry_signature(mesh):
    import numpy as np

    digest = hashlib.sha256()
    for attr, dtype in ((mesh.GetPointsAttr(), '<f4'),
                        (mesh.GetFaceVertexCountsAttr(), '<i4'),
                        (mesh.GetFaceVertexIndicesAttr(), '<i4')):
        digest.update(np.asarray(attr.Get(), dtype=dtype).tobytes())
    return digest.hexdigest()


def apply_blender_normals(root):
    from pxr import Usd, UsdGeom

    global _stage
    if _stage is None:
        _stage = Usd.Stage.Open(str(NORMALS_FILE))
        if _stage is None:
            raise RuntimeError('Missing Blender normal asset: ' + str(NORMALS_FILE))
    source = UsdGeom.Mesh(_stage.GetDefaultPrim().GetChild('Normals'))
    target = UsdGeom.Mesh(root.GetStage().GetPrimAtPath(root.GetPath().AppendPath(MESH_PATH)))
    if not target or geometry_signature(target) != source.GetPrim().GetCustomDataByKey('sourceGeometrySHA256'):
        raise ValueError('Retractor geometry differs from the validated Blender normal source')
    normals = source.GetNormalsAttr().Get()
    if len(normals) != len(target.GetFaceVertexIndicesAttr().Get()):
        raise ValueError('Blender normals do not match retractor face corners')
    target.CreateNormalsAttr().Set(normals)
    target.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    root.SetCustomDataByKey('blenderNormalsContract', CONTRACT)
