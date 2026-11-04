"""Transfer incoming appearances and display tools into the existing hospital."""
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parents[1] / 'assets/new_environment'
CLOTH_CONTRACT = 'new_env_reference_cloth_v1'


def apply_cloth_materials(root):
    """Replace cloth graphs in place, preserving every mesh and material binding."""
    from pxr import Sdf, Usd, UsdShade

    stage = root.GetStage()
    library = Usd.Stage.Open(str(ASSET_DIR / 'cloth.usda'))
    source = library.Flatten()
    # Make only cloth branches editable, including their nested material scopes.
    while True:
        instance = next((p for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies())
                         if p.IsInstance() and any(s in p.GetName()
                         for s in ('SurgicalInstrumentTable', 'Cloth', 'GreenDrape', 'BluePads'))), None)
        if instance is None:
            break
        instance.SetInstanceable(False)
    materials = [p for p in Usd.PrimRange(root) if p.IsA(UsdShade.Material)
                 and '/Cloth_' in str(p.GetPath())]
    assert materials, 'Hospital cloth material scopes are missing'
    for material in materials:
        original = library.GetPrimAtPath('/Cloth/' + material.GetName())
        if not original:
            raise RuntimeError('Unknown cloth material: ' + str(material.GetPath()))
        layer = stage.GetEditTarget().GetLayer()
        Sdf.CreatePrimInLayer(layer, material.GetPath().GetParentPath())
        Sdf.CopySpec(source, original.GetPath(), layer, material.GetPath())
        material.SetCustomDataByKey('clothMaterialContract', CLOTH_CONTRACT)
    return len(materials)


def vary_cloth(shader, config):
    """Vary the new green cloth without rebuilding its UV or normal graph."""
    from pxr import Gf, Sdf, Usd, UsdShade

    material = UsdShade.Material(shader.GetPrim().GetParent())
    library = Usd.Stage.Open(str(ASSET_DIR / 'cloth.usda'))
    original, _, _ = UsdShade.Material(library.GetPrimAtPath('/Cloth/' + material.GetPrim().GetName())).ComputeSurfaceSource()
    for name in ('diffuseColor', 'roughness'):
        texture = UsdShade.Shader(shader.GetInput(name).GetConnectedSource()[0].GetPrim())
        baseline = UsdShade.Shader(original.GetInput(name).GetConnectedSource()[0].GetPrim())
        if name == 'diffuseColor':
            scale = baseline.GetInput('scale').Get() or Gf.Vec4f(1.)
            bias = baseline.GetInput('bias').Get() or Gf.Vec4f(0.)
            factors = [v / base for v, base in zip(config['color'], (.045, .24, .13))]
            texture.CreateInput('scale', Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*[scale[i]*factors[i] for i in range(3)], 1.))
            texture.CreateInput('bias', Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*[bias[i]*factors[i] for i in range(3)], 0.))
        else:
            # Offset from the canonical episode roughness; retain the incoming atlas contrast.
            texture.CreateInput('bias', Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*([config['roughness']-.82]*3), 0.))
    return CLOTH_CONTRACT
