"""Validate transfers against the supplied USD assets, without launching Isaac."""
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

try:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade
except ImportError:
    Usd = None

from env.new_environment import ASSET_DIR, CLOTH_CONTRACT, apply_cloth_materials
from env.instrument_materials import STEEL_FINISH
from src.recorder.domain_randomization import apply_background, sample_background

ROOT = Path(__file__).resolve().parents[1]


def geometry(stage):
    return {str(p.GetPath()): [(a.GetName(), str(a.Get())) for a in p.GetAttributes()
                             if not a.GetName().startswith(('outputs:', 'inputs:'))]
            for p in stage.Traverse(Usd.TraverseInstanceProxies())
            if p.IsA(UsdGeom.Mesh) or p.IsA(UsdGeom.Cube) or p.IsA(UsdGeom.Xform)}


@unittest.skipIf(Usd is None, 'Requires USD Python bindings')
class NewEnvironmentTests(unittest.TestCase):
    def test_cloth_transfer_preserves_old_room_geometry_and_new_graphs(self):
        path = ROOT / 'assets/hospital_isaac.usdz'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stage = Usd.Stage.Open(str(path))
        before = geometry(stage)
        self.assertEqual(apply_cloth_materials(stage.GetDefaultPrim()), 42)
        self.assertEqual(geometry(stage), before)
        shaders = [UsdShade.Shader(p) for p in stage.Traverse() if p.GetName() == 'RGB_Texture_Scale'
                   and '/Cloth_' in str(p.GetPath())]
        self.assertEqual(len(shaders), 21)
        for shader in shaders:
            self.assertTrue(shader.GetInput('in').HasConnectedSource())
        for prim in stage.Traverse():
            if '/Cloth_' not in str(prim.GetPath()) or not prim.IsA(UsdShade.Material):
                continue
            material = UsdShade.Material(prim)
            self.assertEqual(prim.GetCustomDataByKey('clothMaterialContract'), CLOTH_CONTRACT)
            shader, _, _ = material.ComputeSurfaceSource()
            self.assertTrue(shader)
            self.assertFalse(material.GetSurfaceOutput('mdl'))
            for name in ('diffuseColor', 'roughness', 'normal'):
                inp = shader.GetInput(name)
                if not inp or not inp.HasConnectedSource():
                    continue
                texture = UsdShade.Shader(inp.GetConnectedSource()[0].GetPrim())
                self.assertTrue(Path(texture.GetInput('file').Get().resolvedPath).is_file())
                self.assertTrue(texture.GetInput('st').HasConnectedSource())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_new_cloth_randomization_is_repeatable_and_keeps_uv_and_normals(self):
        stage = Usd.Stage.Open(str(ROOT / 'assets/hospital_isaac.usdz'))
        apply_cloth_materials(stage.GetDefaultPrim())
        layout = dict(selected_table='Table_04', cloth_material=CLOTH_CONTRACT)
        def state():
            return [(str(p.GetPath()), [(a.GetName(), str(a.Get()), str(a.GetConnections()))
                    for a in p.GetAttributes()]) for p in stage.Traverse() if p.IsA(UsdShade.Shader)]
        config = sample_background(17)
        apply_background(stage, layout, config, root=stage.GetDefaultPrim())
        first = state()
        apply_background(stage, layout, sample_background(91), root=stage.GetDefaultPrim())
        apply_background(stage, layout, sample_background(17), root=stage.GetDefaultPrim())
        self.assertEqual(state(), first)
        self.assertEqual(config['material_contract'], CLOTH_CONTRACT)
        self.assertEqual(len(config['mesh_paths']), 1)

    def test_tools_keep_geometry_bindings_and_receive_matching_satin_finish(self):
        manifest = json.loads((ASSET_DIR / 'manifest.json').read_text())
        self.assertEqual(len(manifest['tools']), 8)
        self.assertFalse(manifest['robot_present'])
        for tool in manifest['tools']:
            with self.subTest(tool=tool['name']):
                path = ROOT / tool['source']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), tool['source_sha256'])
                old = Usd.Stage.Open(str(path))
                new = Usd.Stage.Open(str(ASSET_DIR / tool['asset']))
                self.assertEqual(geometry(old), geometry(new))
                shaders = [p for p in new.Traverse() if p.IsA(UsdShade.Shader)
                           and p.GetAttribute('info:id').Get() == 'UsdPreviewSurface']
                self.assertEqual(len(shaders), 3, 'Satin overrides must reach the instanced material scopes')
                for prim in new.Traverse():
                    self.assertEqual(prim.HasAPI(UsdPhysics.RigidBodyAPI), old.GetPrimAtPath(prim.GetPath()).HasAPI(UsdPhysics.RigidBodyAPI))
                    self.assertEqual(prim.HasAPI(UsdPhysics.CollisionAPI), old.GetPrimAtPath(prim.GetPath()).HasAPI(UsdPhysics.CollisionAPI))
                    if prim.IsA(UsdGeom.Mesh):
                        before = UsdShade.MaterialBindingAPI(old.GetPrimAtPath(prim.GetPath())).ComputeBoundMaterial()[0]
                        after = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
                        self.assertEqual(before.GetPath(), after.GetPath())
                    if prim.IsA(UsdShade.Shader) and prim.GetAttribute('info:id').Get() == 'UsdPreviewSurface':
                        shader = UsdShade.Shader(prim)
                        for actual, expected in zip(shader.GetInput('diffuseColor').Get(), STEEL_FINISH.diffuse_color):
                            self.assertAlmostEqual(actual, expected)
                        self.assertAlmostEqual(shader.GetInput('metallic').Get(), STEEL_FINISH.metallic)
                        self.assertGreaterEqual(shader.GetInput('roughness').Get(), .52 - 1e-6)
        display = Usd.Stage.Open(str(ASSET_DIR / 'instruments.usda'))
        for root in display.GetDefaultPrim().GetChildren():
            self.assertFalse(UsdPhysics.RigidBodyAPI(root).GetRigidBodyEnabledAttr().Get())
            for prim in Usd.PrimRange(root):
                if prim.HasAPI(UsdPhysics.CollisionAPI):
                    self.assertFalse(UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get())

    def test_extracted_textures_are_identical_to_new_package(self):
        manifest = json.loads((ASSET_DIR / 'manifest.json').read_text())
        with zipfile.ZipFile(ROOT / manifest['source']) as package:
            self.assertEqual(hashlib.sha256(Path(package.filename).read_bytes()).hexdigest(), manifest['source_sha256'])
            for filename, digest in manifest['textures'].items():
                data = (ASSET_DIR / 'textures' / filename).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                self.assertEqual(data, package.read('textures/' + filename))


if __name__ == '__main__':
    unittest.main()
