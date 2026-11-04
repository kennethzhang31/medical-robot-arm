"""Documented motor and RGB-D helpers bound into ASPIRE programs."""
import math
import numpy as np
from .bootstrap import setup_paths
setup_paths()
from aspire.sim.cap.integrations.base_api import ApiBase
from .geometry import (box_depth_mask, estimate_topdown_grasp, interpolate_quaternion, mask_to_points,
                       orientation_error, unit_quaternion, vector)


class SurgicalControlApi(ApiBase):
    def functions(self):
        functions = {name: getattr(self, name) for name in (
            "get_observation", "get_robot_state", "goto_pose", "open_gripper", "close_gripper",
            "wait", "get_tray_slot", "get_table_height", "get_tcp_floor", "get_task_feedback",
            "segment_instrument", "get_tabletop_candidates", "mask_to_robot_points", "estimate_grasp")}
        if not self._env.config.allow_evaluator_feedback:
            functions.pop("get_task_feedback")
        return functions

    def get_observation(self):
        """Return six cameras (RGB, metric depth, intrinsics, optical-camera-to-base
        pose_mat), proprio (9 joints + TCP XYZ + WXYZ), and task_target.
        Access RGB as obs['cameras'][camera]['images']['rgb']; depth is under
        the same 'images' dictionary. There is no camera-level 'rgb' key.
        No object poses, segmentation ground truth, grid IDs or expert stages.
        Camera names: front, wrist, top, left, right, tray.
        """
        return self._env.get_observation()

    def get_robot_state(self):
        """Return measured TCP position, WXYZ orientation and two finger encoders,
        all in the robot-base frame. This is proprioception, not a commanded pose.
        """
        return self._env._backend.robot_state()

    def goto_pose(self, position, quaternion_wxyz, *, duration_s=1., timeout_s=None,
                  position_tolerance=.003, angle_tolerance_deg=5., precision="pick"):
        """Interpolate then converge to an absolute TCP pose in robot-base metres.

        Args:
            position: Three finite XYZ values.
            quaternion_wxyz: Four values, normalized by the API.
            duration_s: Interpolation time in simulation seconds (positive).
            timeout_s: Total simulation-time budget; defaults to task configuration.
            position_tolerance: Measured Cartesian error, 0.00025..0.02 m.
                The 0.25 mm setting matches the original Love contact gate;
                requesting it does not guarantee the robot can converge.
            angle_tolerance_deg: Measured angular error, 1..15 degrees.
            precision: 'pick' or 'place'; place enables the existing bounded servo integral.

        Returns:
            Measured robot state. Raises on timeout, invalid command or task failure.
            The calibrated finger/table floor can raise a low requested target.
            This local IK controller does not provide global collision-free planning.
        """
        position, quaternion = vector(position, 3, "position"), unit_quaternion(quaternion_wxyz)
        timeout = self._env.config.motion_timeout_s if timeout_s is None else float(timeout_s)
        if not all(math.isfinite(v) for v in (duration_s, timeout, position_tolerance, angle_tolerance_deg)):
            raise ValueError("Motion parameters must be finite")
        if not 0 < duration_s < timeout <= 30 or not .00025 <= position_tolerance <= .02 or not 1 <= angle_tolerance_deg <= 15:
            raise ValueError("Invalid motion duration, budget or tolerances")
        if precision not in ("pick", "place"):
            raise ValueError("precision must be pick or place")
        if self._env.task_completed():
            return self.get_robot_state()
        backend = self._env._backend
        position = backend.constrain_pose(position, quaternion)
        backend.set_precision(precision)
        start = self.get_robot_state()
        dt = backend.step_dt
        interpolation = max(1, math.ceil(duration_s/dt))
        budget = math.ceil(timeout/dt)
        stable = 0
        for i in range(budget):
            fraction = min(1., (i+1)/interpolation)
            fraction = fraction*fraction*(3-2*fraction)
            p = np.asarray(start["position"]) + fraction*(position-start["position"])
            q = interpolate_quaternion(start["quaternion_wxyz"], quaternion, fraction)
            self._env._advance(np.r_[p, q, self._env._grip])
            state = self.get_robot_state()
            distance = float(np.linalg.norm(state["position"]-position))
            angle = orientation_error(state["quaternion_wxyz"], quaternion)
            converged = fraction == 1. and distance <= position_tolerance and angle <= math.radians(angle_tolerance_deg)
            stable = stable+1 if converged else 0
            if stable >= 4 or self._env.task_completed():
                return state
        raise RuntimeError(f"pose_timeout: measured_error={distance:.4f}m angle={math.degrees(angle):.1f}deg")

    def _gripper(self, closing, timeout_s):
        backend = self._env._backend
        if not math.isfinite(timeout_s) or not .2 <= timeout_s <= 3.:
            raise ValueError("Gripper timeout must be 0.2..3 simulation seconds")
        if self._env.task_completed():
            return self.get_robot_state()
        state = self.get_robot_state()
        hold, q = np.asarray(state["position"]), np.asarray(state["quaternion_wxyz"])
        command = -1. if closing else 1.
        history = []
        minimum = math.ceil((.24 if closing else .16)/backend.step_dt)
        from phase4_feedback import fingers_ready
        for i in range(math.ceil(timeout_s/backend.step_dt)):
            self._env._advance(np.r_[hold, q, command])
            if self._env.task_completed():
                return self.get_robot_state()
            current = self.get_robot_state()
            fingers = np.asarray(current["finger_positions"])
            history.append(fingers.tolist())
            history = history[-5:]
            velocity = (fingers-np.asarray(history[0]))/max((len(history)-1)*backend.step_dt, backend.step_dt)
            if (fingers_ready(history, closing, minimum, i+1)
                    and np.max(np.abs(velocity)) < .01
                    and np.linalg.norm(current["position"]-hold) < .008
                    and orientation_error(current["quaternion_wxyz"], q) < math.radians(10)):
                return current
        raise RuntimeError("finger_or_hold_timeout")

    def open_gripper(self, *, timeout_s=1.):
        """Open fingers while holding measured TCP pose; wait for encoder stability.
        Works at home and during release. Placement is verified independently.
        """
        return self._gripper(False, timeout_s)

    def close_gripper(self, *, timeout_s=1.2):
        """Close fingers while holding measured TCP pose; wait for encoder stability.
        Stable fingers do not prove a grasp. Lift and inspect sensor observations.
        """
        return self._gripper(True, timeout_s)

    def wait(self, seconds=.25):
        """Advance simulation seconds (0..5), holding measured TCP and last gripper command."""
        if not math.isfinite(seconds) or not 0 <= seconds <= 5:
            raise ValueError("wait must be 0..5 simulation seconds")
        state = self.get_robot_state()
        for _ in range(math.ceil(seconds/self._env._backend.step_dt)):
            if self._env.task_completed():
                break
            self._env._advance(np.r_[state["position"], state["quaternion_wxyz"], self._env._grip])

    def get_tray_slot(self):
        """Return fixed fixture calibration for the operator-requested instrument:
        center XYZ (support surface), long_axis vector, lane dimensions and rim_z,
        all in robot-base coordinates. This is a calibrated task goal; it is
        independent of the instrument's measured pose or the expert trajectory.
        """
        return self._env._backend.tray_slot()

    def get_table_height(self):
        """Return the fixed table support height in robot-base metres.
        Fixture calibration only; this never reads the target object's pose.
        """
        return float(self._env._backend.table_z_base)

    def get_task_feedback(self):
        """Return coarse task outcome flags/reason, as in the trial result.
        lift_verified and place_verified come from the independent evaluator;
        no object coordinates, mesh or expert actions are exposed. Use these
        flags to abort after an unverified lift or release, not finger stability.
        """
        return self._env.feedback()

    def get_tcp_floor(self, quaternion_wxyz, *, surface="table"):
        """Return a minimum TCP Z for the calibrated robot finger geometry.
        Uses the same orientation-dependent floor as goto_pose. 'table' keeps
        finger geometry 0.2 mm above the table. 'tray' adds the fixed tray-rim
        height and a 4.5 mm servo margin, matching the P4 placement floor.
        No target pose, mesh or grasp evidence is returned. Query is motionless.
        """
        if surface not in ("table", "tray"):
            raise ValueError("surface must be table or tray")
        quaternion = unit_quaternion(quaternion_wxyz)
        backend = self._env._backend
        position = vector(self.get_robot_state()["position"], 3, "position")
        table = self.get_table_height()
        position[2] = table
        floor = float(backend.constrain_pose(position, quaternion)[2])
        if surface == "tray":
            floor += float(self.get_tray_slot()["rim_z"]) - table + .0045
        return floor

    def segment_instrument(self, *, camera="top", text=None, point=None, box=None, allow_empty=False):
        """Return mask/box/score candidates from the configured perception backend.
        RF-DETR detects one of the five trained classes; text must be an exact
        class name (spaces may replace underscores). Its mask is a depth-derived
        foreground region inside the box, NOT a learned segmentation mask.
        Boxes intersecting another detected instrument are excluded because
        depth alone cannot separate nearby tools. Point prompts need SAM3.
        SAM3 accepts free text; optional point=(pixel_x,pixel_y) uses /segment_point.
        Optional box=[x1,y1,x2,y2] uses visual-exemplar SAM3 segmentation without
        target text; coordinates must come from current RGB-D, not saved scenes.
        Use get_tabletop_candidates to propose class-agnostic foreground boxes.
        Box prompts do not identify an instrument; inspect candidate RGB/geometry.
        A configured sam3_target_prompt maps default/canonical target queries to
        that text. All candidates are returned; no identity filtering or fusion
        is added. Other explicit text prompts are unchanged.
        No model or service is started by this call. No simulator labels are used.
        Set allow_empty=True when a missing detection should trigger another view.
        If unavailable, create a mask from visually selected pixels and use
        mask_to_robot_points / estimate_grasp directly.
        """
        from .perception import RfDetrClient, Sam3Client
        if self._env.config.perception_backend == "rfdetr":
            if box is not None:
                raise ValueError("RF-DETR does not support visual box prompts")
            if point is not None:
                raise ValueError("RF-DETR does not support point prompts")
            url = self._env.config.rfdetr_url
            if not url:
                raise RuntimeError("Configure rfdetr_url and start the trained RF-DETR service")
            target = self._env.config.target if text is None else text.strip().replace(" ", "_")
            from .config import INSTRUMENTS
            if target not in INSTRUMENTS:
                raise ValueError("RF-DETR text must name one of the five trained instrument classes")
            obs = self.get_observation()["cameras"][camera]
            detections = RfDetrClient(url).detect(obs["images"]["rgb"])
            results = []
            for index, row in enumerate(detections):
                if row["label"] != target:
                    continue
                x1, y1, x2, y2 = row["box"]
                if any(index != other_index and
                       max(x1, other["box"][0]) < min(x2, other["box"][2]) and
                       max(y1, other["box"][1]) < min(y2, other["box"][3])
                       for other_index, other in enumerate(detections)):
                    continue
                try:
                    mask = box_depth_mask(row["box"], obs["images"]["depth"],
                                          obs["intrinsics"], obs["pose_mat"],
                                          self._env._backend.table_z_base)
                except ValueError:
                    continue
                results.append(dict(row, mask=mask, mask_source="box_depth_foreground"))
            if not results and not allow_empty:
                raise RuntimeError("RF-DETR returned no isolated target with usable foreground depth")
            return results
        url = self._env.config.sam3_url
        if not url:
            raise RuntimeError("Configure sam3_url or supply a visual mask; no perception service is configured")
        rgb = self.get_observation()["cameras"][camera]["images"]["rgb"]
        if box is not None:
            return Sam3Client(url).segment(rgb, None, point=point, box=box, allow_empty=allow_empty)
        prompt = text or self._env.config.target.replace("_", " ")
        if (self._env.config.sam3_target_prompt is not None and
                (text is None or prompt.strip().replace(" ", "_") == self._env.config.target)):
            prompt = self._env.config.sam3_target_prompt
        return Sam3Client(url).segment(rgb, prompt,
                                       point=point, allow_empty=allow_empty)

    def get_tabletop_candidates(self, *, camera="top", min_points=12, max_candidates=16):
        """Return class-agnostic connected foreground regions from CURRENT RGB-D.
        Each row has box (source-image XYXY), mask (HxW boolean), point_count,
        center (base XYZ), extent_xy (base XY span), mask_source='depth_component'.
        Uses only depth/calibration and fixture table height. No target identity,
        simulator segmentation, object poses, or trained detector is used.
        Select the requested instrument using visible appearance/shape; do not
        assume list order or a fixed box identifies it. Occlusions split regions;
        touching tools can merge. Optional SAM3 box prompts can refine a region.
        """
        from .geometry import tabletop_candidates
        obs = self.get_observation()['cameras'][camera]
        return tabletop_candidates(obs['images']['depth'], obs['intrinsics'], obs['pose_mat'],
                                   self.get_table_height(), min_points=min_points,
                                   max_candidates=max_candidates)

    def mask_to_robot_points(self, mask, *, camera="top"):
        """Backproject a visually supplied HxW binary mask with current metric depth
        and camera calibration. Return Nx3 points in the robot-base frame.
        """
        obs = self.get_observation()["cameras"][camera]
        return mask_to_points(mask, obs["images"]["depth"], obs["intrinsics"], obs["pose_mat"])

    def estimate_grasp(self, mask, *, camera="top"):
        """Estimate a top-down candidate from a sensor mask: position, quaternion_wxyz,
        long_axis_yaw and point_count. Scissors require a full handle-and-blade
        mask: extent centering and broad-handle-to-tip direction are estimated
        visually. Other instruments use generic PCA. Not verified grasp success.
        The returned dictionary has exactly these four fields; it does not
        contain 'mask'. Retain the mask returned by segment_instrument separately
        when calling mask_to_robot_points(mask, camera=camera).
        """
        return estimate_topdown_grasp(self.mask_to_robot_points(mask, camera=camera),
            self._env._backend.table_z_base, ring_handles=self._env.config.target == "scissor")
