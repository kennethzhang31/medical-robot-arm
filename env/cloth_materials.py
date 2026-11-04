"""Apply the Blender-authored, repeating drape textures without geometry edits."""
import json
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parents[1] / 'assets/blender_microfiber'
CONTRACT = 'blender_microfiber_v2'


def apply_fibre_textures(surface):
    from pxr import Gf, Sdf, UsdShade

    metadata = json.loads((ASSET_DIR / 'material.json').read_text(encoding='utf-8'))
    assert metadata['contract'] == CONTRACT
    textures = {}
    for name, filename in [('diffuseColor', 'basecolor.png'), ('roughness', 'roughness.png')]:
        source = surface.GetInput(name).GetConnectedSource()
        if not source or source[0].GetPrim().GetAttribute('info:id').Get() != 'UsdUVTexture':
            raise RuntimeError('Missing drape texture: ' + name)
        path = ASSET_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        textures[name] = UsdShade.Shader(source[0].GetPrim()), path

    stage = surface.GetPrim().GetStage()
    mapping = UsdShade.Shader.Define(stage, surface.GetPath().GetParentPath().AppendChild('FibreUV'))
    mapping.CreateIdAttr('UsdTransform2d')
    uv_input = mapping.CreateInput('in', Sdf.ValueTypeNames.Float2)
    # Keep the original primvar reader on repeat calls; never feed this node itself.
    if not uv_input.HasConnectedSource():
        source = textures['diffuseColor'][0].GetInput('st').GetConnectedSource()
        if not source or source[0].GetPrim().GetAttribute('info:id').Get() != 'UsdPrimvarReader_float2':
            raise RuntimeError('Missing drape UV reader')
        uv_input.ConnectToSource(*source)
    mapping.CreateInput('scale', Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(*metadata['uv_repeats']))
    mapping.CreateOutput('result', Sdf.ValueTypeNames.Float2)
    for name, (texture, path) in textures.items():
        texture.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(path)))
        texture.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(mapping.ConnectableAPI(), 'result')
        for axis in ('wrapS', 'wrapT'):
            texture.CreateInput(axis, Sdf.ValueTypeNames.Token).Set('repeat')
        texture.CreateInput('sourceColorSpace', Sdf.ValueTypeNames.Token).Set('sRGB' if name == 'diffuseColor' else 'raw')
    surface.GetPrim().SetCustomDataByKey('clothMaterialContract', CONTRACT)
    return metadata


def apply_microfiber_surface(surface, metadata, config):
    """Layer the tiled tuft normals and untiled creases using Isaac's OmniPBR."""
    from pxr import Gf, Sdf, UsdShade

    normal_path = ASSET_DIR / 'normal.png'
    if not normal_path.is_file():
        raise FileNotFoundError(normal_path)
    source = surface.GetInput('normal').GetConnectedSource()
    if not source:
        raise RuntimeError('Missing crease normal texture')
    crease_path = ASSET_DIR / 'drape_creases_normal.png'
    if not crease_path.is_file():
        raise FileNotFoundError(crease_path)
    # This is a byte-identical extraction; use one file for both rendering paths.
    UsdShade.Shader(source[0].GetPrim()).GetInput('file').Set(Sdf.AssetPath(str(crease_path)))
    material = UsdShade.Material(surface.GetPrim().GetParent())
    mdl = UsdShade.Shader.Define(surface.GetPrim().GetStage(), material.GetPath().AppendChild('Microfiber'))
    mdl.SetSourceAsset(Sdf.AssetPath('OmniPBR.mdl'), 'mdl')
    mdl.SetSourceAssetSubIdentifier('OmniPBR', 'mdl')
    for name, filename, color_space in [('diffuse_texture', 'basecolor.png', 'sRGB'),
                                        ('reflectionroughness_texture', 'roughness.png', 'raw'),
                                        ('normalmap_texture', 'normal.png', 'raw')]:
        attr = mdl.CreateInput(name, Sdf.ValueTypeNames.Asset)
        attr.Set(Sdf.AssetPath(str(ASSET_DIR / filename)))
        attr.GetAttr().SetColorSpace(color_space)
    crease_input = mdl.CreateInput('detail_normalmap_texture', Sdf.ValueTypeNames.Asset)
    crease_input.Set(Sdf.AssetPath(str(crease_path)))
    crease_input.GetAttr().SetColorSpace('raw')
    # OmniPBR's two UV transforms are independent: tile the pile, keep creases at 1x.
    mdl.CreateInput('texture_scale', Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(*metadata['uv_repeats']))
    mdl.CreateInput('detail_texture_scale', Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(1.))
    weight = metadata['roughness_weight']
    roughness = (config['roughness'] - weight * metadata['roughness_mean']) / (1 - weight)
    for name, value in [('reflection_roughness_constant', roughness),
                         ('reflection_roughness_texture_influence', weight),
                         ('metallic_constant', 0.), ('specular_level', .35),
                         ('bump_factor', metadata['bump_strength']), ('detail_bump_factor', 1.),
                         ('geometry_normal_roughness_strength', 1.)]:
        mdl.CreateInput(name, Sdf.ValueTypeNames.Float).Set(value)
    mdl.CreateInput('flip_tangent_u', Sdf.ValueTypeNames.Bool).Set(False)
    mdl.CreateInput('flip_tangent_v', Sdf.ValueTypeNames.Bool).Set(False)
    tint = [v / base for v, base in zip(config['color'], (.045, .24, .13))]
    mdl.CreateInput('diffuse_tint', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*tint))
    mdl.CreateOutput('out', Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput('mdl').ConnectToSource(mdl.ConnectableAPI(), 'out')
