"""One disposable simulator process per trial."""
import argparse
import hashlib
import json
import time
import traceback
from pathlib import Path
from .artifacts import Artifacts, write_json
from .bootstrap import ROOT, setup_paths, upstream_revision
from .config import load_protocol


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--wall-timeout", type=float, default=600.)
    parser.add_argument("--scene-in")
    parser.add_argument("--scene-out")
    parser.add_argument("--observe-only", action="store_true")
    parser.add_argument("--record-screen", action="store_true")
    setup_paths()
    from isaaclab.app import AppLauncher
    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args(argv)
    directory = Path(args.out)
    sink = Artifacts(directory)
    started = time.monotonic()
    result = dict(seed=args.seed, success=False, execution_ok=False, status="starting",
                  aspire_commit=upstream_revision())
    write_json(directory / "result.json", result)
    app = backend = env = recording = None
    try:
        protocol, config = load_protocol(args.config)
        code = Path(args.code).read_text(encoding="utf-8")
        # Validate before paying the cost of launching Kit.
        from .execution import validate_program
        validate_program(code)
        (directory / "program.py").write_text(code, encoding="utf-8")
        result["program_sha256"] = hashlib.sha256(code.encode()).hexdigest()
        write_json(directory / "contract.json", protocol)
        args.enable_cameras = True
        # Set the recorder's renderer choices before Kit compiles startup shaders.
        args.kit_args += " --/rtx/post/aa/op=2 --/rtx-transient/dlssg/enabled=false"
        result["status"] = "launching_kit"
        write_json(directory / "result.json", result)
        print("ASPIRE: launching Isaac Sim 4.5 with cameras", flush=True)
        app = AppLauncher(args).app
        if args.record_screen:
            if args.headless:
                raise ValueError("App-window recording requires a GUI simulator")
            from .screen_recording import create_window_recording
            recording = create_window_recording(directory)
        from .runtime import IsaacBackend
        from .environment import SurgicalEnv
        from .execution import SurgicalExecutionEnv
        result["status"] = "building_scene"
        write_json(directory / "result.json", result)
        print("ASPIRE: building shared surgical scene", flush=True)
        backend = IsaacBackend(config, device=args.device)
        env = SurgicalEnv(backend, config, artifact_sink=sink)
        execution = SurgicalExecutionEnv(env)
        result["status"] = "resetting_scene"
        write_json(directory / "result.json", result)
        options = {}
        if args.scene_in:
            options["scene_snapshot"] = json.loads(Path(args.scene_in).read_text(encoding="utf-8"))
        obs, _ = execution.reset(seed=args.seed, options=options)
        if args.scene_out:
            from .scene_replay import capture_scene
            write_json(args.scene_out, capture_scene(backend, args.seed))
        if args.scene_in:
            result["scene_replay"] = backend.reset_report["scene_replay"]
        (directory / "prompt.txt").write_text(execution._get_complete_prompt(), encoding="utf-8")
        # Private diagnostics stay out of model feedback and policy observations.
        write_json(directory / "reset_diagnostics.json", backend.reset_report)
        env.set_deadline(max(.1, args.wall_timeout-(time.monotonic()-started)))
        if args.observe_only:
            context = dict(robot=obs["robot"], tray_slot=backend.tray_slot(),
                           table_height=backend.table_z_base, task_target=config.target)
            if config.sam3_target_prompt is not None:
                context["sam3_target_prompt"] = config.sam3_target_prompt
            write_json(directory / "sensor_context.json", context)
            result.update(status="observed", execution_ok=True, manipulation_trial=False)
        else:
            result["status"] = "executing_program"
            write_json(directory / "result.json", result)
            _, reward, terminated, truncated, info = execution.step(code)
            result.update(status="completed", success=reward == 1., execution_ok=info["sandbox_rc"] == 0,
                          terminated=terminated, truncated=truncated, feedback=env.feedback(),
                          stdout=info["stdout"], stderr=info["stderr"])
            if not result["execution_ok"]:
                result["status"] = "program_error"
    except BaseException as error:
        result.update(status="error", error_type=type(error).__name__, error=str(error),
                      traceback=traceback.format_exc())
        if env is not None and env._ready:
            result["feedback"] = env.feedback()
    finally:
        if backend is not None:
            try:
                write_json(directory / "reset_diagnostics.json", backend.reset_report)
                observation = backend.observation()
                observation["task_target"] = backend.config.target
                sink.observation("final", observation)
                if env is not None and env._ready:
                    from dataclasses import asdict
                    # Engineering evidence only; never sent to a skill/model.
                    write_json(directory / "final_evaluation_diagnostics.json", asdict(backend.measure()))
            except Exception as error:
                result["artifact_error"] = str(error)
        if recording is not None:
            try:
                result["screen_recording"] = recording.close()
            except Exception as error:
                result["screen_recording"] = dict(status="failed", error=str(error))
        result["elapsed_s"] = time.monotonic()-started
        # Commit result before teardown, which can itself hang in Kit.
        write_json(directory / "result.json", result)
        sink.close()
        print(json.dumps(result, indent=2), flush=True)
        try:
            if backend is not None:
                backend.close()
        finally:
            if app is not None:
                app.close()
    return 0 if result["execution_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
