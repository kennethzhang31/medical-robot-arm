"""Frozen H/A/B skill-reuse pilot, without a target-object repair loop."""
import ast
import base64
import hashlib
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from .artifacts import write_json
from .bootstrap import ROOT
from .campaign import run_trial
from .config import TaskConfig, load_protocol
from .full import validate_sensor_program

SOURCE_CAMPAIGN = ROOT / "logs/aspire_codex61_scissor_sam3_igvi_20261005_run04"
SKILL_IDS = (
    "f635f6e8c3863eeab1d856077d00551afa93e5aebd7aa6e00365025224f3744e",
    "3b987927f3e66aba0508abf955261db5dd7fd4e1716efd5ca2486cae0841e7c6",
    "e3e632cf74058b5173e5d4419540f06285006e6b4c64ef61847c26658243a0d5",
)
SUBMIT = dict(type="function", function=dict(name="submit_program",
    description="Submit one complete standalone sensor-only Kelly program. No practice or revisions.",
    parameters=dict(type="object", properties=dict(code=dict(type="string"), hypothesis=dict(type="string")),
                    required=["code", "hypothesis"], additionalProperties=False)))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def program_sha(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


def source_accounting(root=SOURCE_CAMPAIGN):
    root = Path(root).resolve()
    state = read_json(root / "state.json")
    if state["status"] != "completed":
        raise ValueError("Source campaign must be completed before transfer")
    launch = read_json(root / "launch.json")
    reports = [read_json(path / "report.json") for path in sorted(root.glob("provider_*")) if path.is_dir()]
    attempted = launch["prior_requests"] + sum(row["requests"] for row in reports)
    return dict(source_campaign=str(root), source_state_sha256=file_sha(root / "state.json"),
                prior_requests=attempted, max_total_requests=150)


def verify_accounting(accounting):
    current = source_accounting(accounting.get("source_campaign", SOURCE_CAMPAIGN))
    if (current["prior_requests"] != accounting["prior_requests"] or
            current.get("source_state_sha256") != accounting.get("source_state_sha256")):
        raise ValueError("Source accounting changed; do not silently reset the cumulative budget")


def boundary_only_baseline(source):
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("require_lift", "require_place")]
    if {node.name for node in functions} != {"require_lift", "require_place"}:
        raise ValueError("Expected the two translated evaluator gates")
    lines = source.splitlines(keepends=True)
    for node in sorted(functions, key=lambda item: item.lineno, reverse=True):
        lines[node.lineno:node.end_lineno] = [
            '    print("Private physical verification is deferred to the independent scorer")\n']
    result = "".join(lines)
    validate_sensor_program(result)
    return result


def recover_unsupported_transport(directory):
    root = Path(directory)
    control = root / "control/transport_recovery.json"
    if control.exists():
        record = read_json(control)
        state = read_json(root / "state.json")
        if (file_sha(control) != state.get("transport_recovery_sha256") or
                record["extra_attempt_allowance"] != 1 or
                record["original_plan_sha256"] != file_sha(root / "plan.json")):
            raise ValueError("Transport recovery record changed")
        return record
    state = read_json(root / "state.json")
    if any(key != "observe" and not key.startswith("observe_replay") for key in state["trials"]):
        raise ValueError("Transport recovery must precede manipulation")
    if (root / "model/A.response.json").exists() or (root / "model/B.request.json").exists():
        raise ValueError("Transport recovery cannot regenerate or select a model completion")
    ledgers = [path for path in sorted(root.glob("provider_*")) if path.is_dir()]
    reports = [read_json(path / "report.json") for path in ledgers]
    if sum(row["requests"] for row in reports) != 1 or any(row["pending"] for row in reports):
        raise ValueError("Recovery is limited to exactly one finalized compatibility rejection")
    errors = list(root.glob("provider_*/request_*.error.json"))
    if len(errors) != 1 or list(root.glob("provider_*/request_*.response.json")):
        raise ValueError("Unexpected provider evidence; no compatibility retry")
    error = read_json(errors[0])
    detail = error.get("provider_detail", "")
    if error.get("http_status") != 400 or "UnsupportedParamsError" not in detail or "tool_choice" not in detail:
        raise ValueError("Only the verified unsupported chat tool_choice rejection can be recovered")
    plan = read_json(root / "plan.json")
    if plan["accounting"]["prior_requests"] + 3 > plan["accounting"]["max_total_requests"]:
        raise ValueError("Transport recovery exceeds cumulative authorization")
    record = dict(reason="HTTP 400 unsupported tool_choice before model completion; use source campaign native /messages transport",
                  extra_attempt_allowance=1, max_new_attempts_including_rejection=3,
                  max_generated_programs=2, request_sha256=file_sha(root / "model/A.request.json"),
                  error_path=str(errors[0].relative_to(root)), error_sha256=file_sha(errors[0]),
                  original_plan_sha256=file_sha(root / "plan.json"), cumulative_cap=plan["accounting"]["max_total_requests"])
    write_json(control, record)
    state["transport_recovery_sha256"] = file_sha(control)
    write_json(root / "state.json", state)
    return record


def recover_native_tool_finish(directory):
    from .relay import collect_messages_stream
    root = Path(directory).resolve()
    campaign = FrozenComparison(root)
    control = root / "control/native_tool_finish_B.json"
    if control.exists():
        record = read_json(control)
        if file_sha(control) != campaign.state.get("native_tool_finish_recovery_sha256"):
            raise ValueError("Native finish recovery record changed")
        campaign.verify(record["hashes"])
        return record
    state = campaign.state
    if (state.get("status") != "stopped" or state.get("phase") != "generation"
            or state.get("error") != "Incomplete/non-tool response preserved, not executed"
            or (root / "frozen_programs.json").exists()
            or any(key != "observe" and not key.startswith("observe_replay") for key in state["trials"])):
        raise ValueError("Native finish recovery requires a stopped pre-evaluation completion-guard failure")
    reports = [read_json(path / "report.json") for path in root.glob("provider_*") if path.is_dir()]
    if sum(row["requests"] for row in reports) != 2 or any(row["pending"] for row in reports):
        raise ValueError("Native finish recovery requires exactly two finalized original attempts")
    original_path = root / "model/B.response.json"
    original = read_json(original_path)
    if (len(original.get("choices", [])) != 1 or original["choices"][0].get("finish_reason") != "stop"
            or read_json(root / "model/A.response.json")["choices"][0].get("finish_reason") != "tool_calls"):
        raise ValueError("Only the original B stop-label mismatch may be recovered")
    matches = [path for path in root.glob("provider_*/request_*.response.json")
               if file_sha(path) == file_sha(original_path)]
    if len(matches) != 1:
        raise ValueError("Native finish recovery requires one exact preserved provider response")
    stream = matches[0].with_name(matches[0].name.replace(".response.json", ".stream.sse"))
    events = [json.loads(line[5:].strip()) for line in stream.read_bytes().splitlines() if line.startswith(b"data:")]
    reasons = [event.get("delta", {}).get("stop_reason") for event in events if event.get("type") == "message_delta"]
    if not reasons or reasons[-1] != "end_turn":
        raise ValueError("Only a terminal native end_turn tool submission may be recovered")
    reparsed = root / "control/native_tool_finish_B.reparsed.sse"
    reparsed.parent.mkdir(parents=True, exist_ok=True)
    with stream.open("rb") as response:
        normalized = collect_messages_stream(response, reparsed)
    expected = json.loads(json.dumps(original))
    expected["choices"][0]["finish_reason"] = "tool_calls"
    if normalized != expected or file_sha(reparsed) != file_sha(stream):
        raise ValueError("Native normalization changed more than the finish label")
    calls = normalized["choices"][0]["message"].get("tool_calls", [])
    if len(calls) != 1 or calls[0]["function"]["name"] != "submit_program":
        raise ValueError("Recovery requires exactly one original standalone submission")
    value = json.loads(calls[0]["function"]["arguments"])
    if set(value) != {"code", "hypothesis"} or not all(isinstance(item, str) and item.strip() for item in value.values()):
        raise ValueError("Malformed original submission cannot be recovered")
    validate_sensor_program(value["code"])
    normalized_path = root / "model/B.normalized_response.json"
    write_json(normalized_path, normalized)
    protected = [original_path, normalized_path, matches[0], stream, reparsed]
    record = dict(reason="Complete closed native tool block and terminal message_stop with end_turn; only transport finish label normalized",
        condition="B", native_stop_reason="end_turn", new_model_attempts=0, program_changes=0,
        normalized_response=normalized_path.relative_to(root).as_posix(),
        hashes={path.relative_to(root).as_posix(): file_sha(path) for path in protected})
    write_json(control, record)
    campaign.save(native_tool_finish_recovery_sha256=file_sha(control))
    return record


def record_physical_success_policy(directory):
    campaign = FrozenComparison(directory)
    existing = campaign.success_policy()
    if existing is not None:
        return existing
    root = campaign.root
    if not (root / "frozen_programs.json").exists():
        raise ValueError("Reporting amendment requires already frozen H/A/B programs")
    campaign.verify(read_json(root / "frozen_programs.json"))
    control = root / "control"
    control.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for name in ("state.json", "report.json"):
        destination = control / ("physical_policy_previous_" + name)
        destination.write_bytes((root / name).read_bytes())
        snapshots[destination.relative_to(root).as_posix()] = file_sha(destination)
    previous = read_json(control / "physical_policy_previous_state.json")
    observed = sum(previous["trials"].get(f"{condition}_s{seed}", {}).get("status") in ("completed", "program_error")
                   for seed in campaign.plan["cases"] for condition in ("H", "A", "B"))
    record = dict(version=1, recorded_at=datetime.now().astimezone().isoformat(),
        user_request="Consider physically complete pick/place as success", reporting_only=True,
        primary_metric="physical_success", physical_success="lift_verified and place_verified",
        strict_success="result.success and execution_ok", conditions=["H", "A", "B"],
        applies_to="All completed and future paired rollouts in this run", post_hoc=observed > 0,
        completed_rollouts_at_recording=observed, snapshot_hashes=snapshots,
        setup_manifest_sha256=file_sha(root / "setup_hashes.json"),
        programs_manifest_sha256=file_sha(root / "frozen_programs.json"))
    write_json(control / "physical_success_policy.json", record)
    return campaign.success_policy()


def prepare_comparison(directory, *, cases=5, model="chatgpt1/gpt-6.1-sol",
                       base_url="https://llm.igvi.cs.nthu.edu.tw/v1", source_root=SOURCE_CAMPAIGN,
                       shared_root=None, target="kelly", sam3_target_prompt=None, session_parent=None,
                       record_screen=False, match_source_physics=False):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT / "logs"):
        raise ValueError("Experiment output must be under repository logs")
    if type(cases) is not int or not 1 <= cases <= 6:
        raise ValueError("Use 1..6 paired cases: at most 18 rollouts plus two motionless sessions")
    if target not in ("kelly", "scalpel", "scissor"):
        raise ValueError("Supported comparison targets are kelly, scalpel and scissor")
    if base_url != "https://llm.igvi.cs.nthu.edu.tw/v1":
        raise ValueError("This pilot uses the user-authorized IGVI origin")
    prior_sessions = 0
    session_accounting = None
    if session_parent is not None:
        parent = Path(session_parent).resolve()
        if not parent.is_relative_to(ROOT / "logs") or parent == directory:
            raise ValueError("Session parent must be another preserved run under repository logs")
        previous = read_json(parent / "state.json")
        previous_contract = read_json(parent / "contract.json")
        failed_reset = (previous.get("phase") == "initial_observation"
                        and set(previous["trials"]) == {"observe"}
                        and previous["trials"]["observe"].get("status") == "error"
                        and previous["trials"]["observe"].get("error", "").startswith("reset_settle_failed:"))
        if (previous["status"] != "stopped" or not (previous.get("phase") == "perception_blocked" or failed_reset)
                or previous_contract["task"]["target"] != target
                or any(key != "observe" and not key.startswith("observe_replay") for key in previous["trials"])
                or list((parent / "model").glob("*")) or list(parent.glob("provider_*"))
                or (parent / "frozen_programs.json").exists()):
            raise ValueError("Only a stopped, motionless same-target preflight may supply session carry-in")
        previous_plan = read_json(parent / "plan.json") if (parent / "plan.json").exists() else {}
        inherited = previous_plan.get("session_accounting", {}).get("prior_sessions", 0)
        started = previous["sessions_started"]
        if any(type(value) is not int or value < 0 for value in (started, inherited)):
            raise ValueError("Invalid parent session count")
        prior_sessions = started + inherited
        session_accounting = dict(parent=str(parent), state_sha256=file_sha(parent / "state.json"),
                                  contract_sha256=file_sha(parent / "contract.json"), prior_sessions=prior_sessions)
        if (parent / "plan.json").exists():
            session_accounting["plan_sha256"] = file_sha(parent / "plan.json")
    if prior_sessions + 2 + 3*cases > 20:
        raise ValueError("Session carry-in plus preflight and rollouts exceeds the 20-session cap")
    accounting = source_accounting(source_root)
    if accounting["prior_requests"] + 2 > accounting["max_total_requests"]:
        raise ValueError("Insufficient cumulative model budget")
    shared_root = Path(shared_root or ROOT / "logs/aspire_shared_skills/sam3")
    skills = [read_json(shared_root / f"{identifier}.json") for identifier in SKILL_IDS]
    for identifier, row in zip(SKILL_IDS, skills):
        expected = hashlib.sha256(json.dumps(dict(pattern=row["pattern"], provenance=row["provenance"]),
                                             sort_keys=True).encode()).hexdigest()
        if row["id"] != identifier or identifier != expected or not row["coordinator_review"]["admit"]:
            raise ValueError("Shared skill identity/approval differs")
        if row["status"] != "debug_validated_repair" or row["provenance"]["task"] != "scissor":
            raise ValueError("Expected the admitted scissors library")
        validate_sensor_program(row["pattern"]["code_sketch"])
    protocol, _ = load_protocol(ROOT / f"configs/aspire/translated/{target}-sam3.json")
    physics_reference = None
    if match_source_physics:
        if target != "scissor":
            raise ValueError("Source physics matching is limited to the same-object scissors comparison")
        reference = SOURCE_CAMPAIGN / "contract.json"
        source_protocol, _ = load_protocol(reference)
        if source_protocol["task"]["target"] != target:
            raise ValueError("Source physics target differs")
        settings = {name: source_protocol["task"][name] for name in
                    ("solver_position_iterations", "solver_velocity_iterations")}
        if any(value is None for value in settings.values()):
            raise ValueError("Source solver settings must be explicit")
        protocol["task"].update(settings)
        physics_reference = dict(source_contract=str(reference), contract_sha256=file_sha(reference),
            settings=settings, reason="Restore the completed source campaign's solver settings before generation; no outcome-driven tuning")
    observation_seed, evaluation_start = {"kelly": (501, 601), "scalpel": (551, 701),
                                         "scissor": (801, 901)}[target]
    if sam3_target_prompt is not None:
        if target != "scalpel" or sam3_target_prompt != "knife":
            raise ValueError("The declared calibrated mapping is scalpel -> knife only")
        protocol["task"]["sam3_target_prompt"] = sam3_target_prompt
        observation_seed = 552
    label = {"kelly": "Kelly", "scalpel": "scalpel", "scissor": "scissors"}[target]
    protocol["task"]["allow_evaluator_feedback"] = False
    protocol["evaluation_seeds"] = list(range(evaluation_start, evaluation_start+cases))
    protocol["development_seeds"] = [observation_seed]
    TaskConfig(**protocol["task"])
    baseline = ROOT / f"examples/aspire/translated/{target}.py"
    sanitized = boundary_only_baseline(baseline.read_text(encoding="utf-8"))
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "contract.json", protocol)
    write_json(directory / "launch.json", dict(prior_requests=accounting["prior_requests"],
               model=model, base_url=base_url, max_total_requests=accounting["max_total_requests"]))
    for condition, library in (("H", []), ("A", []), ("B", skills)):
        program_directory = directory / "programs" / condition
        program_directory.mkdir(parents=True)
        write_json(program_directory / "library.json", library)
    (directory / "programs/H/frozen_program.py").write_text(sanitized, encoding="utf-8")
    write_json(directory / "baseline_provenance.json", dict(
        original=str(baseline.relative_to(ROOT)), original_sha256=file_sha(baseline),
        translated_manifest_sha256=file_sha(ROOT / "examples/aspire/translated/manifest.json"),
        copy_sha256=file_sha(directory / "programs/H/frozen_program.py"),
        changes=["Only require_lift and require_place evaluator assertions are deferred to private scoring.",
                 "No ASPIRE motion/localization changes. Expert PROFILE and all motor stages remain unchanged."],
        limitation="Removing oracle gates can change failure termination; H is a boundary-sanitized translation, not the original controller."))
    plan = dict(protocol=f"{label} frozen H/A/B engineering pilot v1", model=model, base_url=base_url,
        target=target, experiment_type=("same_object_frozen_skill_ablation" if target == "scissor" else
            "zero_shot_manipulation_transfer_with_calibrated_perception" if sam3_target_prompt else "zero_shot_cross_object_transfer"),
        source_library_campaign=str(SOURCE_CAMPAIGN),
        cases=protocol["evaluation_seeds"], observation_seed=observation_seed, headless=False,
        max_manipulation_rollouts=3*cases, max_simulator_sessions=20,
        max_new_model_requests=2, accounting=accounting,
        conditions=dict(H="Frozen translated human baseline; evaluator assertions deferred to scorer",
                        A="One generated program; no source library or new pilot outcomes",
                        B="One generated program; exactly three frozen admitted scissors skills; no new pilot outcomes"),
        scoring="Existing private lift_verified and place_verified metrics; report execution_ok separately",
        pairing="H saves each measured initial asset state; A/B restore and verify it before motion",
        limitations=["Single program generation per condition and five cases by default; engineering pilot only.",
                     "Saved asset states exclude PhysX contact/solver caches; no identical trajectory claim.",
                     "The proposed two-second stable-hold/rotation metric is not implemented.",
                     "No refinement, selection, retries, source skill admission, or expansion after seeing outcomes."])
    if record_screen:
        plan["record_screen"] = True
        plan["recording"] = dict(scope="Isaac rendered app window only", fps=4, audio=False,
            file="trials/<identifier>/screen.mp4", includes_motionless_preflight=True,
            limitation="Capture and encoding add wall-clock overhead equally for H/A/B; not camera-only footage")
    if session_accounting is not None:
        plan["session_accounting"] = session_accounting
    if physics_reference is not None:
        plan["physics_reference"] = physics_reference
        plan["limitations"].append("Declared source-matched solver settings differ from the preserved failed default-physics preflight.")
    if target == "scissor":
        plan["perception_check"] = dict(target=target, text="scissor", threshold=0.5,
            conditions=["H", "A", "B"],
            expected_service=read_json(ROOT / "logs/sam3_saved_image_audit_20261007/restored_health.json"))
        plan["revision_policy"] = "One fresh A and B submission before manipulation; no outcome-driven revisions. B differs only by the frozen source library."
        plan["limitations"].append("Same target object as the source campaign; this tests library reuse, not cross-object transfer.")
    if sam3_target_prompt is not None:
        plan["perception_mapping"] = dict(target=target, text=sam3_target_prompt, threshold=0.5,
            conditions=["H", "A", "B"], returns="All candidates; each policy owns association and motion",
            calibration="Saved-image diagnosis, no target manipulation practice; fresh observation seed 552",
            expected_service=read_json(ROOT / "logs/sam3_saved_image_audit_20261007/restored_health.json"))
        plan["revision_policy"] = "One fresh A and B submission before manipulation; no outcome-driven revisions. B differs only by the frozen source library."
        plan["limitations"].append("Shared prompt calibration precedes generation; this is not zero-shot object recognition.")
    write_json(directory / "plan.json", plan)
    protected = ["contract.json", "plan.json", "launch.json", "baseline_provenance.json",
                 "programs/H/frozen_program.py", "programs/H/library.json",
                 "programs/A/library.json", "programs/B/library.json"]
    write_json(directory / "setup_hashes.json", {name: file_sha(directory / name) for name in protected})
    write_json(directory / "state.json", dict(status="prepared", phase="setup", sessions_started=0, trials={}))
    return plan


class FrozenComparison:
    def __init__(self, directory, *, launcher=r"C:\isaac-sim-450\python.bat", simulator=run_trial):
        self.root = Path(directory).resolve()
        self.verify(read_json(self.root / "setup_hashes.json"))
        self.plan = read_json(self.root / "plan.json")
        self.state = read_json(self.root / "state.json")
        self.launcher, self.simulator = launcher, simulator
        accounting = self.plan.get("session_accounting")
        if accounting is not None:
            parent = Path(accounting["parent"])
            if (file_sha(parent / "state.json") != accounting["state_sha256"] or
                    file_sha(parent / "contract.json") != accounting["contract_sha256"] or
                    ("plan_sha256" in accounting and file_sha(parent / "plan.json") != accounting["plan_sha256"])):
                raise ValueError("Preserved session parent changed")

    def verify(self, hashes):
        for name, digest in hashes.items():
            if file_sha(self.root / name) != digest:
                raise ValueError("Frozen artifact changed: " + name)

    def success_policy(self):
        path = self.root / "control/physical_success_policy.json"
        if not path.exists():
            return None
        policy = read_json(path)
        if (policy.get("version") != 1 or policy.get("reporting_only") is not True
                or policy.get("primary_metric") != "physical_success"
                or policy.get("physical_success") != "lift_verified and place_verified"
                or policy.get("strict_success") != "result.success and execution_ok"
                or policy.get("conditions") != ["H", "A", "B"]):
            raise ValueError("Unsupported success reporting amendment")
        if (file_sha(self.root / "setup_hashes.json") != policy["setup_manifest_sha256"]
                or file_sha(self.root / "frozen_programs.json") != policy["programs_manifest_sha256"]):
            raise ValueError("Frozen manifests differ from the success reporting amendment")
        self.verify(policy["snapshot_hashes"])
        return policy

    def save(self, **updates):
        self.state.update(updates)
        if updates.get("status") in ("running", "observed", "frozen", "completed"):
            self.state.pop("error", None)
            self.state.pop("error_type", None)
        write_json(self.root / "state.json", self.state)
        print(json.dumps({key: self.state.get(key) for key in ("status", "phase", "active", "sessions_started")}), flush=True)

    def trial(self, identifier, code, seed, **options):
        directory = self.root / "trials" / identifier
        if directory.exists():
            result = read_json(directory / "result.json")
            if result.get("status") not in ("completed", "program_error", "observed"):
                raise RuntimeError("Interrupted/infrastructure trial preserved; no automatic retry: " + identifier)
            if result.get("seed") != seed or result.get("program_sha256") != program_sha(code):
                raise ValueError("Cached trial seed/program differs")
            self.verify_recording(directory, result)
            self.state["trials"][identifier] = result
            self.save(active=None)
            return result
        carry_in = self.plan.get("session_accounting", {}).get("prior_sessions", 0)
        if self.state["sessions_started"] + carry_in >= self.plan["max_simulator_sessions"]:
            raise ValueError("20-session hard cap reached")
        if identifier in self.state["trials"]:
            raise RuntimeError("Previously launched trial is missing; cannot discard an attempt")
        self.state["sessions_started"] += 1
        self.state["trials"][identifier] = dict(seed=seed, status="launching")
        self.save(status="running", active=identifier)
        if self.plan.get("record_screen"):
            options["record_screen"] = True
        result = self.simulator(self.launcher, code, self.root / "contract.json", seed, directory,
                                wall_timeout=600., headless=self.plan["headless"], **options)
        self.state["trials"][identifier] = result
        self.save(active=None)
        if result.get("status") not in ("completed", "program_error", "observed"):
            raise RuntimeError("Infrastructure failure preserved; evaluation stopped: " + identifier)
        self.verify_recording(directory, result)
        return result

    def verify_recording(self, directory, result):
        if not self.plan.get("record_screen"):
            return
        recording = result.get("screen_recording", {})
        video = directory / "screen.mp4"
        if recording.get("status") != "complete" or not video.is_file():
            raise RuntimeError("Requested window recording failed; trial preserved: " + directory.name)
        if recording.get("sha256") != file_sha(video):
            raise ValueError("Recorded app-window video changed: " + directory.name)

    def observe(self, *, retry_preflight=False):
        code = self.root / "observe.py"
        if not code.exists():
            code.write_text('print("Motionless sensor capture only")\n', encoding="utf-8")
        self.save(phase="initial_observation")
        scene = self.root / "scenes/context.json"
        self.trial("observe", code, self.plan["observation_seed"], observe_only=True, scene_out=scene)
        if "context_scene_sha256" in self.state and file_sha(scene) != self.state["context_scene_sha256"]:
            raise ValueError("Saved motionless context scene changed")
        self.state["context_scene_sha256"] = file_sha(scene)
        self.save()
        identifier = self.state.get("preflight_replay_identifier", "observe_replay")
        if retry_preflight:
            if any((self.root / "model").glob("*.request.json")) or any(
                    key != "observe" and not key.startswith("observe_replay") for key in self.state["trials"]):
                raise ValueError("Preflight retry is permitted only before generation or manipulation")
            previous = self.state["trials"].get(identifier, {})
            if previous.get("status") in (None, "observed", "completed", "program_error", "launching"):
                raise ValueError("Only a completed infrastructure-failed replay preflight may be retried")
            carry_in = self.plan.get("session_accounting", {}).get("prior_sessions", 0)
            if self.state["sessions_started"]+carry_in+1+3*len(self.plan["cases"]) > self.plan["max_simulator_sessions"]:
                raise ValueError("Preflight retry would exceed the cap including remaining rollouts")
            count = sum(key.startswith("observe_replay_retry_") for key in self.state["trials"])
            next_identifier = f"observe_replay_retry_{count+1:03d}"
            write_json(self.root / f"control/{next_identifier}.json", dict(
                previous=identifier, result_sha256=file_sha(self.root / f"trials/{identifier}/result.json"),
                reason="Explicit motionless infrastructure replay retry before any generation or target outcomes",
                snapshot_sha256=file_sha(scene), scene_replay_code_sha256=file_sha(ROOT / "src/aspire/scene_replay.py"),
                max_simulator_sessions=self.plan["max_simulator_sessions"]))
            identifier = next_identifier
            self.state["preflight_replay_identifier"] = identifier
            self.save()
        result = self.trial(identifier, code, self.plan["observation_seed"], observe_only=True, scene_in=scene)
        if not result.get("scene_replay", {}).get("matched"):
            raise ValueError("Motionless replay preflight did not verify scene pairing")
        write_json(self.root / "scene_replay_preflight.json", result["scene_replay"])
        if self.plan.get("perception_mapping") or self.plan.get("perception_check"):
            self.perception_preflight()

    def perception_preflight(self):
        import numpy as np
        from PIL import Image
        from .geometry import mask_to_points, relative_point
        from .perception import Sam3Client
        path = self.root / "control/perception_preflight.json"
        if path.exists():
            record = read_json(path)
            if file_sha(path) != self.state.get("perception_preflight_sha256"):
                raise ValueError("Perception preflight record changed")
            self.verify(record["input_hashes"])
            if not record["ready"]:
                raise ValueError("Mapped perception preflight did not establish two-view target candidates")
            return record
        mapping = self.plan.get("perception_mapping") or self.plan["perception_check"]
        contract = read_json(self.root / "contract.json")
        url = contract["task"]["sam3_url"]
        with urllib.request.urlopen(url + "/health", timeout=10.) as response:
            health = json.load(response)
        if health != mapping["expected_service"]:
            raise ValueError("Mapped comparison perception fingerprint differs")
        directory = self.root / "trials/observe"
        context = read_json(directory / "sensor_context.json")
        observation = read_json(directory / "initial/observation.json")
        snapshot = read_json(self.root / "scenes/context.json")
        robot = snapshot["state"]["articulation"]["robot"]["root_pose"][0]
        target = relative_point(snapshot["state"]["rigid_object"]["object"]["root_pose"][0][:3],
                                robot[:3], robot[3:])
        inputs = ["scenes/context.json", "trials/observe/sensor_context.json", "trials/observe/initial/observation.json"]
        rows, views = [], set()
        client = Sam3Client(url)
        for camera in ("top", "front", "left", "right"):
            image = directory / "initial" / f"{camera}.png"
            depth_path = directory / "initial" / f"{camera}_depth.npy"
            inputs.extend([str(image.relative_to(self.root)), str(depth_path.relative_to(self.root))])
            depth = np.load(depth_path, allow_pickle=False)
            calibration = observation["cameras"][camera]
            detections = client.segment(np.asarray(Image.open(image).convert("RGB")), mapping["text"], allow_empty=True)
            candidates = []
            for detection in detections:
                candidate = dict(score=detection["score"], box=detection["box"])
                try:
                    points = mask_to_points(detection["mask"], depth, calibration["intrinsics"], calibration["pose_mat"])
                    table = context["table_height"]
                    points = points[(points[:, 2] > table+.0005) & (points[:, 2] < table+.045)]
                    if len(points) < 8:
                        raise ValueError("Insufficient table-foreground points")
                    center = np.median(points, axis=0)
                    distance = float(np.linalg.norm(center[:2]-target[:2]))
                    candidate.update(points=len(points), center_base=center.tolist(), private_target_root_xy_distance=distance)
                    if distance < .06:
                        views.add(camera)
                except ValueError as error:
                    candidate["depth_error"] = str(error)
                candidates.append(candidate)
            rows.append(dict(camera=camera, detections=candidates))
        record = dict(ready=len(views) >= 2, matched_views=sorted(views), results=rows,
            prompt=mapping["text"], threshold=mapping["threshold"], service=health,
            input_hashes={name: file_sha(self.root / name) for name in inputs},
            limitation="Private root-XY proxy used only for a diagnostic gate; not mask ground truth, policy filtering or model input")
        write_json(path, record)
        self.save(perception_ready=record["ready"], perception_preflight_sha256=file_sha(path))
        if not record["ready"]:
            self.save(status="stopped", phase="perception_blocked", active=None)
            raise ValueError("Mapped perception preflight did not establish two-view target candidates")
        return record

    def payload(self, condition):
        if condition not in ("A", "B"):
            raise ValueError("Only A/B use the model")
        directory = self.root / "trials/observe"
        context = read_json(directory / "sensor_context.json")
        prompt = (directory / "prompt.txt").read_text(encoding="utf-8")
        library = read_json(self.root / f"programs/{condition}/library.json")
        target = self.plan.get("target", "kelly")
        label = "Kelly" if target == "kelly" else "scissors" if target == "scissor" else target
        if context["task_target"] != target:
            raise ValueError("Observed target differs from frozen comparison target")
        scope = ("This is fresh same-object frozen-skill generation: " if target == "scissor" else
                 "This is zero-shot generation: ")
        library_validation = ("were debug-validated on earlier scissors scenes, not this pilot's fresh seeds; "
                              if target == "scissor" else f"are not {label}-validated; ")
        instruction = (f"Generate ONE complete standalone Python program to pick {label} and place it in its tray lane. "
            "Use only the documented sensor/motor API and imports numpy/math. SAM3 uses text prompts, not points. "
            f"{scope}you cannot execute, inspect outcomes, revise, select candidates, or "
            "access simulator state. The context is a single motionless sensor observation on a separate seed. "
            "Use sensors during execution, never hardcode observed target coordinates. Do not use get_task_feedback. "
            "The private evaluator scores the executed program independently. Source library repairs, when supplied, "
            f"{library_validation}respect their limitations and adapt assumptions using sensors. "
            "Submit exactly one complete program using submit_program, without partial code or other tool calls.")
        mapping = self.plan.get("perception_mapping")
        if mapping:
            instruction += (f" Shared perception calibration for H/A/B maps the default or explicit canonical '{target}' query "
                f"to '{mapping['text']}' at threshold 0.5. All candidates are returned unchanged, including possible "
                "other instrument instances; confidence is not target identity. Each policy must associate candidates "
                "using sensors. No source fusion helper or private target filter is added to the API.")
        content = [dict(type="text", text=instruction + "\nPublic task/API:\n" + prompt +
                        "\nInitial sensor/fixture context:\n" + json.dumps(context) +
                        "\nFrozen source repair library:\n" + json.dumps(library))]
        for camera in ("top", "front", "left", "right", "wrist", "tray"):
            image = base64.b64encode((directory / "initial" / f"{camera}.png").read_bytes()).decode("ascii")
            content.extend([dict(type="text", text="Initial " + camera + " camera:"),
                            dict(type="image_url", image_url=dict(url="data:image/png;base64,"+image))])
        submit = dict(type="function", function=dict(SUBMIT["function"],
            description=f"Submit one complete standalone sensor-only {label} program. No practice or revisions."))
        return dict(model=self.plan["model"], max_tokens=128000,
            messages=[dict(role="system", content="Write trusted sensor-only surgical robot code. Follow the supplied API exactly."),
                      dict(role="user", content=content)], tools=[submit],
            tool_choice=dict(type="function", function=dict(name="submit_program")))

    def generate(self, transport):
        if (self.root / "frozen_programs.json").exists():
            self.verify(read_json(self.root / "frozen_programs.json"))
            return
        if self.state.get("perception_ready") is False:
            raise ValueError("Sensor-only perception preflight did not establish target localization")
        if self.plan.get("perception_mapping"):
            if self.state.get("perception_ready") is not True:
                raise ValueError("Mapped perception preflight must pass before generation")
            self.perception_preflight()
        if any(key != "observe" and not key.startswith("observe_replay") for key in self.state["trials"]):
            raise ValueError("Target outcomes already exist: generation forbidden")
        self.verify(read_json(self.root / "setup_hashes.json"))
        inputs = ["trials/observe/prompt.txt", "trials/observe/sensor_context.json"]
        inputs += [f"trials/observe/initial/{camera}.png" for camera in ("top", "front", "left", "right", "wrist", "tray")]
        input_manifest = self.root / "generation_inputs.json"
        if not input_manifest.exists():
            write_json(input_manifest, {name: file_sha(self.root / name) for name in inputs})
        input_hashes = read_json(input_manifest)
        self.verify(input_hashes)
        self.save(status="running", phase="generation")
        self.report()
        for condition in ("A", "B"):
            self.verify(input_hashes)
            request_path = self.root / f"model/{condition}.request.json"
            response_path = self.root / f"model/{condition}.response.json"
            payload = self.payload(condition)
            if request_path.exists() and read_json(request_path) != payload:
                raise ValueError("Generation context changed")
            if not response_path.exists():
                if request_path.exists():
                    control = self.root / "control/transport_recovery.json"
                    if (not control.exists() or condition != "A" or self.state.get("transport_replayed") or
                            file_sha(control) != self.state.get("transport_recovery_sha256") or
                            read_json(control)["request_sha256"] != file_sha(request_path)):
                        raise RuntimeError("Interrupted generation request; do not silently spend another attempt")
                    self.save(transport_replayed=True)
                else:
                    write_json(request_path, payload)
                self.save(active="model:" + condition)
                write_json(response_path, transport(payload))
            reply = read_json(response_path)
            if condition == "B" and (self.root / "control/native_tool_finish_B.json").exists():
                recovery = recover_native_tool_finish(self.root)
                reply = read_json(self.root / recovery["normalized_response"])
            choice = reply["choices"][0]
            if choice.get("finish_reason") != "tool_calls":
                raise ValueError("Incomplete/non-tool response preserved, not executed")
            calls = choice["message"].get("tool_calls", [])
            if len(calls) != 1 or calls[0]["function"]["name"] != "submit_program":
                raise ValueError("Expected exactly one standalone submission")
            value = json.loads(calls[0]["function"]["arguments"])
            if set(value) != {"code", "hypothesis"} or not all(isinstance(item, str) and item.strip() for item in value.values()):
                raise ValueError("Malformed standalone submission")
            validate_sensor_program(value["code"])
            target = self.root / f"programs/{condition}"
            (target / "frozen_program.py").write_text(value["code"], encoding="utf-8")
            write_json(target / "submission.json", value)
        self.verify(input_hashes)
        names = [f"programs/{condition}/frozen_program.py" for condition in ("H", "A", "B")]
        names += [f"model/{condition}.{kind}.json" for condition in ("A", "B") for kind in ("request", "response")]
        names += inputs + ["generation_inputs.json"]
        if (self.root / "control/native_tool_finish_B.json").exists():
            recovery = recover_native_tool_finish(self.root)
            names += list(recovery["hashes"]) + ["control/native_tool_finish_B.json"]
        write_json(self.root / "frozen_programs.json", {name: file_sha(self.root / name) for name in names})
        self.save(status="frozen", phase="ready_for_evaluation", active=None)
        self.report()

    def report(self, *, filename="report.json"):
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("Report filename must be a JSON basename under the run directory")
        policy = self.success_policy()
        primary_metric = "physical_success" if policy is not None else "strict_success"
        pairs = []
        counts = {condition: dict(completed=0, lift_verified=0, place_verified=0, execution_ok=0,
                                  physical_success=0, strict_success=0, success=0)
                  for condition in ("H", "A", "B")}
        for seed in self.plan["cases"]:
            row = dict(seed=seed, conditions={})
            for condition in counts:
                result = self.state["trials"].get(f"{condition}_s{seed}", {})
                if result.get("status") not in ("completed", "program_error"):
                    continue
                feedback = result.get("feedback", {})
                physical_success = bool(feedback.get("lift_verified") and feedback.get("place_verified"))
                strict_success = bool(result.get("success") and result.get("execution_ok"))
                outcome = dict(status=result["status"], execution_ok=bool(result.get("execution_ok")),
                    lift_verified=bool(feedback.get("lift_verified")), place_verified=bool(feedback.get("place_verified")),
                    physical_success=physical_success, strict_success=strict_success,
                    success=physical_success if policy is not None else strict_success, reason=feedback.get("reason"),
                    evaluator_phase=feedback.get("phase"), elapsed_s=result.get("elapsed_s"))
                row["conditions"][condition] = outcome
                counts[condition]["completed"] += 1
                for metric in ("lift_verified", "place_verified", "execution_ok", "physical_success", "strict_success", "success"):
                    counts[condition][metric] += int(outcome[metric])
            pairs.append(row)
        attempted = sum(read_json(path / "report.json")["requests"]
                        for path in self.root.glob("provider_*") if path.is_dir())
        usage = [read_json(path) for path in sorted(self.root.glob("provider_*/request_*.usage.json"))]
        recovery = self.root / "control/transport_recovery.json"
        allowance = read_json(recovery)["extra_attempt_allowance"] if recovery.exists() else 0
        costs = dict(new_model_attempts=attempted, cumulative_model_attempts=self.plan["accounting"]["prior_requests"]+attempted,
                     max_new_model_attempts=2+allowance, max_generated_programs=2,
                     explicit_transport_recovery=allowance, authorized_cumulative_cap=150, provider_usage=usage,
                     total_trial_elapsed_s=sum(row.get("elapsed_s", 0.) for row in self.state["trials"].values()))
        scoring = dict(primary_metric=primary_metric, physical_success="lift_verified and place_verified",
                       strict_success="result.success and execution_ok", post_hoc=bool(policy and policy["post_hoc"]))
        if policy is not None:
            scoring.update(policy="control/physical_success_policy.json",
                policy_sha256=file_sha(self.root / "control/physical_success_policy.json"),
                completed_rollouts_at_amendment=policy["completed_rollouts_at_recording"])
        report = dict(status=self.state["status"], cases=self.plan["cases"],
                   sessions_started=self.state["sessions_started"], counts=counts, pairs=pairs,
                   prior_simulator_sessions=self.plan.get("session_accounting", {}).get("prior_sessions", 0),
                   total_simulator_sessions=self.state["sessions_started"] + self.plan.get("session_accounting", {}).get("prior_sessions", 0),
                   costs=costs, scoring=scoring, limitations=self.plan["limitations"])
        write_json(self.root / filename, report)
        return report

    def evaluate(self):
        hashes = read_json(self.root / "frozen_programs.json")
        self.verify(hashes)
        self.save(status="running", phase="paired_evaluation")
        for seed in self.plan["cases"]:
            scene = self.root / f"scenes/s{seed}.json"
            for condition in ("H", "A", "B"):
                self.verify(hashes)
                self.verify(read_json(self.root / "setup_hashes.json"))
                expected_scene = self.state.get("scene_hashes", {}).get(str(seed))
                if expected_scene and file_sha(scene) != expected_scene:
                    raise ValueError("Saved initial scene changed")
                if condition != "H" and not expected_scene:
                    raise ValueError("H did not commit the saved initial scene")
                kwargs = dict(scene_out=scene) if condition == "H" else dict(scene_in=scene)
                result = self.trial(f"{condition}_s{seed}", self.root / f"programs/{condition}/frozen_program.py", seed, **kwargs)
                if condition != "H" and not result.get("scene_replay", {}).get("matched"):
                    raise ValueError("Unverified initial scene pairing; stop before further trials")
                if condition == "H":
                    self.state.setdefault("scene_hashes", {})[str(seed)] = file_sha(scene)
                    self.save()
                elif file_sha(scene) != self.state["scene_hashes"][str(seed)]:
                    raise ValueError("Saved initial scene changed")
                self.report()
        self.save(status="completed", phase="completed", active=None)
        self.report()


def relay_transport(url, payload):
    request = urllib.request.Request(url + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=1830.) as response:
        return json.load(response)
