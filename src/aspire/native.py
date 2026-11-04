"""Surgical bindings for the upstream ASPIRE trial loop (not a search loop)."""
import json
import traceback
from pathlib import Path
from .bootstrap import UPSTREAM, setup_paths
from .execution import SurgicalExecutionEnv, validate_program


def upstream_regeneration_prompt():
    """Read the upstream Franka regeneration template verbatim."""
    setup_paths()
    from aspire.sim.cap.envs.configs.loader import DictLoader
    path = UPSTREAM/"aspire/sim/env_configs/robosuite/cube_lifting_multimodel_aspire_traced.yaml"
    return DictLoader.load([str(path)])["env"]["cfg"]["multi_turn_prompt"]


def last_executed_source(code_path):
    """Use the final trial artifact, not upstream's initial-only root snapshot."""
    turns = json.loads((Path(code_path).parent/"all_responses.json").read_text(encoding="utf-8"))
    executed = [turn for turn in turns if turn.get("code_blocks")]
    if not executed:
        raise ValueError("No executed code in final upstream trial artifact")
    return executed[-1]["code_blocks"][-1]


class NativeSurgicalExecutionEnv(SurgicalExecutionEnv):
    def __init__(self, low_level, *, execution_timeout=600., remaining_requests=lambda: 0,
                 generation_requests=9):
        super().__init__(low_level)
        self.execution_timeout = execution_timeout
        self.remaining_requests = remaining_requests
        self.generation_requests = generation_requests
        self.execution_turns = 0
        self.budget_stopped = False

    def reset(self, *, seed=None, options=None):
        options = dict(options or {})
        trial = options.pop("trial", seed)
        if trial != seed or options:
            raise ValueError("Only matching upstream trial metadata is accepted")
        return super().reset(seed=seed, options={})

    def _exec_user_code(self, code):
        # Syntax/API errors are feedback for the native regeneration loop.
        try:
            validate_program(code)
        except Exception:
            return dict(ok=False, stdout="", stderr=traceback.format_exc(), result=None)
        return super()._exec_user_code(code)

    def step(self, code):
        self.execution_turns += 1
        self.low_level_env.set_deadline(self.execution_timeout)
        obs, reward, terminated, truncated, info = super().step(code)
        if reward != 1. and not terminated and self.remaining_requests() < self.generation_requests:
            truncated = True
            self.budget_stopped = True
        return obs, reward, terminated, truncated, info


def native_trial_config(directory, *, revisions=3, ensemble=True):
    return dict(output_dir=str(Path(directory).resolve()), record_video=False,
        use_parallel_ensemble=ensemble, use_multimodel=False, use_oracle_code=False,
        use_visual_feedback=True, use_wrist_camera=True, use_img_differencing=False,
        use_video_differencing=False, save_multiturn_prompts=True,
        evolve_skill_library=False, max_code_blocks=1+revisions, stop_on_terminal=True)
