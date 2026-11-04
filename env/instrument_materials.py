"""Steel material finishes without changing instrument geometry or mesh normals."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VisualMaterialSpec:
    diffuse_color: tuple[float, float, float]
    metallic: float
    roughness: float


STEEL_FINISH = VisualMaterialSpec((0.48, 0.50, 0.52), 0.95, 0.52)
STEEL_CONTRACT = 'matched_satin_steel_v1'
BLENDER_RETRACTOR_MATERIAL = Path(__file__).resolve().parents[1] / 'assets/blender_retractor_material/love_retractor.usda'
BLENDER_RETRACTOR_CONTRACT = 'blender_retractor_steel_v1'


# The unbound scissor needs a fallback; the retractor imports its Blender material.
# Other instruments retain their separate bindings and get surface-input tuning.
INSTRUMENT_MATERIAL_OVERRIDES = {
    "scissor": STEEL_FINISH,
}


def apply_blender_retractor_material(root):
    """Bind the Blender-exported material without editing the source mesh or shaders."""
    from pxr import Usd, UsdGeom, UsdShade

    if not BLENDER_RETRACTOR_MATERIAL.is_file():
        raise FileNotFoundError(BLENDER_RETRACTOR_MATERIAL)
    meshes = [prim for prim in Usd.PrimRange(root) if prim.IsA(UsdGeom.Mesh)]
    if not meshes:
        raise ValueError('No retractor meshes to bind')
    material = UsdShade.Material.Define(root.GetStage(), root.GetPath().AppendChild('BlenderSteel'))
    material.GetPrim().GetReferences().AddReference(str(BLENDER_RETRACTOR_MATERIAL))
    surface, _, _ = material.ComputeSurfaceSource()
    if not surface or surface.GetIdAttr().Get() != 'UsdPreviewSurface':
        raise ValueError('Blender retractor material has no portable surface shader')
    for mesh in meshes:
        UsdShade.MaterialBindingAPI.Apply(mesh).Bind(material)
    root.SetCustomDataByKey('steelMaterialContract', BLENDER_RETRACTOR_CONTRACT)


def tune_steel_materials(root, *, retractor=False, minimum_roughness=0.52, normalize_steel=False):
    """Bind the Blender retractor material or tune other tools' separate surfaces."""
    from pxr import Gf, Sdf, Usd, UsdShade

    if retractor:
        # The exported Blender shader is authoritative; generic tuning must not overwrite it.
        apply_blender_retractor_material(root)
        return
    for prim in Usd.PrimRange(root):
        if not prim.IsA(UsdShade.Shader):
            continue
        shader = UsdShade.Shader(prim)
        if shader.GetIdAttr().Get() != 'UsdPreviewSurface':
            continue
        metallic = shader.GetInput('metallic')
        if not metallic or (metallic.Get() or 0.0) < 0.5:
            continue
        if normalize_steel:
            color = shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f)
            color.DisconnectSource()
            color.Set(Gf.Vec3f(*STEEL_FINISH.diffuse_color))
            metallic.Set(STEEL_FINISH.metallic)
        roughness = shader.GetInput('roughness')
        if roughness and not roughness.HasConnectedSource():
            # Keep the blade slightly smoother than the satin handle/other tools.
            minimum = 0.40 if 'Blade' in str(prim.GetPath()) else minimum_roughness
            roughness.Set(max(float(roughness.Get() or 0.0), minimum))
        normal = shader.GetInput('normal')
        if normal and not normal.HasConnectedSource() and normal.Get() == Gf.Vec3f(1.0):
            normal.Set(Gf.Vec3f(0.0, 0.0, 1.0))
    if normalize_steel:
        root.SetCustomDataByKey('steelMaterialContract', STEEL_CONTRACT)


def spawn_satin_instrument(prim_path, cfg, translation=None, orientation=None, **kwargs):
    """Tune before cloning so every environment and duplicate gets the finish."""
    from isaaclab.sim.spawners.from_files import spawn_from_usd
    from isaaclab.sim.utils import clone

    @clone
    def spawn_one(prim_path, cfg, translation=None, orientation=None, **kwargs):
        prim = spawn_from_usd(prim_path, cfg, translation=translation, orientation=orientation, **kwargs)
        retractor = Path(cfg.usd_path).stem == 'love_centered_root_at_center'
        tune_steel_materials(prim, retractor=retractor, normalize_steel=True)
        return prim

    return spawn_one(prim_path, cfg, translation=translation, orientation=orientation, **kwargs)
