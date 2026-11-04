"""Population search with separate development, selection, and final partitions."""
import hashlib
import json
import math
import json
import time
from pathlib import Path
from . import campaign
from .artifacts import write_json
from .config import load_protocol


STRATEGIES = (
    "Reconsider camera selection and cross-view target association.",
    "Reconsider depth filtering and partial/occluded visible geometry.",
    "Reconsider grasp location, long-axis estimation and wrist branch selection.",
    "Reconsider approach waypoints, reachability and rotation scheduling.",
    "Reconsider contact height, closure sequencing and sensor-based grasp checks.",
    "Reconsider lift motion and stability while holding the object.",
    "Reconsider transfer routing and object-to-hand offset estimation.",
    "Reconsider release height, placement alignment and settling.",
)
PUBLIC_FIELDS = ("seed", "success", "status", "feedback", "stdout", "stderr", "error")


def load_saved_baseline(directory, protocol, source, plan, model, base_url):
    """Reuse a complete baseline only; never silently rerun or discard requests."""
    directory = Path(directory).resolve()
    previous = json.loads((directory/"report.json").read_text(encoding="utf-8"))
    provider = json.loads((directory/"provider.json").read_text(encoding="utf-8"))
    saved_protocol, _ = load_protocol(directory/"contract.json")
    if saved_protocol != protocol or previous["plan"] != plan:
        raise ValueError("Saved baseline protocol/search budget differs")
    if provider["model"] != model or provider["base_url"] != base_url:
        raise ValueError("Saved baseline provider differs")
    if previous["status"] != "stopped_proposal_error" or previous["completed_revision_rounds"] != 0:
        raise ValueError("Resume requires a proposal failure immediately after the baseline")
    rows = previous["programs"]
    if len(rows) != 2 or rows[1]["status"] != "proposal_error" or rows[0]["status"] != "evaluated":
        raise ValueError("Resume requires an evaluated baseline and one failed proposal")
    if previous["provider_requests"] != 1:
        raise ValueError("Unexpected saved provider request count")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if rows[0]["program_sha256"] != digest or (directory/"initial/program.py").read_text(encoding="utf-8") != source:
        raise ValueError("Saved baseline program differs")
    trials = [directory/"initial"/f"dev_seed_{seed}" for seed in protocol["development_seeds"]]
    validation_trials = [directory/"initial/validation"/f"seed_{seed}" for seed in protocol["validation_seeds"]]
    for paths, seeds, results in ((trials, protocol["development_seeds"], rows[0]["results"]),
                                  (validation_trials, protocol["validation_seeds"], rows[0]["validation_report"]["results"])):
        if len(results) != len(seeds):
            raise ValueError("Saved baseline cohort is incomplete")
        for path, seed, result in zip(paths, seeds, results):
            on_disk = json.loads((path/"result.json").read_text(encoding="utf-8"))
            trial_protocol, _ = load_protocol(path/"contract.json")
            if on_disk != result or trial_protocol != protocol or result["seed"] != seed or result["program_sha256"] != digest:
                raise ValueError("Saved trial evidence differs from baseline")
            if result["status"] not in ("completed", "program_error") or not (path/"prompt.txt").is_file():
                raise ValueError("Saved trial did not initialize")
    if previous["attempted_trial_count"] != len(trials)+len(validation_trials):
        raise ValueError("Unexpected saved trial count")
    row = rows[0]
    row["trial_directories"] = [str(path) for path in trials]
    row["reused_from"] = str(directory)
    return previous, row, trials


def search_plan(config, *, candidates=8, iterations=3, development_only=True, wall_timeout=600.):
    if type(candidates) is not int or not 1 <= candidates <= 16:
        raise ValueError("K/candidates must be 1..16")
    if type(iterations) is not int or not 1 <= iterations <= 10:
        raise ValueError("T/iterations must be 1..10")
    if not 10 <= wall_timeout <= 3600:
        raise ValueError("wall_timeout must be 10..3600 seconds")
    protocol, task = load_protocol(config)
    if "validation_seeds" not in protocol:
        raise ValueError("Population search requires separate validation_seeds")
    programs = 1 + candidates*iterations
    dev = programs*len(protocol["development_seeds"])
    validation = programs*len(protocol["validation_seeds"])
    final = 0 if development_only else len(protocol["evaluation_seeds"])
    return dict(target=task.target, candidates_per_round=candidates, max_revision_rounds=iterations,
                initial_programs=1, max_proposed_programs=candidates*iterations,
                max_provider_requests=candidates*iterations, max_total_programs=programs,
                development_cases=len(protocol["development_seeds"]),
                validation_cases=len(protocol["validation_seeds"]),
                final_cases_reserved=len(protocol["evaluation_seeds"]),
                max_development_trials=dev, max_validation_trials=validation,
                max_final_trials=final, max_total_trials=dev+validation+final,
                worker_wall_timeout_s=wall_timeout,
                max_worker_wait_hours=(dev+validation+final)*wall_timeout/3600,
                development_only=development_only, monetary_cost="unknown",
                limitations=["Seed-generated scenes; exact physical scene replay is not implemented.",
                             "The translated starting skills use evaluator-assisted feedback."])


def search(launcher, code, config, out, *, candidates=8, iterations=3, model, base_url,
           api_key_env, wall_timeout=600., headless=True, development_only=True,
           reasoning_effort=None, max_output_tokens=128000, provider_timeout=1800., resume_baseline=None):
    if not math.isfinite(provider_timeout) or not 10 <= provider_timeout <= 1800:
        raise ValueError("provider_timeout must be 10..1800 seconds")
    plan = search_plan(config, candidates=candidates, iterations=iterations,
                       development_only=development_only, wall_timeout=wall_timeout)
    protocol, _ = load_protocol(config)
    source = Path(code).read_text(encoding="utf-8")
    from .execution import validate_program
    validate_program(source)
    saved = load_saved_baseline(resume_baseline, protocol, source, plan, model, base_url) if resume_baseline else None
    directory = Path(out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write_json(directory/"contract.json", protocol)
    write_json(directory/"search_plan.json", plan)
    write_json(directory/"provider.json", dict(model=model, base_url=base_url,
        credential_variable=api_key_env, max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort, timeout_s=provider_timeout))
    report = dict(status="baseline_running", plan=plan, provider_requests=0,
                  completed_revision_rounds=0, attempted_trial_count=0,
                  evaluation_run=False, programs=[], history=[])
    pool = []
    best = None

    def checkpoint():
        report["elapsed_s"] = time.monotonic()-started
        write_json(directory/"report.json", report)

    def freeze():
        if best is not None:
            (directory/"frozen_program.py").write_text(best["source"], encoding="utf-8")
            report.update(selected_program_id=best["id"], program_sha256=best["digest"],
                          split="validation", success_count=best["validation_score"],
                          trial_count=len(protocol["validation_seeds"]))

    def score_program(entry):
        nonlocal best
        path = directory/entry["id"]
        path.mkdir()
        source_path = path/"program.py"
        source_path.write_text(entry["source"], encoding="utf-8")
        entry["trials"] = []
        entry["development_results"] = []
        row = dict(id=entry["id"], round=entry["round"], program_sha256=entry["digest"],
                   status="development_running", results=[], trial_directories=[])
        report["programs"].append(row)
        for seed in protocol["development_seeds"]:
            trial = path/f"dev_seed_{seed}"
            print(f"{entry['id']} development seed {seed}", flush=True)
            result = campaign.run_trial(launcher, source_path, config, seed, trial,
                                       wall_timeout=wall_timeout, headless=headless)
            report["attempted_trial_count"] += 1
            entry["trials"].append(trial)
            entry["development_results"].append(result)
            row["results"].append(result)
            row["trial_directories"].append(str(trial))
            checkpoint()
        entry["development_score"] = sum(r["success"] for r in entry["development_results"])
        row["development_success_count"] = entry["development_score"]
        # Complete the cohort, preserve all failures, then stop before proposing
        # repairs for an environment that did not initialize consistently.
        if any(not (trial/"prompt.txt").exists() or result["status"] not in ("completed", "program_error")
               for trial, result in zip(entry["trials"], entry["development_results"])):
            row["status"] = "infrastructure_failure"
            report.update(status="stopped_infrastructure", reason=
                "Repair reset/startup/runtime infrastructure before further candidate generation.")
            checkpoint()
            return False
        validation = campaign.evaluate(launcher, source_path, config, path/"validation",
            wall_timeout=wall_timeout, headless=headless, split="validation")
        report["attempted_trial_count"] += validation["trial_count"]
        row["validation_report"] = validation
        if any(r["status"] not in ("completed", "program_error") for r in validation["results"]):
            row["status"] = "infrastructure_failure"
            report.update(status="stopped_infrastructure", reason="Validation infrastructure failed.")
            checkpoint()
            return False
        entry["validation_score"] = validation["success_count"]
        row.update(status="evaluated", validation_success_count=entry["validation_score"])
        # Keep earliest program on ties; validation never affects LLM context.
        if best is None or entry["validation_score"] > best["validation_score"]:
            best = entry
        pool.append(entry)
        freeze()
        checkpoint()
        return True

    def program(identifier, source, round_index):
        return dict(id=identifier, source=source, round=round_index,
                    digest=hashlib.sha256(source.encode()).hexdigest())

    def solved():
        return best is not None and best["validation_score"] == len(protocol["validation_seeds"]) and \
            best["development_score"] == len(protocol["development_seeds"])

    try:
        checkpoint()
        if saved:
            previous, row, trials = saved
            write_json(directory/"resume_snapshot.json", previous)
            report.update(provider_requests=previous["provider_requests"],
                attempted_trial_count=previous["attempted_trial_count"],
                resume_baseline=str(Path(resume_baseline).resolve()),
                prior_elapsed_s=previous["elapsed_s"])
            report["programs"].append(row)
            entry = program("initial", source, 0)
            entry.update(trials=trials, development_results=row["results"],
                development_score=row["development_success_count"], validation_score=row["validation_success_count"])
            pool.append(entry)
            best = entry
            freeze()
            print("Reusing saved baseline; no simulator trials repeated.", flush=True)
            checkpoint()
        elif not score_program(program("initial", source, 0)):
            return report
        for round_index in range(1, iterations+1):
            if solved():
                break
            # A failed request still counts. Do not spend on an incomplete K population.
            if report["provider_requests"]+candidates > plan["max_provider_requests"]:
                report["request_budget_exhausted"] = True
                break
            # Survivors depend only on development, including their full sources
            # and public outcomes. No validation scores/results enter generation.
            survivors = sorted(pool, key=lambda p: -p["development_score"])[:3]
            context_pool = [dict(id=p["id"], program=p["source"],
                development_success_count=p["development_score"],
                development_feedback=[{key:r[key] for key in PUBLIC_FIELDS if key in r}
                                      for r in p["development_results"]]) for p in survivors]
            generation = directory/f"generation_{round_index:02d}"
            generation.mkdir()
            population = []
            report["status"] = "generating_population"
            # Generate the entire K population before executing any new program.
            for candidate_index in range(candidates):
                parent = survivors[candidate_index % len(survivors)]
                identifier = f"round_{round_index:02d}_candidate_{candidate_index+1:02d}"
                context = dict(round=round_index, candidate=candidate_index+1,
                    population_size=candidates, parent_id=parent["id"], top_development_programs=context_pool,
                    strategy=STRATEGIES[candidate_index % len(STRATEGIES)],
                    instruction="Propose a structurally distinct executable repair hypothesis. "
                        "Do not only make small parameter changes. Preserve the public API and task contract.",
                    already_proposed_programs=[p["source"] for p in population])
                write_json(generation/f"{identifier}_context.json", context)
                report["provider_requests"] += 1
                report["active_proposal"] = identifier
                checkpoint()
                try:
                    revised = campaign.refine_program(model, base_url, api_key_env, parent["source"],
                        parent["trials"], usage_path=generation/f"{identifier}_usage.json",
                        reasoning_effort=reasoning_effort, max_output_tokens=max_output_tokens,
                        repair_context=context, timeout=provider_timeout)
                    validate_program(revised)
                except Exception as error:
                    report["programs"].append(dict(id=identifier, round=round_index,
                        status="proposal_error", error_type=type(error).__name__, error=str(error)))
                    report["status"] = "stopped_proposal_error"
                    checkpoint()
                    return report
                entry = program(identifier, revised, round_index)
                (generation/f"{identifier}.py").write_text(revised, encoding="utf-8")
                if entry["digest"] in {p["digest"] for p in pool+population}:
                    report["programs"].append(dict(id=identifier, round=round_index,
                        status="duplicate_proposal", program_sha256=entry["digest"]))
                    report["status"] = "stopped_duplicate_proposal"
                    checkpoint()
                    return report
                population.append(entry)
            report.pop("active_proposal", None)
            report["status"] = "evaluating_population"
            for entry in population:
                if not score_program(entry):
                    return report
            report["completed_revision_rounds"] = round_index
            report["history"].append(dict(round=round_index,
                candidates=[p["id"] for p in population], selected_program_id=best["id"]))
            checkpoint()
        report["status"] = "search_completed"
        report["stop_reason"] = "all_development_and_validation_cases_solved" if solved() else (
            "insufficient_request_budget_for_full_population" if report.get("request_budget_exhausted") else "revision_budget_exhausted")
        freeze()
        checkpoint()
        if not development_only:
            # Freeze once; final outcomes can never trigger another proposal.
            evaluation = campaign.evaluate(launcher, directory/"frozen_program.py", config,
                directory/"evaluation", wall_timeout=wall_timeout, headless=headless)
            report.update(evaluation_run=True, evaluation_report=evaluation)
            report["attempted_trial_count"] += evaluation["trial_count"]
        return report
    except Exception as error:
        report.update(status="error", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        checkpoint()
