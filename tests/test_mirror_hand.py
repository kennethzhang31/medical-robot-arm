"""Check the actual hand reference, wrist mount and passive joints without Kit."""
import hashlib
import unittest

from env.mirror_hand import ASSET, ACTIVE_JOINTS, ARM_JOINTS, MOUNT_POS, MOUNT_ROT, mount_hand

try:
    from pxr import Gf, Usd, UsdGeom, UsdPhysics
except ImportError:
    Usd = None


@unittest.skipIf(Usd is None, 'Requires USD Python bindings')
class MirrorHandTests(unittest.TestCase):
    def test_ur5_mount_preserves_wrist_and_passive_mechanism(self):
        before = hashlib.sha256(ASSET.read_bytes()).hexdigest()
        stage = Usd.Stage.CreateInMemory()
        robot = UsdGeom.Xform.Define(stage, '/Robot').GetPrim()
        root_joint = UsdPhysics.FixedJoint.Define(stage, '/Robot/root_joint')
        UsdPhysics.ArticulationRootAPI.Apply(root_joint.GetPrim())
        wrist = UsdGeom.Xform.Define(stage, '/Robot/wrist_3_link')
        wrist.AddTranslateOp().Set(Gf.Vec3d(.1, .2, .3))
        UsdPhysics.RigidBodyAPI.Apply(wrist.GetPrim())
        wrist_mass = UsdPhysics.MassAPI.Apply(wrist.GetPrim())
        wrist_mass.CreateMassAttr(.1879)
        UsdGeom.Cube.Define(stage, '/Robot/wrist_3_link/Geometry')
        for name in ARM_JOINTS:
            UsdPhysics.RevoluteJoint.Define(stage, '/Robot/' + name)

        hand = mount_hand(robot)
        self.assertTrue(stage.GetPrimAtPath('/Robot/wrist_3_link/Geometry').IsActive())
        self.assertAlmostEqual(wrist_mass.GetMassAttr().Get(), .1879)
        self.assertFalse(stage.GetPrimAtPath('/Robot/MirrorHand/Physics/root_joint').IsActive())
        roots = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        self.assertEqual([p.GetPath() for p in roots], [root_joint.GetPath()])
        driven = [p.GetName() for p in Usd.PrimRange(hand)
                  if p.HasAPI(UsdPhysics.DriveAPI, 'angular')]
        self.assertCountEqual(driven, ACTIVE_JOINTS)
        closures = [p for p in Usd.PrimRange(hand) if 'closure_joint' in p.GetName()]
        self.assertEqual(len(closures), 5)
        for prim in closures:
            self.assertTrue(UsdPhysics.Joint(prim).GetExcludeFromArticulationAttr().Get())
        revolute = [p for p in Usd.PrimRange(hand) if p.IsA(UsdPhysics.RevoluteJoint)]
        self.assertEqual(len(revolute), 25)
        mount = UsdPhysics.FixedJoint(stage.GetPrimAtPath('/Robot/mirror_hand_mount'))
        self.assertEqual(mount.GetBody0Rel().GetTargets(), ['/Robot/hand_mount_link'])
        adapter_joint = UsdPhysics.FixedJoint(stage.GetPrimAtPath('/Robot/hand_adapter_joint'))
        self.assertEqual(adapter_joint.GetBody0Rel().GetTargets(), [wrist.GetPath()])
        self.assertEqual(adapter_joint.GetBody1Rel().GetTargets(), ['/Robot/hand_mount_link'])
        palm = stage.GetPrimAtPath('/Robot/MirrorHand/Links/palm_link')
        self.assertEqual(mount.GetBody1Rel().GetTargets(), [palm.GetPath()])
        transform = UsdGeom.Xformable(palm).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        expected = Gf.Matrix4d().SetRotate(Gf.Quatd(*MOUNT_ROT))
        expected.SetTranslateOnly(Gf.Vec3d(.1, .2, .3) + Gf.Vec3d(*MOUNT_POS))
        self.assertTrue(Gf.IsClose(transform, expected, 1e-7))
        self.assertEqual(hashlib.sha256(ASSET.read_bytes()).hexdigest(), before)
        with self.assertRaisesRegex(ValueError, 'already mounted'):
            mount_hand(robot)


if __name__ == '__main__':
    unittest.main()
