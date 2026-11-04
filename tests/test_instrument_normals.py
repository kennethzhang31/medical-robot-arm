"""Blender shading data must never alter the simulated shape or physics."""
import hashlib
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class InstrumentNormalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.convert_aspire_assets import usd_bindings
        usd_bindings()
        from pxr import Usd, UsdGeom
        cls.Usd, cls.UsdGeom = Usd, UsdGeom

    def stage(self):
        stage = self.Usd.Stage.CreateInMemory()
        root = stage.DefinePrim('/Tool', 'Xform')
        root.GetReferences().AddReference(str(ROOT/'env/aspire_usd45/love_centered_root_at_center.usda'))
        return stage, root

    def test_only_normals_change_and_repeated_application_is_stable(self):
        from env.instrument_normals import apply_blender_normals, geometry_signature, MESH_PATH, CONTRACT
        stage, root = self.stage()
        mesh = self.UsdGeom.Mesh(stage.GetPrimAtPath('/Tool/' + MESH_PATH))
        before = geometry_signature(mesh)
        attributes = {str(attr.GetPath()): attr.Get() for prim in stage.Traverse()
                      for attr in prim.GetAttributes() if attr.GetName() != 'normals'}
        schemas = {str(prim.GetPath()): prim.GetAppliedSchemas() for prim in stage.Traverse()}
        relations = {str(rel.GetPath()): rel.GetTargets() for prim in stage.Traverse()
                     for rel in prim.GetRelationships()}
        source = ROOT/'assets/love_centered_root_at_center.usd'
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        apply_blender_normals(root)
        values = np.asarray(mesh.GetNormalsAttr().Get()).copy()
        self.assertEqual(values.shape, (816, 3))
        self.assertTrue(np.isfinite(values).all())
        np.testing.assert_allclose(np.linalg.norm(values, axis=1), 1., atol=1e-6)
        self.assertEqual(mesh.GetNormalsInterpolation(), 'faceVarying')
        self.assertEqual(root.GetCustomDataByKey('blenderNormalsContract'), CONTRACT)
        self.assertEqual(geometry_signature(mesh), before)
        self.assertEqual(attributes, {str(attr.GetPath()): attr.Get() for prim in stage.Traverse()
                         for attr in prim.GetAttributes() if attr.GetName() != 'normals'})
        self.assertEqual(schemas, {str(prim.GetPath()): prim.GetAppliedSchemas() for prim in stage.Traverse()})
        self.assertEqual(relations, {str(rel.GetPath()): rel.GetTargets() for prim in stage.Traverse()
                         for rel in prim.GetRelationships()})
        apply_blender_normals(root)
        np.testing.assert_array_equal(values, np.asarray(mesh.GetNormalsAttr().Get()))
        self.assertEqual(source_hash, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_rejects_changed_geometry_before_overriding_normals(self):
        from env.instrument_normals import apply_blender_normals, MESH_PATH
        stage, root = self.stage()
        mesh = self.UsdGeom.Mesh(stage.GetPrimAtPath('/Tool/' + MESH_PATH))
        original_normals = mesh.GetNormalsAttr().Get()
        points = mesh.GetPointsAttr().Get()
        points[0] = points[0] * 1.01
        mesh.GetPointsAttr().Set(points)
        with self.assertRaisesRegex(ValueError, 'geometry differs'):
            apply_blender_normals(root)
        self.assertEqual(mesh.GetNormalsAttr().Get(), original_normals)


if __name__ == '__main__':
    unittest.main()
