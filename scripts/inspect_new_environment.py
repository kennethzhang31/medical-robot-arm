"""Inspect incoming USD assets without importing them into the live simulator."""
import json
from pathlib import Path
from collections import Counter

from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

ROOT = Path(__file__).resolve().parents[1]


def inspect(path):
    stage = Usd.Stage.Open(str(path))
    assert stage and stage.GetDefaultPrim(), path
    prims = list(stage.Traverse(Usd.TraverseInstanceProxies()))
    materials = {}
    for prim in prims:
        if prim.IsA(UsdShade.Material):
            material = UsdShade.Material(prim)
            shader, _, _ = material.ComputeSurfaceSource()
            materials[str(prim.GetPath())] = {
                'shader': str(shader.GetPath()) if shader else None,
                'inputs': {i.GetBaseName(): str(i.Get()) for i in shader.GetInputs()} if shader else {},
            }
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    return {
        'file': str(path.relative_to(ROOT)),
        'default_prim': str(stage.GetDefaultPrim().GetPath()),
        'up_axis': UsdGeom.GetStageUpAxis(stage),
        'metres_per_unit': UsdGeom.GetStageMetersPerUnit(stage),
        'types': dict(Counter(p.GetTypeName() for p in prims)),
        'children': [str(p.GetPath()) for p in stage.GetDefaultPrim().GetChildren()],
        'bounds': str(bounds.ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedRange()),
        'robots': [str(p.GetPath()) for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)
                   or any(s in p.GetName().lower() for s in ('robot', 'franka', 'panda'))],
        'joints': [str(p.GetPath()) for p in prims if p.IsA(UsdPhysics.Joint)],
        'rigid_bodies': [str(p.GetPath()) for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)],
        'colliders': [str(p.GetPath()) for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)],
        'materials': materials,
        'textures': {str(p.GetPath()): str(p.GetAttribute('inputs:file').Get()) for p in prims
                     if p.GetAttribute('inputs:file')},
        'meshes': {str(p.GetPath()): {'vertices': len(UsdGeom.Mesh(p).GetPointsAttr().Get() or []),
                    'bounds': str(bounds.ComputeWorldBound(p).ComputeAlignedRange()),
                    'material': str(UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0].GetPath())}
                   for p in prims if p.IsA(UsdGeom.Mesh)},
    }


if __name__ == '__main__':
    output = ROOT / 'exports/new_env_transfer_20261028'
    output.mkdir(parents=True, exist_ok=True)
    report = [inspect(path) for path in [ROOT / 'assets/hospital_isaac.usdz',
              ROOT / 'new-env/hospital_isaac_room_v3_2.usdz', *sorted((ROOT / 'new-env/instruments').glob('*.usd'))]]
    (output / 'inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for item in report:
        print(item['file'], item['types'], 'robot matches:', item['robots'], 'bounds:', item['bounds'])
