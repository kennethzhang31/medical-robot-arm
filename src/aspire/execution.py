"""Use the upstream code executor, with a surgical task API and bounded motion."""
import ast
from .bootstrap import setup_paths
setup_paths()
from aspire.sim.cap.envs.tasks.base import CodeExecEnvConfig, CodeExecutionEnvBase
from aspire.sim.cap.integrations.base_api import register_api
from .control import SurgicalControlApi


def validate_program(code):
    """Reject accidental raw-simulator/file/network use, not a security sandbox.

    Trials still execute Python. Run only trusted/reviewed programs on this
    workstation; adversarial Python needs an OS/container boundary.
    """
    tree = ast.parse(code)
    forbidden = {"env", "APIS", "open", "exec", "eval", "compile", "globals", "locals", "getattr", "setattr", "delattr", "vars", "breakpoint", "__import__", "input"}
    file_helpers = {"load", "loadtxt", "genfromtxt", "fromfile", "tofile", "save", "savetxt",
                    "savez", "savez_compressed", "memmap", "ctypeslib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and (node.id in forbidden or node.id.startswith("__")):
            raise ValueError(f"Program must use the public sensor/motor API: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError(f"Private attributes are not part of the skill API: {node.attr}")
        if isinstance(node, ast.Attribute) and node.attr in file_helpers:
            raise ValueError("File/native-memory helpers are not part of the skill API")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                binding = alias.asname or alias.name
                if binding in forbidden or binding.startswith("_") or alias.name.startswith("_") or alias.name in file_helpers:
                    raise ValueError("Private or reserved import binding")
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(name not in ("numpy", "math") for name in modules) or getattr(node, "level", 0):
                raise ValueError("Skill imports are limited to numpy and math")
    return tree


class SurgicalExecutionEnv(CodeExecutionEnvBase):
    def __init__(self, low_level):
        from .tracing import TracedSurgicalControlApi
        register_api("surgical-control", TracedSurgicalControlApi)
        super().__init__(CodeExecEnvConfig(low_level=low_level, apis=["surgical-control"],
                                         prompt=low_level.task_prompt, privileged=False))

    def _exec_user_code(self, code):
        validate_program(code)
        self._exec_globals["RESULT"] = None
        return super()._exec_user_code(code)

    def reset(self, *, seed=None, options=None):
        for api in self._apis.values():
            api.trace.reset()
        return super().reset(seed=seed, options=options)

    def step(self, code):
        # Upstream handles stdout, traceback capture and persistent program state.
        obs, reward, terminated, truncated, info = super().step(code)
        info["feedback"] = self.low_level_env.feedback()
        # Failure is terminal too; it must not be reported as successful termination.
        terminated = terminated or self.low_level_env._evaluator.failed
        return obs, reward, terminated, truncated, info

    def close(self):
        self.low_level_env.close()
