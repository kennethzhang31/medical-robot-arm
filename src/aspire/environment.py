"""ASPIRE BaseEnv adapter over a single IsaacLab scene."""
import time
import numpy as np
from .bootstrap import setup_paths
setup_paths()
from aspire.sim.cap.envs.base import BaseEnv
from gymnasium import Env, spaces
from .evaluator import TaskEvaluator
from .geometry import unit_quaternion, vector


class EpisodeStopped(RuntimeError):
    pass


class SurgicalEnv(BaseEnv):
    """The backend owns Isaac state; observations contain sensors and commands."""
    privileged = False
    viser_debug = False

    def __init__(self, backend, config, *, artifact_sink=None):
        super().__init__()
        self._backend, self.config = backend, config
        self.max_steps = config.max_steps
        self._sim_step_count = 0
        self._evaluator = TaskEvaluator()
        self._ready = False
        self._grip = 1.
        self._sink = artifact_sink
        self._deadline = None
        self._capture = False
        self._frame_buffer, self._wrist_frame_buffer = [], []
        self.action_space = spaces.Box(-np.inf, np.inf, (8,), dtype=np.float32)
        size = config.camera_size
        camera_space = spaces.Dict({
            "images": spaces.Dict({"rgb":spaces.Box(0,255,(size,size,3),dtype=np.uint8),
                                   "depth":spaces.Box(0,np.inf,(size,size),dtype=np.float32)}),
            "intrinsics":spaces.Box(-np.inf,np.inf,(3,3),dtype=np.float32),
            "pose_mat":spaces.Box(-np.inf,np.inf,(4,4),dtype=np.float64)})
        self.observation_space = spaces.Dict({
            "cameras":spaces.Dict({name:camera_space for name in ("front","wrist","top","left","right","tray")}),
            "robot":spaces.Dict({"position":spaces.Box(-np.inf,np.inf,(3,),dtype=np.float64),
                "quaternion_wxyz":spaces.Box(-1.,1.,(4,),dtype=np.float64),
                "finger_positions":spaces.Box(0.,.05,(2,),dtype=np.float32)}),
            "proprio":spaces.Box(-np.inf,np.inf,(16,),dtype=np.float64),
            "task_target":spaces.Text(32,charset="abcdefghijklmnopqrstuvwxyz_")})

    def reset(self, *, seed=None, options=None):
        Env.reset(self, seed=seed)
        effective_seed = int(self.np_random.integers(0, 2**31)) if seed is None else int(seed)
        self._ready = False
        self._sim_step_count = 0
        self._deadline = None
        self._grip = 1.
        self._frame_buffer.clear()
        self._wrist_frame_buffer.clear()
        self._backend.reset(seed=effective_seed, options=options or {})
        self._evaluator.reset(self._backend.measure())
        self._ready = True
        obs = self.get_observation()
        if self._sink:
            self._sink.observation("initial", obs)
        self._record_frame(force=True)
        return obs, {"task_prompt": self.task_prompt, "seed": effective_seed}

    @property
    def task_prompt(self):
        return (f"Pick the {self.config.target.replace('_', ' ')} from the table and place it "
                "in its designated tray lane. Lift it clear, transport without dropping, "
                "open the fingers, and retreat until it rests in the lane. "
                "Preserve preloaded instruments. Use sensor observations and the public API only. "
                "All motion poses use robot-base XYZ metres and WXYZ quaternions. "
                "Fixture calibration is supplied by get_tray_slot(); it contains no target-object pose.")

    def set_deadline(self, seconds):
        self._deadline = time.monotonic() + seconds

    def _check_running(self):
        if not self._ready:
            raise EpisodeStopped("Call reset before motion")
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise EpisodeStopped("trial_wall_timeout")
        if self._sim_step_count >= self.max_steps:
            raise EpisodeStopped("simulation_step_budget_exhausted")
        if self._evaluator.failed:
            raise EpisodeStopped(self._evaluator.reason)
        if self.task_completed():
            raise EpisodeStopped("task_already_completed")

    def _advance(self, action, *, stop_on_failure=True):
        self._check_running()
        action = vector(action, 8, "absolute TCP action")
        action[3:7] = unit_quaternion(action[3:7])
        if action[7] not in (-1., 1.):
            raise ValueError("Gripper command must be +1 (open) or -1 (close)")
        self._backend.validate_action(action)
        self._backend.advance(action)
        self._sim_step_count += 1
        self._grip = float(action[7])
        self._evaluator.update(self._backend.measure(), self._grip)
        if self._sink:
            self._sink.action(self._sim_step_count, action, self._evaluator.feedback())
        self._record_frame()
        if self._evaluator.failed and stop_on_failure:
            raise EpisodeStopped(self._evaluator.reason)

    def step(self, action):
        self._advance(action, stop_on_failure=False)
        return (self.get_observation(), self.compute_reward(), self.task_completed() or self._evaluator.failed,
                self._sim_step_count >= self.max_steps, self.feedback())

    def get_observation(self):
        observation = self._backend.observation()
        observation["task_target"] = self.config.target
        return observation

    def compute_reward(self):
        return float(self.task_completed())

    def task_completed(self):
        return self._ready and self._evaluator.place_verified and not self._evaluator.failed

    def feedback(self):
        return dict(self._evaluator.feedback(), sim_steps=self._sim_step_count)

    def render(self, mode="rgb_array"):
        if mode != "rgb_array":
            raise ValueError("Only rgb_array is supported")
        return self._backend.rgb("front")

    def render_wrist(self):
        return self._backend.rgb("wrist")

    def enable_video_capture(self, enabled=True, *, clear=True, wrist_camera=False):
        self._capture = enabled
        self._capture_wrist = wrist_camera
        if clear:
            self._frame_buffer.clear()
            self._wrist_frame_buffer.clear()

    def _record_frame(self, force=False):
        if not force and self._sim_step_count % self.config.video_stride:
            return
        if self._sink:
            self._sink.frame(self._sim_step_count, self._backend.rgb("front"), self._backend.rgb("wrist"))
        if self._capture:
            self._frame_buffer.append(self.render().copy())
            if getattr(self, "_capture_wrist", False):
                self._wrist_frame_buffer.append(self.render_wrist().copy())

    def get_video_frames(self, *, clear=False):
        frames = [frame.copy() for frame in self._frame_buffer]
        if clear:
            self._frame_buffer.clear()
        return frames

    def get_wrist_video_frames(self, *, clear=False):
        frames = [frame.copy() for frame in self._wrist_frame_buffer]
        if clear:
            self._wrist_frame_buffer.clear()
        return frames

    def close(self):
        self._ready = False
        self._backend.close()
