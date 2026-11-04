"""Preview and smoke-test the UR5 with the mirror hand in the hospital scene."""
import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.aspire.bootstrap import setup_paths
setup_paths()
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frames', type=int, default=1200)
parser.add_argument('--out', type=Path, default=ROOT / 'exports/ur5_mirror_hand')
parser.add_argument('--standalone', action='store_true', help='Use an empty scene for the physics check')
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
if args.frames < 1:
    parser.error('--frames must be positive')
args.enable_cameras = True
args.kit_args += (' --/app/vulkan=false --/app/renderer/multiGpu/enabled=false'
                  ' --/rtx/post/aa/op=2 --/rtx-transient/dlssg/enabled=false')
app = AppLauncher(args).app
print('MIRROR_HAND: application ready', flush=True)
preview_exit_code = 0

try:
    import torch
    import isaaclab.sim as sim_utils
    from isaaclab.assets import Articulation, RigidObject, RigidObjectCfg
    from isaaclab.sensors import Camera, CameraCfg
    from pxr import UsdPhysics
    from env.mirror_hand import ACTIVE_JOINTS, ARM_JOINTS, MOUNT_POS, WRIST_BODY, create_robot_cfg
    from isaaclab.utils.math import quat_apply

    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1/120, device=args.device))
    print('MIRROR_HAND: building scene', flush=True)
    view_eye, view_target = (1.45, 1.65, 1.25), (.25, -.25, .20)
    sim.set_camera_view(eye=view_eye, target=view_target)
    light = sim_utils.DomeLightCfg(intensity=1800., color=(.85, .90, 1.))
    light.func('/World/Light', light)
    cfg = create_robot_cfg()
    tools = {}
    ground_z = 0.
    if not args.standalone:
        from phase4_scene import (LAYOUT, table_geometry, spawn_hospital, spawn_sensor_safe_light,
                                  spawn_centered_tray, tray_scale_for_layout)
        from phase3_shared_env_cfg import LIGHTING, INSTRUMENTS, ASSET_DIR, INSTRUMENT_MATERIAL_OVERRIDES
        from env.instrument_materials import spawn_satin_instrument
        from src.aspire.assets import apply_compatible_assets
        geometry = table_geometry()
        room_cfg = sim_utils.UsdFileCfg(usd_path=str(ROOT / 'assets' / LAYOUT['hospital_asset']))
        spawn_hospital('/World/HospitalRoom', room_cfg,
                       translation=geometry['room_pos'], orientation=geometry['room_rot'])
        # The room blocks the dome; use the recorder's local work lights as well.
        for name in ('key', 'fill'):
            intensity = LAYOUT.get('lighting', {}).get(
                f'shared_{name}_light', getattr(LIGHTING, f'{name}_intensity'))
            local_light = sim_utils.SphereLightCfg(
                intensity=intensity, color=getattr(LIGHTING, f'{name}_color'),
                radius=getattr(LIGHTING, f'{name}_radius'))
            spawn_sensor_safe_light(f'/World/{name.title()}Light', local_light,
                                    translation=getattr(LIGHTING, f'{name}_pos'))
        cfg.init_state.pos = tuple(LAYOUT['robot_pos'])
        cfg.init_state.rot = tuple(LAYOUT['robot_rot_wxyz'])
        ground_z = geometry['room_pos'][2] - .01
        apply_compatible_assets(INSTRUMENTS)
        tool_layout = json.loads((ROOT / 'env/mirror_hand_tool_layout.json').read_text())
        from src.recorder.scene_clutter import pool, prepare as prepare_clutter
        tool_types = {name: name for name in INSTRUMENTS}
        tool_types.update(pool('scalpel'))
        for name, kind in tool_types.items():
            spec = INSTRUMENTS[kind]
            placement = tool_layout['positions'].get(kind)
            x, y = placement['x'], placement['y']
            material = INSTRUMENT_MATERIAL_OVERRIDES.get(kind)
            tool = RigidObject(RigidObjectCfg(
                prim_path=f'/World/Tools/{name}',
                spawn=sim_utils.UsdFileCfg(
                    usd_path=str(ASSET_DIR / spec.usd), func=spawn_satin_instrument, scale=spec.scale,
                    semantic_tags=[('class', kind)],
                    visual_material=sim_utils.PreviewSurfaceCfg(
                        diffuse_color=material.diffuse_color, metallic=material.metallic,
                        roughness=material.roughness) if material else None,
                    rigid_props=sim_utils.RigidBodyPropertiesCfg(
                        disable_gravity=False, linear_damping=.8, angular_damping=4.),
                    collision_props=sim_utils.CollisionPropertiesCfg(
                        contact_offset=spec.contact_offset, rest_offset=spec.rest_offset),
                    mass_props=sim_utils.MassPropertiesCfg(mass=spec.mass)),
                init_state=RigidObjectCfg.InitialStateCfg(
                    pos=(x, y, .05) if name in INSTRUMENTS else (3., 3., -2.))))
            tools[name] = (tool, x, y)
        tray_path = str(ASSET_DIR / 'SurgicalTray.usd')
        tray_cfg = sim_utils.UsdFileCfg(usd_path=tray_path, scale=tray_scale_for_layout(tray_path),
                                      semantic_tags=[('class', 'surgical_tray')])
        tray_yaw = math.radians(LAYOUT['tray_yaw_deg']) / 2
        spawn_centered_tray('/World/RandomTray', tray_cfg,
            translation=(*LAYOUT['tray_xy'], LAYOUT['tray_root_z']),
            orientation=(math.cos(tray_yaw), 0., 0., math.sin(tray_yaw)))
    ground = sim_utils.GroundPlaneCfg()
    ground.func('/World/Ground', ground, translation=(0., 0., ground_z))
    robot = Articulation(cfg)
    stage = sim.stage
    camera = Camera(CameraCfg(
        prim_path='/World/InspectionCamera', width=960, height=720, data_types=['rgb'],
        spawn=sim_utils.PinholeCameraCfg(focal_length=24., clipping_range=(.01, 10.))))
    args.out.mkdir(parents=True, exist_ok=True)
    # This layer references the supplied assets, which are never rewritten.
    stage.GetRootLayer().Export(str(args.out / 'mounted_hand.usda'))
    sim.reset()
    if tools:
        from types import SimpleNamespace
        from phase4_reset import table_pose
        from phase4_grasp_validation import rigid_world_points
        templates = {}
        for name, (tool, x, y) in tools.items():
            if name not in INSTRUMENTS:
                continue
            tool.update(sim.get_physics_dt())
            rigid_world_points(tool)
            # All five tools have a thin local Y axis; place that axis upright.
            templates[name] = dict(yaw=0., quat=(math.sqrt(.5), math.sqrt(.5), 0., 0.),
                                   points=tool._p4_link_corners)
            pose = table_pose(templates[name], x, y, tool_layout['positions'][name]['yaw_deg'])
            tool.write_root_link_pose_to_sim(torch.tensor([pose.tolist()], device=robot.device,
                                                          dtype=tool.data.root_state_w.dtype))
            tool.write_root_velocity_to_sim(torch.zeros_like(tool.data.root_state_w[:, 7:13]))
        # Reuse the recorder's seeded footprint packing for the original extra copies.
        class ToolScene(dict):
            def write_data_to_sim(self):
                for tool in self.values():
                    tool.write_data_to_sim()

        scene = ToolScene({name: item[0] for name, item in tools.items()})
        for _ in range(360):
            sim.step(render=False)
        for name in INSTRUMENTS:
            tool = scene[name]
            tool.update(sim.get_physics_dt())
            points = rigid_world_points(tool)
            center = (points.min(axis=0) + points.max(axis=0)) / 2
            pose = tool.data.root_link_state_w[:, :7].clone()
            pose[0, 0] += tools[name][1] - center[0]
            pose[0, 1] += tools[name][2] - center[1]
            tool.write_root_link_pose_to_sim(pose)
            tool.write_root_velocity_to_sim(torch.zeros_like(tool.data.root_state_w[:, 7:13]))
            tool.update(sim.get_physics_dt())
            templates[name].update(yaw=tool_layout['positions'][name]['yaw_deg'],
                quat=tool.data.root_link_quat_w[0].cpu().numpy().copy())
        namespace = dict(PHASE3_TARGET_OBJECT='scalpel',
            phase3_scene_key_for_object=lambda name: name, _p4_spawn_templates=templates,
            _p4_force_args=[None, {'grid': {}}])
        prepare_clutter(SimpleNamespace(scene=scene, sim=sim, device=robot.device,
                                       physics_dt=sim.get_physics_dt()), namespace)
        active_tools = set(INSTRUMENTS) | {
            item['instance'] for item in namespace['_p4_clutter']['instances']}
        tools = {name: item for name, item in tools.items() if name in active_tools}
        print(f'MIRROR_HAND: {len(tools)} working instruments and surgical tray loaded; '
              f'base positions restored from {tool_layout["source"]}', flush=True)
    camera.set_world_poses_from_view(
        torch.tensor([view_eye], device=robot.device),
        torch.tensor([view_target], device=robot.device))
    robot.update(sim.get_physics_dt())
    _, names = robot.find_joints(ACTIVE_JOINTS, preserve_order=True)
    assert names == ACTIVE_JOINTS, names
    assert not any(name.startswith('panda_') for name in robot.joint_names + robot.body_names)
    arm_ids, arm_names = robot.find_joints(ARM_JOINTS, preserve_order=True)
    assert arm_names == ARM_JOINTS and len(arm_ids) == 6, arm_names
    assert robot.num_joints == 26, robot.joint_names
    flex_ids, _ = robot.find_joints('finger[1-5]_flexion_joint')
    abd_ids, _ = robot.find_joints('finger[1-5]_abduction_joint')
    wrist_joint_ids, _ = robot.find_joints('wrist_3_joint')
    palm_id = robot.find_bodies('palm_link')[0][0]
    wrist_id = robot.find_bodies(WRIST_BODY)[0][0]
    max_mount_error = 0.
    max_closure_error = 0.
    min_flex = [float('inf')] * 5
    max_flex = [-float('inf')] * 5
    min_abd = [float('inf')] * 5
    max_abd = [-float('inf')] * 5
    completed = 0
    for frame in range(args.frames):
        if not app.is_running():
            break
        target = robot.data.default_joint_pos.clone()
        # A conservative motion check, below the unvalidated full travel limits.
        phase = 2 * math.pi * frame / 480
        target[:, flex_ids] = math.radians(10.) * (1 - math.cos(phase)) / 2
        target[:, abd_ids] = math.radians(3.) * math.sin(phase)
        target[:, wrist_joint_ids] += math.radians(5.) * math.sin(phase)
        robot.set_joint_position_target(target)
        robot.write_data_to_sim()
        sim.step(render=not args.headless)
        robot.update(sim.get_physics_dt())
        completed += 1
        assert torch.isfinite(robot.data.joint_pos).all(), 'Non-finite joint state'
        expected = robot.data.body_pos_w[:, wrist_id] + quat_apply(
            robot.data.body_quat_w[:, wrist_id], torch.tensor([MOUNT_POS], device=robot.device))
        error = torch.linalg.vector_norm(robot.data.body_pos_w[:, palm_id] - expected).item()
        max_mount_error = max(max_mount_error, error)
        positions = robot.data.joint_pos[0, flex_ids].tolist()
        for i, value in enumerate(positions):
            min_flex[i] = min(min_flex[i], value)
            max_flex[i] = max(max_flex[i], value)
        for i, value in enumerate(robot.data.joint_pos[0, abd_ids].tolist()):
            min_abd[i] = min(min_abd[i], value)
            max_abd[i] = max(max_abd[i], value)
        # Measure the actual loop endpoints using live rigid-body poses.
        for i in range(1, 6):
            joint = UsdPhysics.RevoluteJoint(stage.GetPrimAtPath(
                f'/World/Robot/MirrorHand/fourbar_closures/finger{i}_closure_joint'))
            endpoints = []
            for relation, attr in ((joint.GetBody0Rel(), joint.GetLocalPos0Attr()),
                                   (joint.GetBody1Rel(), joint.GetLocalPos1Attr())):
                body_id = robot.find_bodies(relation.GetTargets()[0].name)[0][0]
                local = torch.tensor([list(attr.Get())], device=robot.device)
                endpoints.append(robot.data.body_pos_w[:, body_id] + quat_apply(
                    robot.data.body_quat_w[:, body_id], local))
            max_closure_error = max(max_closure_error,
                torch.linalg.vector_norm(endpoints[0] - endpoints[1]).item())
    assert completed > 0, 'Preview closed before the first physics step'
    tool_positions = {}
    for name, (tool, x, y) in tools.items():
        tool.update(sim.get_physics_dt())
        points = rigid_world_points(tool)
        low, high = points.min(axis=0), points.max(axis=0)
        assert low[2] > -.01 and low[2] < .02, (name, low, high)
        for axis, key in enumerate(('grid_x', 'grid_y')):
            assert low[axis] >= LAYOUT[key][0] and high[axis] <= LAYOUT[key][1], (name, low, high)
        if name in INSTRUMENTS:
            assert abs((low[0] + high[0]) / 2 - x) < .003, (name, low, high)
            assert abs((low[1] + high[1]) / 2 - y) < .003, (name, low, high)
        tool_positions[name] = dict(center_w=((low + high) / 2).tolist(), bottom_z_m=float(low[2]))
    report = dict(robot_model='UR5', arm_joints=arm_names, frames=completed,
                  active_joints=names, joint_count=robot.num_joints,
                  tools=tool_positions,
                  wrist_position_w=robot.data.body_pos_w[0, wrist_id].tolist(),
                  max_mount_error_m=max_mount_error, max_closure_error_m=max_closure_error,
                  flexion_motion_deg=[math.degrees(b-a) for a, b in zip(min_flex, max_flex)],
                  abduction_motion_deg=[math.degrees(b-a) for a, b in zip(min_abd, max_abd)])
    (args.out / 'smoke_test.json').write_text(json.dumps(report, indent=2) + '\n')
    print('MIRROR_HAND_RESULT', json.dumps(report), flush=True)
    assert max_mount_error < .001, report
    assert max_closure_error < .001, report
    if completed >= 480:
        assert min(report['flexion_motion_deg']) > 5., report
        assert min(report['abduction_motion_deg']) > 1., report
    from PIL import Image
    for name, closeup in (('overview', False), ('hand_closeup', True)):
        if closeup:
            center = robot.data.body_pos_w[:, palm_id].clone()
            camera.set_world_poses_from_view(center + torch.tensor([[.25, .30, .18]], device=robot.device), center)
        for _ in range(12):
            sim.render()
        camera.update(sim.get_physics_dt(), force_recompute=True)
        rgb = camera.data.output['rgb'][0, :, :, :3].cpu().numpy()
        Image.fromarray(rgb).save(args.out / (name + '.png'))
except BaseException:
    import traceback
    traceback.print_exc()
    sys.stderr.flush()
    preview_exit_code = 1
finally:
    # This runtime can hang in native shutdown with another Kit process open.
    if args.headless:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(preview_exit_code)
    app.close(wait_for_replicator=False)
if preview_exit_code:
    raise SystemExit(preview_exit_code)
