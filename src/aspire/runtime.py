"""Private IsaacLab backend. Import only after AppLauncher has started Kit."""
import json
import os
import math
import numpy as np
import torch
from .geometry import relative_point, quaternion_multiply, quat_matrix, rotate, vector
from .evaluator import Measurement

CAMERAS = dict(front="camera", wrist="grip_cam_b", top="cam_top",
               left="cam_left", right="cam_right", tray="cam_tray")


def configure_process(config):
    # Recorder sessions must not silently override this trial's contract.
    for name in ("P4_SESSION_CONFIG", "P4_RESUME_CAMERA_MANIFEST"):
        os.environ.pop(name, None)
    for name, value in dict(P4_CAMERA_SIZE=config.camera_size,
                            P4_DISTRACTOR_MIN=config.distractor_min,
                            P4_DISTRACTOR_MAX=config.distractor_max,
                            P4_RANDOMIZATION=config.randomization,
                            P4_RANDOMIZATION_SEED=17).items():
        os.environ[name] = str(value)


class IsaacBackend:
    def __init__(self, config, device="cuda:0"):
        configure_process(config)
        import gymnasium as gym
        import isaaclab_tasks  # registers the base lift task
        from isaaclab_tasks.utils import parse_env_cfg
        from phase3_shared_env_cfg import RecorderEnvRequest, INSTRUMENTS, apply_shared_env_cfg
        from .assets import apply_compatible_assets
        apply_compatible_assets(INSTRUMENTS)
        from phase3_recorder_camera_patch import phase3_apply_final_cameras_to_env_cfg, phase3_load_camera_tuning
        from phase4_scene import LAYOUT
        self.config, self.layout = config, LAYOUT
        self.key = lambda name: "object" if name == config.target else name
        self.names = tuple(INSTRUMENTS)
        cfg = parse_env_cfg("Isaac-Lift-Cube-Franka-IK-Abs-v0", device=device, num_envs=1)
        grip = phase3_load_camera_tuning().PHASE3_CAMERAS["grip_cam_b"]
        apply_shared_env_cfg(cfg, RecorderEnvRequest(target=config.target,
            distractors=tuple(n for n in self.names if n != config.target),
            environment=(), use_canonical_target_only=True), camera_width=config.camera_size,
            camera_height=config.camera_size,
            grip_camera_prim="{ENV_REGEX_NS}/Robot/panda_hand/GripCamB_Final",
            grip_pos=grip["pos"], grip_rot=grip["rot"])
        # Opt-in numerical audit; authored physics remains the default. Record
        # overrides in the task contract and apply the same settings to all tools.
        for name in self.names:
            props = getattr(cfg.scene, self.key(name)).spawn.rigid_props
            if config.solver_position_iterations is not None:
                props.solver_position_iteration_count = config.solver_position_iterations
            if config.solver_velocity_iterations is not None:
                props.solver_velocity_iteration_count = config.solver_velocity_iterations
        phase3_apply_final_cameras_to_env_cfg(cfg)
        for key in CAMERAS.values():
            camera = getattr(cfg.scene, key)
            camera.width = camera.height = config.camera_size
            camera.data_types = ["rgb", "distance_to_image_plane"]
        # Own reset and termination; inherited cube reward is never consumed.
        cfg.events.reset_object_position = None
        cfg.terminations.time_out = None
        cfg.terminations.object_dropping = None
        cfg.episode_length_s = 100000.
        cfg.commands.object_pose.debug_vis = False
        cfg.scene.ee_frame.debug_vis = False
        # Separate initial bodies before measuring their actual PhysX link frame.
        x0, x1 = LAYOUT["grid_x"]; y0, y1 = LAYOUT["grid_y"]
        nx, ny = LAYOUT["grid_cols"], LAYOUT["grid_rows"]
        for i, name in enumerate(self.names):
            row, col = divmod(2*i, nx)
            obj = getattr(cfg.scene, self.key(name))
            obj.init_state.pos = (x0+(col+.5)*(x1-x0)/nx, y0+(row+.5)*(y1-y0)/ny, .10)
            obj.init_state.rot = (math.sqrt(.5), -math.sqrt(.5), 0., 0.) if name == "scalpel" else (1., 0., 0., 0.)
        self.raw = gym.make("Isaac-Lift-Cube-Franka-IK-Abs-v0", cfg=cfg).unwrapped
        self.step_dt = float(self.raw.step_dt)
        from phase4_approach import configure
        configure(self.raw, True)
        self.ns = dict(PHASE3_TARGET_OBJECT=config.target, phase3_scene_key_for_object=self.key,
                       _p4_attempt_number=1)
        self._templates = None
        self.reset_report = {}

    @staticmethod
    def array(value):
        return value.detach().cpu().numpy().copy()

    def _base(self):
        robot = self.raw.scene["robot"]
        return self.array(robot.data.root_pos_w[0]), self.array(robot.data.root_quat_w[0])

    def _tcp_world(self):
        ee = self.raw.scene["ee_frame"]
        return self.array(ee.data.target_pos_w[0, 0]), self.array(ee.data.target_quat_w[0, 0])

    def robot_state(self):
        base, q = self._base(); pos, quat = self._tcp_world()
        inv = q.copy(); inv[1:] *= -1
        joints = self.array(self.raw.scene["robot"].data.joint_pos[0])
        return dict(position=relative_point(pos, base, q),
                    quaternion_wxyz=quaternion_multiply(inv, quat), finger_positions=joints[-2:].copy())

    @property
    def table_z_base(self):
        base, q = self._base()
        return float(relative_point([base[0], base[1], 0.], base, q)[2])

    def validate_action(self, action):
        # Broad reachable envelope, including the tray. IK convergence is checked separately.
        if np.linalg.norm(action[:3]) > 1.25 or not -.05 <= action[2] <= 1.0:
            raise ValueError("TCP action outside the workspace envelope")

    def constrain_pose(self, position, quaternion):
        from phase4_feedback import finger_floor_height
        base, q = self._base()
        world = rotate(q, position) + base
        world_q = quaternion_multiply(q, quaternion)
        target_q = torch.as_tensor(world_q, device=self.raw.device, dtype=torch.float32)
        world[2] = max(world[2], float(finger_floor_height(self.raw, torch, target_q)))
        result = relative_point(world, base, q)
        self.validate_action(np.r_[result, quaternion, 1.])
        return result

    def set_precision(self, skill):
        from phase4_approach import set_precision_skill
        set_precision_skill(self.raw, skill)

    def advance(self, action):
        value = torch.as_tensor(action, device=self.raw.device, dtype=torch.float32).unsqueeze(0)
        with torch.inference_mode():
            self.raw.step(value)

    def _hold(self):
        state = self.robot_state()
        return np.r_[state["position"], state["quaternion_wxyz"], 1.]

    def reset(self, *, seed, options):
        if set(options) - {"scene_snapshot"}:
            raise ValueError("Trial layout is specified in TaskConfig, not reset options")
        from phase4_reset import reset_robot, restore_objects
        from phase4_grasp_validation import rigid_world_points
        from phase4_cell_spawn import fit_spawn_to_cells, settled_cell_failures
        from phase4_tray_slots import select_occupancy, floor_heights, check_preloaded
        from phase3_settle_contract import settle_all_objects
        from phase4_runtime import bounded_settle
        from src.recorder import scene_clutter
        rng = np.random.default_rng(seed)
        os.environ["P4_RANDOMIZATION_SEED"] = str(seed)
        with torch.inference_mode():
            self.raw.reset(seed=seed)
            reset_robot(self.raw)
            # A first physics tick resolves authored root -> rigid link offsets.
            self.advance(self._hold())
            if self._templates is None:
                self._templates = {}
                for name in self.names:
                    obj = self.raw.scene[self.key(name)]
                    rigid_world_points(obj)
                    # A pre-settle body may still stand on its long axis. Orient
                    # its measured thin axis downward before seating its hull.
                    thin = int(np.argmin(np.ptp(obj._p4_link_corners, axis=0)))
                    flat = ((math.sqrt(.5),0.,math.sqrt(.5),0.) if thin == 0 else
                            (math.sqrt(.5),-math.sqrt(.5),0.,0.) if thin == 1 else (1.,0.,0.,0.))
                    self._templates[name] = dict(yaw=0., quat=np.asarray(flat), points=obj._p4_link_corners.copy())
            spawn = {n: dict(yaw_deg=float(rng.uniform(-180., 180.))) for n in self.names}
            spawn["grid"] = {}
            if self.config.yaw_deg is not None:
                spawn[self.config.target]["yaw_deg"] = self.config.yaw_deg
            fit_spawn_to_cells(spawn, self.config.target, rng, target_cell=self.config.target_cell)
            self.ns.update(_p4_spawn_templates=self._templates, _p4_force_args=(self.raw, spawn, "BROAD_FLAT"),
                _p4_cell_assignments=json.loads(spawn["grid"]["object_cell_assignments"]),
                _p4_tray_objects=select_occupancy(self.config.target, rng, {"tray_mode":self.config.tray_mode}))
            scene_clutter.park(self.raw, self.ns)
            floor_heights(self.ns)
            restore_objects(self.raw, self.ns, spawn)
            scene_clutter.prepare(self.raw, self.ns)
            if self.config.randomization == "train":
                from src.recorder.domain_randomization import apply_episode_lighting
                apply_episode_lighting(self.raw, self.ns)
            hold = torch.as_tensor(self._hold(), device=self.raw.device, dtype=torch.float32).unsqueeze(0)
            # Parked pool bodies are excluded; only active extras need settling.
            active = tuple(i["instance"] for i in self.ns.get("_p4_clutter", {}).get("instances", []))
            settle = bounded_settle(settle_all_objects, self.raw, hold, self.key, min_steps=150, poll_every=10,
                consecutive_ok=3, linear_speed_threshold=.003, names=self.names+active)
            self.reset_report = dict(seed=seed, spawn=spawn, settle=settle,
                                     clutter=self.ns.get("_p4_clutter", {}))
            self.reset_report["private_velocity_audit"] = {name: dict(
                actor_linear_velocity_w=self.array(self.raw.scene[self.key(name)].data.root_link_lin_vel_w[0]).tolist(),
                com_linear_velocity_w=self.array(self.raw.scene[self.key(name)].data.root_com_lin_vel_w[0]).tolist(),
                com_position_w=self.array(self.raw.scene[self.key(name)].data.root_com_pos_w[0]).tolist())
                for name in self.names}
            if not settle["success"]:
                raise RuntimeError("reset_settle_failed: " + settle["reason"])
            failures = settled_cell_failures(self.raw, self.ns)
            for correction in range(2):
                if not failures:
                    break
                settled_cell_failures(self.raw, self.ns, recenter=True)
                self.raw.scene.write_data_to_sim()
                settle = bounded_settle(settle_all_objects, self.raw, hold, self.key, min_steps=150,
                    poll_every=10, consecutive_ok=3, linear_speed_threshold=.003, names=self.names+active)
                self.reset_report.update(settle=settle, recenter_passes=correction+1)
                if not settle["success"]:
                    raise RuntimeError("reset_recenter_settle_failed")
                failures = settled_cell_failures(self.raw, self.ns)
            if failures:
                raise RuntimeError("reset_cell_validation_failed: " + str(failures))
            check_preloaded(self.raw, self.ns, capture=True)
            scene_clutter.validate(self.raw, self.ns)
            for _ in range(8):
                self.advance(self._hold())
        self.reset_report = dict(seed=seed, spawn=spawn, settle=settle,
                                 preloaded=self.ns["_p4_tray_initial"], clutter=self.ns.get("_p4_clutter", {}))
        if "scene_snapshot" in options:
            from .scene_replay import restore_scene
            self.reset_report["scene_replay"] = restore_scene(self, options["scene_snapshot"], seed)
        from phase4_feedback import rgb_has_spatial_detail
        for name in CAMERAS:
            if not rgb_has_spatial_detail(self.rgb(name)):
                raise RuntimeError("blank_camera: " + name)

    def rgb(self, name):
        if name not in CAMERAS:
            raise ValueError("Unknown camera: " + str(name))
        return self.array(self.raw.scene[CAMERAS[name]].data.output["rgb"][0, :, :, :3]).astype(np.uint8)

    def observation(self):
        base, q = self._base(); inv = q.copy(); inv[1:] *= -1
        cameras = {}
        for name, key in CAMERAS.items():
            sensor = self.raw.scene[key]
            pos = self.array(sensor.data.pos_w[0]); cq = self.array(sensor.data.quat_w_ros[0])
            pose = np.eye(4)
            pose[:3,:3] = quat_matrix(quaternion_multiply(inv, cq))
            pose[:3,3] = relative_point(pos, base, q)
            cameras[name] = dict(images=dict(rgb=self.rgb(name),
                depth=self.array(sensor.data.output["distance_to_image_plane"][0]).squeeze(-1)),
                intrinsics=self.array(sensor.data.intrinsic_matrices[0]), pose_mat=pose)
        state = self.robot_state()
        joints = self.array(self.raw.scene["robot"].data.joint_pos[0])
        return dict(cameras=cameras, robot=state,
                    proprio=np.r_[joints, state["position"], state["quaternion_wxyz"]])

    def tray_slot(self):
        from phase4_tray_slots import slot_spec
        spec = slot_spec(self.config.target, self.layout)
        base, q = self._base(); inv = q.copy(); inv[1:] *= -1
        center = relative_point([*spec["center_xy"], self.ns["_p4_tray_floors"][self.config.target]], base, q)
        return dict(slot_id=spec["slot_id"], center=center.tolist(), size=spec["size_local_xy"],
                    long_axis=rotate(inv, spec["long_axis_world"]).tolist(),
                    rim_z=float(self.ns["_p4_tray_rim_z"]-base[2]), frame="robot_base")

    def measure(self):
        from phase4_grasp_validation import rigid_world_points
        from phase4_tray_slots import slot_measurement, check_preloaded
        obj = self.raw.scene["object"]
        points = rigid_world_points(obj)
        slot = slot_measurement(obj, self.config.target, self.layout)
        preloaded_ok = True
        try:
            check_preloaded(self.raw, self.ns)
        except RuntimeError:
            preloaded_ok = False
        pos, q = self._tcp_world()
        return Measurement(pos, q, np.asarray(slot["center"]), float(points[:,2].min()),
            self.robot_state()["finger_positions"], slot, self.ns["_p4_tray_floors"][self.config.target],
            preloaded_ok, float(torch.linalg.norm(obj.data.root_lin_vel_w[0])))

    def close(self):
        self.raw.close()
