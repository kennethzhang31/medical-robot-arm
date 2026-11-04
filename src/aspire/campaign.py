"""Bounded trial orchestration and development-only program refinement."""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from .artifacts import write_json
from .bootstrap import ROOT
from .config import load_protocol


def worker_environment(environment=None):
    source = os.environ if environment is None else environment
    # Provider credentials belong to the orchestrator, never generated programs.
    result = {k:v for k,v in source.items() if not any(word in k.upper() for word in
              ("API_KEY", "ACCESS_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL"))}
    result["PYTHONUNBUFFERED"] = "1"
    return result


def launcher_command(launcher, arguments):
    values = [str(launcher), *map(str, arguments)]
    if os.name == "nt" and Path(launcher).suffix.lower() in (".bat", ".cmd"):
        if any(any(c in value for c in '\r\n"&|<>^%!') for value in values):
            raise ValueError("Windows launcher arguments contain shell metacharacters")
        # Pass a raw command line: list2cmdline backslash-escapes the nested CMD
        # quotes, which CMD does not interpret like the C runtime does.
        shell = os.environ.get("COMSPEC", "cmd.exe")
        return '"'+shell+'" /d /s /c "'+' '.join('"'+value+'"' for value in values)+'"'
    return values


def run_trial(launcher, code, config, seed, out, *, wall_timeout=600., headless=True,
              scene_in=None, scene_out=None, observe_only=False, record_screen=False):
    if not 10 <= wall_timeout <= 3600:
        raise ValueError("wall_timeout must be 10..3600 seconds")
    directory = Path(out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    args = [ROOT / "scripts/aspire_worker.py", "--code", Path(code).resolve(), "--config",
            Path(config).resolve(), "--seed", str(seed), "--out", directory,
            "--wall-timeout", str(wall_timeout), "--device", "cuda:0"]
    if headless:
        args.append("--headless")
    if record_screen:
        if headless:
            raise ValueError("App-window recording requires headless=False")
        args.append("--record-screen")
    if scene_in is not None:
        args.extend(["--scene-in", Path(scene_in).resolve()])
    if scene_out is not None:
        args.extend(["--scene-out", Path(scene_out).resolve()])
    if observe_only:
        args.append("--observe-only")
    command = launcher_command(launcher, args)
    result = dict(seed=seed, success=False, execution_ok=False, status="worker_starting")
    write_json(directory / "result.json", result)
    started = time.monotonic()
    with (directory / "worker.log").open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                env=worker_environment(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                rc = process.wait(timeout=wall_timeout)
            except subprocess.TimeoutExpired:
                # Only terminate the process tree created by this trial.
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=20,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.kill()
                process.wait(timeout=20)
                result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
                result["interrupted_status"] = result["status"]
                result.update(status="worker_wall_timeout", elapsed_s=time.monotonic()-started)
                write_json(directory / "result.json", result)
                return result
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            if result["status"] in ("starting", "worker_starting", "launching_kit", "building_scene", "resetting_scene"):
                result.update(status="worker_crashed", error=f"Worker exited with code {rc}")
            result["worker_returncode"] = rc
        except Exception as error:
            result.update(status="worker_error", error=str(error))
    result["elapsed_s"] = time.monotonic()-started
    write_json(directory / "result.json", result)
    return result


def evaluate(launcher, code, config, out, *, wall_timeout=600., headless=True, split="eval"):
    protocol, _ = load_protocol(config)
    directory = Path(out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    source = Path(code).read_text(encoding="utf-8")
    frozen = directory / "frozen_program.py"
    frozen.write_text(source, encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    write_json(directory / "contract.json", protocol)
    results = []
    partition = {"dev":"development_seeds", "validation":"validation_seeds", "eval":"evaluation_seeds"}[split]
    for seed in protocol[partition]:
        print(f"{split} seed {seed}: starting", flush=True)
        result = run_trial(launcher, frozen, config, seed, directory/f"seed_{seed}",
                           wall_timeout=wall_timeout, headless=headless)
        results.append(result)
        report = dict(split=split, program_sha256=digest, success_count=sum(r["success"] for r in results),
                      trial_count=len(results), results=results)
        write_json(directory / "report.json", report)
        print(f"{split} seed {seed}: {result['status']}, success={result['success']}", flush=True)
    return report


def refine_program(model, base_url, api_key_env, current, trials, *, timeout=1800., usage_path=None,
                   reasoning_effort=None, max_output_tokens=128000, repair_context=None):
    """Provider-neutral Chat Completions request. Explicit --model opts into this."""
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing orchestrator credential: {api_key_env}")
    feedback = []
    for directory in trials:
        result = json.loads((directory/"result.json").read_text(encoding="utf-8"))
        # Deliberately exclude reset diagnostics / privileged evaluator geometry.
        feedback.append({k:result[k] for k in ("seed", "success", "status", "feedback", "stdout", "stderr", "error") if k in result})
    prompt = next((p/"prompt.txt" for p in trials if (p/"prompt.txt").exists()), None)
    if prompt is None:
        raise RuntimeError("No initialized trial produced API documentation; fix runtime before refinement")
    text = (prompt.read_text(encoding="utf-8") + "\nRefine this sensor-based program using DEVELOPMENT trial feedback. "
            "Return only executable Python. Allowed imports: numpy and math. Use camera sensors and public API. "
            "No filesystem, networking, simulator access, object ground truth, seed-specific coordinates or expert actions.\n"
            + "Current program:\n"+current+"\nFeedback:\n"+json.dumps(feedback))
    if repair_context is not None:
        text += "\nPopulation search context (development evidence only):\n" + json.dumps(repair_context)
    content = [dict(type="text", text=text)]
    # Two distinct failure signatures plus one successful control, when available.
    # Never use validation images/outcomes as revision feedback.
    selected, signatures = [], set()
    for successful in (False, True):
        for directory, outcome in zip(trials, feedback):
            if bool(outcome.get("success")) != successful or not (directory/"initial").exists():
                continue
            signature = (outcome.get("status"), outcome.get("feedback", {}).get("reason"),
                         outcome.get("stderr", "").splitlines()[-1:] or outcome.get("error"))
            signature = str(signature)
            if signature in signatures:
                continue
            signatures.add(signature)
            selected.append((directory, outcome))
            if successful or len(selected) >= 2:
                break
    evidence = []
    for directory, outcome in selected:
        pictures = [directory/"initial/top.png", directory/"final/top.png", directory/"final/wrist.png"]
        # The final sampled motion frame shows the failed stage, rather than
        # only reset and terminal states. Stage stdout supplies its context.
        frames = sorted((directory/"frames").glob("*_wrist.jpg"))
        if frames:
            pictures.append(frames[-1])
        for picture in pictures:
            if not picture.exists():
                continue
            label = f"Development seed {outcome['seed']}, success={outcome.get('success')}: {picture.relative_to(directory)}"
            mime = "image/jpeg" if picture.suffix == ".jpg" else "image/png"
            content.extend([dict(type="text", text=label), dict(type="image_url", image_url=dict(
                url=f"data:{mime};base64,"+base64.b64encode(picture.read_bytes()).decode()))])
            evidence.append(dict(seed=outcome["seed"], image=str(picture)))
    if usage_path is not None:
        write_json(Path(usage_path).with_name(Path(usage_path).stem+"_evidence.json"), evidence)
    if not 1024 <= max_output_tokens <= 128000:
        raise ValueError("max_output_tokens must be 1024..128000")
    payload = dict(model=model, max_tokens=max_output_tokens, messages=[dict(role="user", content=content)])
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    request = urllib.request.Request(base_url.rstrip("/")+"/chat/completions",
        data=json.dumps(payload).encode(), headers={"Authorization":"Bearer "+api_key,
                                                   "Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        completion = json.load(response)
    choice = completion["choices"][0]
    if usage_path is not None:
        write_json(usage_path, dict(requested_model=model, response_model=completion.get("model"),
                                   usage=completion.get("usage"), finish_reason=choice.get("finish_reason")))
    if choice.get("finish_reason") == "length":
        raise RuntimeError("Model response was truncated; candidate will not be executed")
    value = (choice["message"].get("content") or "").strip()
    if not value:
        raise RuntimeError("Model returned no executable program")
    if value.startswith("```"):
        value = value.split("\n",1)[1].rsplit("```",1)[0].strip()
    from .execution import validate_program
    validate_program(value)
    return value+"\n"


def refine(launcher, code, config, out, *, rounds, model, base_url, api_key_env,
           wall_timeout=600., headless=True, development_only=False, reasoning_effort=None,
           max_output_tokens=128000, initial_trials=None):
    if not 1 <= rounds <= 10:
        raise ValueError("Refinement rounds must be 1..10")
    if rounds > 1 and not os.environ.get(api_key_env):
        raise RuntimeError(f"Missing orchestrator credential: {api_key_env}")
    protocol, _ = load_protocol(config)
    directory = Path(out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/"provider.json", dict(model=model, base_url=base_url,
        credential_variable=api_key_env, rounds=rounds, development_only=development_only,
        max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort))
    current = Path(code).read_text(encoding="utf-8")
    best, best_score = current, -1
    history = []
    for round_index in range(rounds):
        candidate = directory/f"candidate_{round_index}.py"
        candidate.write_text(current, encoding="utf-8")
        trials = []; results = []
        for seed in protocol["development_seeds"]:
            trial = directory/f"round_{round_index}_seed_{seed}"
            print(f"development round {round_index} seed {seed}", flush=True)
            reused = (initial_trials or {}).get(seed) if round_index == 0 else None
            if reused is not None:
                reused = Path(reused).resolve()
                result = json.loads((reused/"result.json").read_text(encoding="utf-8"))
                if result.get("seed") != seed or result.get("program_sha256") != hashlib.sha256(current.encode()).hexdigest():
                    raise ValueError("Initial trial seed/program differs from campaign")
                previous, _ = load_protocol(reused/"contract.json")
                if previous["task"] != protocol["task"] or result["status"] not in ("completed", "program_error", "error"):
                    raise ValueError("Initial trial task/status differs from campaign")
                trial = reused
            else:
                result = run_trial(launcher, candidate, config, seed, trial,
                                   wall_timeout=wall_timeout, headless=headless)
            results.append(result)
            trials.append(trial)
        score = sum(r["success"] for r in results)
        # A separate partition selects candidates; only development reaches the LLM.
        if "validation_seeds" in protocol:
            validation = evaluate(launcher, candidate, config, directory/f"validation_{round_index}",
                                  wall_timeout=wall_timeout, headless=headless, split="validation")
            selection_score = validation["success_count"]
            selection_count = validation["trial_count"]
        else:
            selection_score, selection_count = score, len(results)
        if selection_score > best_score:
            best, best_score = current, selection_score
        (directory/"frozen_program.py").write_text(best, encoding="utf-8")
        history.append(dict(round=round_index, success_count=score, trials=len(results),
                            selection_split="validation" if "validation_seeds" in protocol else "dev",
                            selection_success_count=selection_score, selection_trial_count=selection_count,
                            trial_directories=[str(p) for p in trials]))
        write_json(directory/"development.json", history)
        if score == len(results) and selection_score == selection_count:
            break
        if round_index+1 < rounds:
            try:
                current = refine_program(model, base_url, api_key_env, current, trials,
                                         usage_path=directory/f"provider_usage_{round_index}.json",
                                         reasoning_effort=reasoning_effort, max_output_tokens=max_output_tokens)
            except Exception as error:
                write_json(directory/"refinement_error.json", dict(round=round_index, error=str(error)))
                raise
    frozen = directory/"frozen_program.py"
    frozen.write_text(best, encoding="utf-8")
    if development_only:
        selection_partition = "validation_seeds" if "validation_seeds" in protocol else "development_seeds"
        report = dict(split="validation" if "validation_seeds" in protocol else "dev", success_count=best_score,
                      trial_count=len(protocol[selection_partition]),
                      program_sha256=hashlib.sha256(best.encode()).hexdigest(),
                      evaluation_run=False, history=history)
        write_json(directory/"report.json", report)
        return report
    # Held-out seeds are first touched after all development and program selection.
    return evaluate(launcher, frozen, config, directory/"evaluation", wall_timeout=wall_timeout,
                    headless=headless)
