"""Run the upstream ASPIRE trial loop on one disposable Isaac surgical scene."""
import argparse
import json
import sys
import time
import traceback
import urllib.request
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import setup_paths, upstream_revision
setup_paths()
from src.aspire.artifacts import Artifacts, write_json
from src.aspire.config import load_protocol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--relay-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--seed", type=int, default=501)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--revisions", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=128000)
    parser.add_argument("--provider-timeout", type=float, default=1800.)
    parser.add_argument("--execution-timeout", type=float, default=600.)
    parser.add_argument("--initial-code")
    from isaaclab.app import AppLauncher
    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args()
    directory = Path(args.out)
    sink = Artifacts(directory/"sensor_artifacts")
    result = dict(status="starting", seed=args.seed, success=False, execution_ok=False,
        aspire_commit=upstream_revision(), pipeline="upstream_native_trial", candidates=args.candidates,
        max_revision_rounds=args.revisions)
    started = time.monotonic()
    app = backend = env = None

    def checkpoint(status):
        result["status"] = status
        write_json(directory/"result.json", result)

    def remaining():
        with urllib.request.urlopen(args.relay_url+"/budget", timeout=10) as response:
            return json.load(response)["remaining"]

    try:
        protocol, task = load_protocol(args.config)
        if args.seed not in protocol["development_seeds"]:
            raise ValueError("Native smoke test must use a development seed")
        write_json(directory/"contract.json", protocol)
        args.enable_cameras = True
        args.kit_args += " --/rtx/post/aa/op=2 --/rtx-transient/dlssg/enabled=false"
        checkpoint("launching_kit")
        app = AppLauncher(args).app
        from src.aspire.runtime import IsaacBackend
        from src.aspire.environment import SurgicalEnv
        from src.aspire.native import NativeSurgicalExecutionEnv, native_trial_config, upstream_regeneration_prompt
        from aspire.sim.cap.envs.trial import _run_single_trial
        from aspire.sim.cap.llm.client import VLM_MODELS
        if args.model not in VLM_MODELS:
            VLM_MODELS.append(args.model)
        checkpoint("building_scene")
        backend = IsaacBackend(task, device=args.device)
        env = SurgicalEnv(backend, task, artifact_sink=sink)
        execution = NativeSurgicalExecutionEnv(env, execution_timeout=args.execution_timeout,
            remaining_requests=remaining, generation_requests=args.candidates+1)
        native_args = SimpleNamespace(model=args.model, server_url=args.relay_url+"/chat/completions",
            api_key=None, temperature=1., max_tokens=args.max_output_tokens,
            ensemble_size=args.candidates, request_timeout_s=args.provider_timeout+30,
            reasoning_effort="medium", debug=True, use_legacy_multi_turn_decision_prompt=False,
            visual_differencing_model=args.model, visual_differencing_model_server_url=args.relay_url+"/chat/completions",
            visual_differencing_model_api_key=None)
        config = native_trial_config(directory, revisions=args.revisions)
        if args.initial_code:
            from src.aspire.execution import validate_program
            initial_source = Path(args.initial_code).read_text(encoding="utf-8")
            validate_program(initial_source)
            execution.oracle_code = initial_source
            config["use_oracle_code"] = True  # Upstream's supplied-program path, not privileged control.
            result["initial_code"] = str(Path(args.initial_code).resolve())
        write_json(directory/"native_config.json", config)
        prompt = upstream_regeneration_prompt()
        (directory/"upstream_regeneration_prompt.txt").write_text(prompt, encoding="utf-8")
        partial = {}
        checkpoint("native_trial_running")
        summary = _run_single_trial(execution, args.seed, native_args, config, prompt, partial)
        result.update(status="completed", upstream_summary=asdict(summary),
            success=summary.reward == 1. and bool(summary.task_completed), execution_ok=summary.sandbox_rc == 0,
            execution_turns=execution.execution_turns, budget_stopped=execution.budget_stopped,
            feedback=env.feedback())
        from src.aspire.native import last_executed_source
        (directory/"last_executed_block.py").write_text(last_executed_source(summary.code_path), encoding="utf-8")
    except BaseException as error:
        result.update(status="error", error_type=type(error).__name__, error=str(error),
            traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if backend is not None:
            try:
                write_json(directory/"reset_diagnostics.json", backend.reset_report)
                observation = backend.observation()
                observation["task_target"] = backend.config.target
                sink.observation("final", observation)
                if env is not None and env._ready:
                    result["feedback"] = env.feedback()
                    write_json(directory/"final_evaluation_diagnostics.json", asdict(backend.measure()))
            except Exception as error:
                result["artifact_error"] = str(error)
        result["elapsed_s"] = time.monotonic()-started
        write_json(directory/"result.json", result)
        sink.close()
        if backend is not None:
            backend.close()
        if app is not None:
            app.close()
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
