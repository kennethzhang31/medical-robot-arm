"""Offline USD checks against the real assets; no simulator or asset saves."""
import hashlib
import json
from pathlib import Path
import struct
import unittest
import zipfile

from env.instrument_materials import STEEL_CONTRACT, STEEL_FINISH, tune_steel_materials
from src.recorder.domain_randomization import apply_background, sample_background

try:
    from pxr import Gf, Usd, UsdGeom, UsdShade
except ImportError:
    Usd = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(Usd is None, 'Requires USD Python bindings')
class SceneMaterialTests(unittest.TestCase):
    def test_matching_steel_keeps_geometry_normals_physics_and_separate_regions(self):
        for asset in ('assets/knife_centered.usd',
                      'env/aspire_usd45/kelly_root_at_center.usda',
                      'env/aspire_usd45/scalpel_type2_root.usda'):
            with self.subTest(asset=asset):
                path = ROOT / asset
                source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                stage = Usd.Stage.Open(str(path))
                def non_shader_state():
                    return {str(p.GetPath()): (p.GetAppliedSchemas(),
                            [(a.GetName(), str(a.Get())) for a in p.GetAttributes()],
                            [(r.GetName(), r.GetTargets()) for r in p.GetRelationships()])
                            for p in stage.Traverse() if not p.IsA(UsdShade.Shader)}
                before = non_shader_state()
                retractor = 'love_' in asset
                tune_steel_materials(stage.GetDefaultPrim(), retractor=retractor, normalize_steel=True)
                self.assertEqual(non_shader_state(), before)
                shaders = [UsdShade.Shader(p) for p in stage.Traverse()
                           if p.GetAttribute('info:id').Get() == 'UsdPreviewSurface']
                self.assertGreater(len(shaders), 0)
                for shader in shaders:
                    self.assertEqual(shader.GetInput('diffuseColor').Get(), Gf.Vec3f(*STEEL_FINISH.diffuse_color))
                    self.assertAlmostEqual(shader.GetInput('metallic').Get(), .95)
                    expected = .40 if 'Blade' in str(shader.GetPath()) else .52
                    self.assertAlmostEqual(shader.GetInput('roughness').Get(), expected)
                first = stage.GetRootLayer().ExportToString()
                tune_steel_materials(stage.GetDefaultPrim(), retractor=retractor, normalize_steel=True)
                self.assertEqual(stage.GetRootLayer().ExportToString(), first)
                self.assertEqual(stage.GetDefaultPrim().GetCustomDataByKey('steelMaterialContract'), STEEL_CONTRACT)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)

    def test_scalpel_retains_two_finishes_and_repairs_invalid_normal(self):
        stage = Usd.Stage.Open(str(ROOT/'assets/knife_centered.usd'))
        shaders = [UsdShade.Shader(p) for p in stage.Traverse()
                   if p.IsA(UsdShade.Shader) and p.GetAttribute('info:id').Get() == 'UsdPreviewSurface']
        colors = [s.GetInput('diffuseColor').Get() for s in shaders]
        tune_steel_materials(stage.GetDefaultPrim())
        self.assertEqual(len(shaders), 2)
        self.assertEqual([s.GetInput('diffuseColor').Get() for s in shaders], colors)
        finishes = {s.GetPath().GetParentPath().name: s for s in shaders}
        self.assertAlmostEqual(finishes['Hand'].GetInput('roughness').Get(), .52)
        self.assertAlmostEqual(finishes['Blade'].GetInput('roughness').Get(), .40)
        for shader in shaders:
            self.assertEqual(shader.GetInput('metallic').Get(), 1.)
            self.assertEqual(shader.GetInput('normal').Get(), Gf.Vec3f(0., 0., 1.))

    def test_retractor_binds_blender_export_without_overrides_or_geometry_changes(self):
        from env.instrument_materials import BLENDER_RETRACTOR_CONTRACT, BLENDER_RETRACTOR_MATERIAL
        source = ROOT/'env/aspire_usd45/love_centered_root_at_center.usda'
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        stage = Usd.Stage.CreateInMemory()
        root = stage.DefinePrim('/Tool', 'Xform')
        root.GetReferences().AddReference(str(source))
        def geometry_state():
            return {str(p.GetPath()): (
                [schema for schema in p.GetAppliedSchemas() if schema != 'MaterialBindingAPI'],
                [(a.GetName(), str(a.Get()), a.GetConnections()) for a in p.GetAttributes()],
                [(r.GetName(), r.GetTargets()) for r in p.GetRelationships()
                 if not r.GetName().startswith('material:binding')])
                for p in stage.Traverse() if not p.IsA(UsdShade.Material) and not p.IsA(UsdShade.Shader)}
        before = geometry_state()
        library = Usd.Stage.Open(str(BLENDER_RETRACTOR_MATERIAL))
        exported, _, _ = UsdShade.Material(library.GetDefaultPrim()).ComputeSurfaceSource()
        tune_steel_materials(root, retractor=True, normalize_steel=True, minimum_roughness=.99)
        self.assertEqual(geometry_state(), before)
        meshes = [p for p in Usd.PrimRange(root) if p.IsA(UsdGeom.Mesh)]
        self.assertGreater(len(meshes), 0)
        for mesh in meshes:
            material, _ = UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()
            shader, _, _ = material.ComputeSurfaceSource()
            self.assertEqual(str(material.GetPath()), '/Tool/BlenderSteel')
            self.assertEqual(shader.GetIdAttr().Get(), 'UsdPreviewSurface')
            for expected in exported.GetInputs():
                actual = shader.GetInput(expected.GetBaseName())
                self.assertEqual(actual.Get(), expected.Get())
                self.assertFalse(actual.HasConnectedSource())
        self.assertEqual(root.GetCustomDataByKey('steelMaterialContract'), BLENDER_RETRACTOR_CONTRACT)
        first = stage.GetRootLayer().ExportToString()
        tune_steel_materials(root, retractor=True, normalize_steel=True)
        self.assertEqual(stage.GetRootLayer().ExportToString(), first)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)

    def test_other_tools_and_tray_keep_their_authored_metal_colors(self):
        for asset in ('env/aspire_usd45/kelly_root_at_center.usda',
                      'env/aspire_usd45/scalpel_type2_root.usda', 'assets/SurgicalTray.usd'):
            with self.subTest(asset=asset):
                stage = Usd.Stage.Open(str(ROOT/asset))
                shaders = [UsdShade.Shader(p) for p in stage.Traverse()
                           if p.IsA(UsdShade.Shader) and p.GetAttribute('info:id').Get() == 'UsdPreviewSurface']
                before = [(s.GetInput('metallic').Get(), s.GetInput('diffuseColor').Get()) for s in shaders]
                minimum = .40 if asset.endswith('SurgicalTray.usd') else .52
                tune_steel_materials(stage.GetDefaultPrim(), minimum_roughness=minimum)
                self.assertEqual([(s.GetInput('metallic').Get(), s.GetInput('diffuseColor').Get())
                                  for s in shaders], before)
                for shader in shaders:
                    if (shader.GetInput('metallic').Get() or 0.) >= .5:
                        self.assertGreaterEqual(shader.GetInput('roughness').Get(), minimum - 1e-6)

    def test_drape_fibres_preserve_geometry_other_tables_and_source_assets(self):
        from env.cloth_materials import ASSET_DIR, CONTRACT
        source = ROOT/'assets/hospital_isaac.usdz'
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        stage = Usd.Stage.Open(str(source))
        selected = stage.GetPrimAtPath('/HospitalScene/Furniture/Table_04')
        def mesh_state(root):
            return {str(p.GetPath()): (UsdGeom.Mesh(p).GetPointsAttr().Get(),
                                      UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
                    for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)}
        geometry = mesh_state(selected)
        other = stage.GetPrimAtPath('/HospitalScene/Furniture/Table_03')
        other_before = mesh_state(other)
        def shaders(root):
            return {str(p.GetPath()): [(a.GetName(), str(a.Get()), list(a.GetConnections()))
                                      for a in p.GetAttributes()]
                    for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()) if p.IsA(UsdShade.Shader)}
        other_materials = shaders(other)
        config = sample_background(17)
        apply_background(stage, {'selected_table': 'Table_04'}, config, root=stage.GetDefaultPrim())
        first = shaders(selected)
        apply_background(stage, {'selected_table': 'Table_04'}, sample_background(91), root=stage.GetDefaultPrim())
        apply_background(stage, {'selected_table': 'Table_04'}, sample_background(17), root=stage.GetDefaultPrim())
        self.assertEqual(shaders(selected), first)
        self.assertEqual(mesh_state(selected), geometry)
        self.assertEqual(mesh_state(other), other_before)
        self.assertEqual(shaders(other), other_materials)
        for path in config['mesh_paths']:
            material, _ = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(path)).ComputeBoundMaterial()
            shader, _, _ = material.ComputeSurfaceSource()
            self.assertTrue(shader.GetInput('diffuseColor').HasConnectedSource())
            self.assertTrue(shader.GetInput('normal').HasConnectedSource())
            self.assertTrue(shader.GetInput('roughness').HasConnectedSource())
            self.assertEqual(shader.GetInput('metallic').Get(), 0.)
            self.assertEqual(shader.GetPrim().GetCustomDataByKey('clothMaterialContract'), CONTRACT)
            for name, filename in [('diffuseColor', 'basecolor.png'), ('roughness', 'roughness.png')]:
                texture = UsdShade.Shader(shader.GetInput(name).GetConnectedSource()[0].GetPrim())
                self.assertEqual(Path(texture.GetInput('file').Get().path), ASSET_DIR / filename)
                self.assertEqual(texture.GetInput('wrapS').Get(), 'repeat')
                self.assertEqual(texture.GetInput('wrapT').Get(), 'repeat')
                self.assertEqual(texture.GetInput('sourceColorSpace').Get(), 'sRGB' if name == 'diffuseColor' else 'raw')
                mapping = UsdShade.Shader(texture.GetInput('st').GetConnectedSource()[0].GetPrim())
                self.assertEqual(mapping.GetIdAttr().Get(), 'UsdTransform2d')
                self.assertEqual(mapping.GetInput('in').GetConnectedSource()[0].GetPrim().GetAttribute('info:id').Get(),
                                 'UsdPrimvarReader_float2')
                self.assertAlmostEqual(mapping.GetInput('scale').Get()[0], 272.2575, places=4)
                self.assertAlmostEqual(mapping.GetInput('scale').Get()[1], 173.169167, places=4)
            normal = UsdShade.Shader(shader.GetInput('normal').GetConnectedSource()[0].GetPrim())
            self.assertTrue(normal.GetInput('file').Get().path.endswith('drape_creases_normal.png'))
            self.assertEqual(list(normal.GetInput('scale').Get()[:3]), [2., 2., 2.])
            self.assertEqual(list(normal.GetInput('bias').Get()[:3]), [-1., -1., -1.])
            self.assertEqual(normal.GetInput('st').GetConnectedSource()[0].GetPrim().GetAttribute('info:id').Get(),
                             'UsdPrimvarReader_float2')
            mdl, _, _ = material.ComputeSurfaceSource('mdl')
            self.assertEqual(mdl.GetSourceAsset('mdl').path, 'OmniPBR.mdl')
            self.assertEqual(mdl.GetSourceAssetSubIdentifier('mdl'), 'OmniPBR')
            self.assertEqual(mdl.GetInput('detail_texture_scale').Get(), Gf.Vec2f(1.))
            self.assertEqual(Path(mdl.GetInput('normalmap_texture').Get().path), ASSET_DIR / 'normal.png')
            self.assertEqual(Path(mdl.GetInput('detail_normalmap_texture').Get().path),
                             Path(normal.GetInput('file').Get().resolvedPath))
            self.assertFalse(mdl.GetInput('flip_tangent_v').Get())
            self.assertEqual(mdl.GetInput('normalmap_texture').GetAttr().GetColorSpace(), 'raw')
            self.assertEqual(mdl.GetInput('diffuse_texture').GetAttr().GetColorSpace(), 'sRGB')
            weight = mdl.GetInput('reflection_roughness_texture_influence').Get()
            self.assertAlmostEqual((1 - weight) * mdl.GetInput('reflection_roughness_constant').Get()
                                   + weight * .84, config['roughness'], places=6)
        self.assertEqual(config['material_contract'], CONTRACT)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_hash)

    def test_fibre_textures_are_small_and_match_blender_export(self):
        from env.cloth_materials import ASSET_DIR, CONTRACT
        metadata = json.loads((ASSET_DIR / 'material.json').read_text())
        self.assertEqual(metadata['contract'], CONTRACT)
        self.assertAlmostEqual(metadata['tile_metres'], .012)
        self.assertEqual(set(metadata['asset_sha256']),
                         {'basecolor.png', 'normal.png', 'roughness.png', 'drape_creases_normal.png'})
        self.assertEqual(len(metadata['reference_sha256']), 64)
        self.assertTrue(all(0 <= v <= 1 for v in metadata['reference_crop_normalized']))
        for name, digest in metadata['asset_sha256'].items():
            raw = (ASSET_DIR / name).read_bytes()
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', raw[16:24]),
                             (4096, 2048) if name == 'drape_creases_normal.png' else (512, 512))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        with zipfile.ZipFile(ROOT / 'assets/hospital_isaac.usdz') as package:
            self.assertEqual(package.read('0/drape_creases_normal.png'),
                             (ASSET_DIR / 'drape_creases_normal.png').read_bytes())

    def test_microfiber_normal_texture_has_valid_relief(self):
        import numpy as np
        from PIL import Image
        from env.cloth_materials import ASSET_DIR
        normals = np.asarray(Image.open(ASSET_DIR / 'normal.png').convert('RGB'), dtype=float) / 127.5 - 1
        self.assertTrue(np.isfinite(normals).all())
        self.assertTrue(np.allclose(np.linalg.norm(normals, axis=-1), 1, atol=.012))
        self.assertGreater(float(normals[:, :, 2].min()), .3)
        self.assertGreater(float(normals[:, :, :2].std()), .05)


if __name__ == '__main__':
    unittest.main()
