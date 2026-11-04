"""UR5 with the supplied closed-chain mirror hand, assembled before physics starts."""
from pathlib import Path

ASSET = Path(__file__).resolve().parents[1] / 'arm/mirror_hand_1013/mirror_hand_1013.usd'
ACTIVE_JOINTS = [f'finger{i}_{kind}_joint' for i in range(1, 6)
                 for kind in ('abduction', 'flexion')]
MOUNT_POS = (0., 0., .020)
MOUNT_ROT = (0., 1., 0., 0.)
WRIST_BODY = 'wrist_3_link'
ARM_JOINTS = ['shoulder_pan_joint', 'shoulder_lift_joint', 'elbow_joint',
              'wrist_1_joint', 'wrist_2_joint', 'wrist_3_joint']


def mount_hand(robot):
    """Fix the palm to the UR5 tool flange, preserving the passive mechanisms."""
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    stage, path = robot.GetStage(), robot.GetPath()
    wrist = stage.GetPrimAtPath(path.AppendChild(WRIST_BODY))
    if not wrist or not wrist.HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError('Expected the UR5 wrist_3_link rigid body')
    if stage.GetPrimAtPath(path.AppendChild('MirrorHand')):
        raise ValueError('MirrorHand is already mounted')
    if not ASSET.is_file():
        raise FileNotFoundError(ASSET)

    adapter_body = UsdGeom.Xform.Define(stage, path.AppendChild('hand_mount_link'))
    wrist_matrix = UsdGeom.Xformable(wrist).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    robot_matrix = UsdGeom.Xformable(robot).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    adapter_body.AddTransformOp().Set(wrist_matrix * robot_matrix.GetInverse())
    UsdPhysics.RigidBodyAPI.Apply(adapter_body.GetPrim())
    mass = UsdPhysics.MassAPI.Apply(adapter_body.GetPrim())
    mass.CreateMassAttr(.015)
    mass.CreateCenterOfMassAttr(Gf.Vec3f(0., 0., .002))
    mass.CreateDiagonalInertiaAttr(Gf.Vec3f(2.3e-6, 2.3e-6, 4.3e-6))
    mass.CreatePrincipalAxesAttr(Gf.Quatf(1.))
    adapter = UsdGeom.Cylinder.Define(stage, adapter_body.GetPath().AppendChild('HandAdapter'))
    adapter.CreateRadiusAttr(.024)
    adapter.CreateHeightAttr(.004)
    adapter.AddTranslateOp().Set(Gf.Vec3d(0., 0., .002))
    adapter.CreateDisplayColorAttr([Gf.Vec3f(.25, .27, .29)])
    UsdPhysics.CollisionAPI.Apply(adapter.GetPrim())
    adapter_joint = UsdPhysics.FixedJoint.Define(stage, path.AppendChild('hand_adapter_joint'))
    adapter_joint.CreateBody0Rel().SetTargets([wrist.GetPath()])
    adapter_joint.CreateBody1Rel().SetTargets([adapter_body.GetPath()])
    adapter_joint.CreateLocalPos0Attr(Gf.Vec3f(0.))
    adapter_joint.CreateLocalPos1Attr(Gf.Vec3f(0.))
    adapter_joint.CreateLocalRot0Attr(Gf.Quatf(1.))
    adapter_joint.CreateLocalRot1Attr(Gf.Quatf(1.))
    adapter_joint.CreateCollisionEnabledAttr(False)

    hand = UsdGeom.Xform.Define(stage, path.AppendChild('MirrorHand'))
    hand.GetPrim().GetReferences().AddReference(str(ASSET))
    hand.GetPrim().RemoveAPI(UsdPhysics.ArticulationRootAPI)
    stage.GetPrimAtPath(hand.GetPath().AppendPath('Physics/root_joint')).SetActive(False)
    mount = Gf.Matrix4d().SetRotate(Gf.Quatd(*MOUNT_ROT))
    mount.SetTranslateOnly(Gf.Vec3d(*MOUNT_POS))
    hand.AddTransformOp().Set(mount * wrist_matrix * robot_matrix.GetInverse())

    joint = UsdPhysics.FixedJoint.Define(stage, path.AppendChild('mirror_hand_mount'))
    joint.CreateBody0Rel().SetTargets([adapter_body.GetPath()])
    joint.CreateBody1Rel().SetTargets([hand.GetPath().AppendPath('Links/palm_link')])
    joint.CreateLocalPos0Attr(Gf.Vec3f(*MOUNT_POS))
    joint.CreateLocalRot0Attr(Gf.Quatf(*MOUNT_ROT))
    joint.CreateLocalPos1Attr(Gf.Vec3f(0.))
    joint.CreateLocalRot1Attr(Gf.Quatf(1.))
    joint.CreateCollisionEnabledAttr(False)
    robot.SetCustomDataByKey('end_effector', 'mirror_hand_1013')
    robot.SetCustomDataByKey('robot_model', 'UR5')
    return hand.GetPrim()


def spawn_with_hand(prim_path, cfg, translation=None, orientation=None, **kwargs):
    from isaaclab.sim.spawners.from_files import spawn_from_usd
    prim = spawn_from_usd(prim_path, cfg, translation=translation, orientation=orientation, **kwargs)
    mount_hand(prim)
    return prim


def create_robot_cfg(prim_path='/World/Robot'):
    """Use the classic UR5 geometry, six arm joints and ten driven hand joints."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import ArticulationCfg
    from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR

    robot_cfg = ArticulationCfg(
        prim_path=prim_path,
        spawn=sim_utils.UsdFileCfg(
            usd_path=ISAAC_NUCLEUS_DIR + '/Robots/UniversalRobots/ur5/ur5.usd',
            func=spawn_with_hand,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(disable_gravity=False),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=False, solver_position_iteration_count=32,
                solver_velocity_iteration_count=4)),
        init_state=ArticulationCfg.InitialStateCfg(joint_pos={
            'shoulder_pan_joint': 0., 'shoulder_lift_joint': -1.2, 'elbow_joint': 1.6,
            'wrist_1_joint': -1.9707963268, 'wrist_2_joint': -1.5707963268,
            'wrist_3_joint': 0., 'finger[1-5]_.*_joint': 0.}),
        actuators={
            'arm': ImplicitActuatorCfg(joint_names_expr=ARM_JOINTS[:3],
                effort_limit_sim=150., velocity_limit_sim=3.1415926536,
                stiffness=1008.44, damping=40.),
            'wrist': ImplicitActuatorCfg(joint_names_expr=ARM_JOINTS[3:],
                effort_limit_sim=28., velocity_limit_sim=3.1415926536,
                stiffness=379.823, damping=15.),
        })
    robot_cfg.actuators['mirror_hand'] = ImplicitActuatorCfg(
        joint_names_expr=['finger[1-5]_(abduction|flexion)_joint'],
        effort_limit_sim=.25, velocity_limit_sim=1., stiffness=.3, damping=.01)
    # Passive coordinates participate in physics but must never receive a drive.
    robot_cfg.actuators['passive_fourbar'] = ImplicitActuatorCfg(
        joint_names_expr=['finger[1-5]_(distal|link)_joint'],
        effort_limit_sim=0., stiffness=0., damping=0.)
    return robot_cfg
