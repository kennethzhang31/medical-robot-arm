"""Export the incoming cloth graphs and satin tools; keep both source rooms intact."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from env.instrument_materials import tune_steel_materials

OUT = ROOT / 'assets/new_environment'
SOURCE = ROOT / 'new-env/hospital_isaac_room_v3_2.usdz'
CONTRACT = 'new_env_cloth_matched_satin_tools_v2'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = Usd.Stage.Open(str(SOURCE))
    while True:
        instance = next((p for p in source.Traverse() if p.IsInstance()), None)
        if instance is None:
            break
        instance.SetInstanceable(False)
    flat = source.Flatten()
    library = Usd.Stage.CreateNew(str(OUT / 'cloth.usda'))
    library.SetDefaultPrim(UsdGeom.Scope.Define(library, '/Cloth').GetPrim())
    table = '/HospitalScene/Furniture/Table_04/'
    materials = [p for p in source.Traverse() if p.IsA(UsdShade.Material)
                 and str(p.GetPath()).startswith(table) and '/Cloth_' in str(p.GetPath())]
    assert len(materials) == 6
    for material in materials:
        destination = Sdf.Path('/Cloth').AppendChild(material.GetName())
        Sdf.CopySpec(flat, material.GetPath(), library.GetRootLayer(), destination)
    textures = {}
    with zipfile.ZipFile(SOURCE) as package:
        for prim in library.Traverse():
            attr = prim.GetAttribute('inputs:file')
            if not attr:
                continue
            filename = Path(attr.Get().path.rstrip(']')).name
            data = package.read('textures/' + filename)
            path = OUT / 'textures' / filename
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            attr.Set(Sdf.AssetPath('textures/' + filename))
            textures[filename] = hashlib.sha256(data).hexdigest()
    library.GetRootLayer().Save()

    display = Usd.Stage.CreateNew(str(OUT / 'instruments.usda'))
    display.SetDefaultPrim(UsdGeom.Xform.Define(display, '/Instruments').GetPrim())
    UsdGeom.SetStageUpAxis(display, 'Z')
    UsdGeom.SetStageMetersPerUnit(display, 1.)
    tools = []
    (OUT / 'source').mkdir(exist_ok=True)
    for index, path in enumerate(sorted((ROOT / 'new-env/instruments').glob('*.usd'))):
        incoming = Usd.Stage.Open(str(path))
        assert UsdGeom.GetStageUpAxis(incoming) == 'Z' and UsdGeom.GetStageMetersPerUnit(incoming) == 1.
        shutil.copyfile(path, OUT / 'source' / path.name)
        target = OUT / (path.stem + '.usda')
        asset = Usd.Stage.CreateNew(str(target))
        root = UsdGeom.Xform.Define(asset, '/Asset').GetPrim()
        asset.SetDefaultPrim(root)
        root.GetReferences().AddReference('source/' + path.name)
        UsdGeom.SetStageUpAxis(asset, 'Z')
        UsdGeom.SetStageMetersPerUnit(asset, 1.)
        while True:
            instance = next((p for p in asset.Traverse() if p.IsInstance()), None)
            if instance is None:
                break
            instance.SetInstanceable(False)
        tune_steel_materials(asset.GetDefaultPrim(), normalize_steel=True)
        asset.GetRootLayer().Save()
        root = UsdGeom.Xform.Define(display, '/Instruments/' + path.stem)
        root.GetPrim().GetReferences().AddReference(target.name)
        UsdPhysics.RigidBodyAPI(root.GetPrim()).CreateRigidBodyEnabledAttr(False)
        for prim in Usd.PrimRange(root.GetPrim()):
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(False)
        # Table_03 is a background table, far from the active Table_04 workspace.
        UsdGeom.XformCommonAPI(root).SetTranslate(Gf.Vec3d(-2.3 + (index % 4 - 1.5) * .32,
                                                        3.55 + (index // 4 - .5) * .22, .910))
        tools.append(dict(name=path.stem, source=str(path.relative_to(ROOT)),
                          source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          asset=target.name, purpose='static_display_only'))
    assert len(tools) == 8
    display.GetRootLayer().Save()
    metadata = dict(contract=CONTRACT, source=str(SOURCE.relative_to(ROOT)),
                    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    textures=textures, tools=tools, robot_present=False)
    (OUT / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('Transferred', len(materials), 'cloth materials,', len(textures), 'textures and', len(tools), 'satin tools')


if __name__ == '__main__':
    main()
