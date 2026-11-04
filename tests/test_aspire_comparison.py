"""Verify isolation, immutable generation, paired execution and bounded accounting."""
import ast
import hashlib
import json
import io
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from src.aspire import comparison
from src.aspire.artifacts import write_json
from src.aspire.scene_replay import state_difference, restore_scene, encode_state


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    baselines = {target: (comparison.ROOT / f"examples/aspire/translated/{target}.py").read_text(encoding="utf-8")
                 for target in ("kelly", "scalpel", "scissor")}
    configs = {target: comparison.read_json(comparison.ROOT / f"configs/aspire/translated/{target}-sam3.json")
               for target in ("kelly", "scalpel", "scissor")}
    monkeypatch.setattr(comparison, "ROOT", tmp_path)
    path = tmp_path / "examples/aspire/translated"
    path.mkdir(parents=True)
    for target, baseline in baselines.items():
        (path / f"{target}.py").write_text(baseline, encoding="utf-8")
        write_json(tmp_path / f"configs/aspire/translated/{target}-sam3.json", configs[target])
    write_json(path / "manifest.json", {})
    write_json(tmp_path / "logs/sam3_saved_image_audit_20261007/restored_health.json", dict(ready=True, threshold=.5))
    replay_code = tmp_path / "src/aspire/scene_replay.py"
    replay_code.parent.mkdir(parents=True)
    replay_code.write_text("Replay implementation hash fixture", encoding="utf-8")
    monkeypatch.setattr(comparison, "source_accounting", lambda root=None: dict(prior_requests=96, max_total_requests=150))
    shared = tmp_path / "shared"
    identifiers = []
    for index in range(3):
        pattern = dict(code_sketch='print("source helper")\n', limitations=f"Scissors only {index}")
        provenance = dict(task="scissor", debug_repair_pairs=[dict(seed=101)])
        identifier = hashlib.sha256(json.dumps(dict(pattern=pattern, provenance=provenance), sort_keys=True).encode()).hexdigest()
        write_json(shared / f"{identifier}.json", dict(id=identifier, pattern=pattern, provenance=provenance,
                   status="debug_validated_repair", coordinator_review=dict(admit=True)))
        identifiers.append(identifier)
    monkeypatch.setattr(comparison, "SKILL_IDS", tuple(identifiers))
    directory = tmp_path / "logs/pilot"
    comparison.prepare_comparison(directory, shared_root=shared)
    launches = []

    def simulator(launcher, code, config, seed, out, **kwargs):
        launches.append((seed, Path(out).name, kwargs))
        out = Path(out)
        out.mkdir(parents=True)
        result = dict(seed=seed, program_sha256=comparison.program_sha(code),
                      status="observed" if kwargs.get("observe_only") else "completed", success=True,
                      execution_ok=True, feedback=dict(lift_verified=True, place_verified=True, reason="verified_pick_place"))
        if kwargs.get("scene_out"):
            write_json(kwargs["scene_out"], dict(seed=seed, state=dict(
                articulation=dict(robot=dict(root_pose=[[0, 0, 0, 1, 0, 0, 0]])),
                rigid_object=dict(object=dict(root_pose=[[.03, .03, .02, 1, 0, 0, 0]])))))
        if kwargs.get("scene_in"):
            assert comparison.read_json(kwargs["scene_in"])["seed"] == seed
            result["scene_replay"] = dict(matched=True, max_absolute_error=0.)
        if kwargs.get("observe_only"):
            target = comparison.read_json(config)["task"]["target"]
            write_json(out / "sensor_context.json", dict(task_target=target, robot={}, tray_slot={}, table_height=0.))
            (out / "prompt.txt").write_text("Public API only", encoding="utf-8")
            (out / "initial").mkdir()
            for camera in ("top", "front", "left", "right", "wrist", "tray"):
                Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8)).save(out / "initial" / f"{camera}.png")
                np.save(out / "initial" / f"{camera}_depth.npy", np.full((4, 4), .02))
            write_json(out / "initial/observation.json", dict(cameras={camera: dict(intrinsics=np.eye(3), pose_mat=np.eye(4))
                       for camera in ("top", "front", "left", "right")}))
            write_json(out / "reset_diagnostics.json", dict(secret="PRIVATE_TARGET_POSE"))
        write_json(out / "result.json", result)
        return result

    return comparison.FrozenComparison(directory, simulator=simulator), launches


def calibrated_pilot(pilot, monkeypatch, *, detections=True):
    original, launches = pilot
    parent = comparison.ROOT / "logs/blocked_scalpel"
    write_json(parent / "contract.json", dict(task=dict(target="scalpel")))
    write_json(parent / "state.json", dict(status="stopped", phase="perception_blocked", sessions_started=2,
                                          trials=dict(observe={}, observe_replay={})))
    from src.aspire.perception import Sam3Client
    monkeypatch.setattr(comparison.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(
        json.dumps(dict(ready=True, threshold=.5)).encode()))
    monkeypatch.setattr(Sam3Client, "segment", lambda self, rgb, text, **kwargs: [dict(mask=np.ones((4, 4), dtype=bool),
        score=.7, box=[0, 0, 4, 4])] if detections else [])
    root = comparison.ROOT / "logs/calibrated_scalpel"
    comparison.prepare_comparison(root, target="scalpel", sam3_target_prompt="knife", session_parent=parent,
                                  shared_root=comparison.ROOT / "shared")
    return comparison.FrozenComparison(root, simulator=original.simulator), launches


def test_calibrated_mapping_is_shared_and_preserves_20_total_session_cap(pilot, monkeypatch):
    campaign, launches = calibrated_pilot(pilot, monkeypatch)
    campaign.observe()
    assert campaign.plan["observation_seed"] == 552
    assert campaign.state["perception_ready"]
    assert campaign.perception_preflight()["matched_views"] == ["front", "left", "right", "top"]
    assert comparison.read_json(campaign.root / "contract.json")["task"]["sam3_target_prompt"] == "knife"
    first, second = campaign.payload("A"), campaign.payload("B")
    for payload in (first, second):
        text = payload["messages"][1]["content"][0]["text"]
        assert "Shared perception calibration" in text and "'knife'" in text
        assert "private_target_root_xy_distance" not in json.dumps(payload)
    assert first["messages"][1]["content"][0]["text"].split("\nFrozen source repair library:")[0] == second["messages"][1]["content"][0]["text"].split("\nFrozen source repair library:")[0]
    campaign.generate(response)
    campaign.evaluate()
    assert len(launches) == 17
    assert comparison.read_json(campaign.root / "report.json")["total_simulator_sessions"] == 19
    campaign.state["sessions_started"] = 18
    with pytest.raises(ValueError, match="hard cap"):
        campaign.trial("extra", campaign.root / "observe.py", 999)


def test_mapped_empty_perception_stops_before_model_generation(pilot, monkeypatch):
    campaign, launches = calibrated_pilot(pilot, monkeypatch, detections=False)
    with pytest.raises(ValueError, match="two-view"):
        campaign.observe()
    assert len(launches) == 2 and campaign.state["phase"] == "perception_blocked"
    with pytest.raises(ValueError, match="perception preflight"):
        campaign.generate(lambda payload: pytest.fail("No call after failed mapped detection"))
    assert not (campaign.root / "model/A.request.json").exists()


def test_session_carry_in_cannot_be_reset_or_mutated(pilot, monkeypatch):
    campaign, _ = calibrated_pilot(pilot, monkeypatch)
    parent = Path(campaign.plan["session_accounting"]["parent"])
    with pytest.raises(ValueError, match="20-session cap"):
        comparison.prepare_comparison(comparison.ROOT / "logs/too_many", cases=6, target="scalpel",
            sam3_target_prompt="knife", session_parent=parent, shared_root=comparison.ROOT / "shared")
    state = comparison.read_json(parent / "state.json")
    state["sessions_started"] = 3
    write_json(parent / "state.json", state)
    with pytest.raises(ValueError, match="session parent changed"):
        comparison.FrozenComparison(campaign.root)


def test_scissors_reset_recovery_preserves_failed_start_and_source_physics(pilot, monkeypatch):
    original, launches = pilot
    parent = comparison.ROOT / "logs/failed_scissors_reset"
    parent.mkdir()
    write_json(parent / "state.json", dict(status="stopped", phase="initial_observation", sessions_started=1,
        trials=dict(observe=dict(status="error", seed=801, error="reset_settle_failed: settle_timeout_or_missing_object"))))
    write_json(parent / "contract.json", dict(task=dict(target="scissor")))
    write_json(parent / "plan.json", {})
    before = comparison.file_sha(parent / "state.json")
    source = comparison.ROOT / "logs/source_scissors"
    source_protocol = comparison.read_json(original.root / "contract.json")
    source_protocol["task"].update(target="scissor", solver_position_iterations=32, solver_velocity_iterations=8)
    write_json(source / "contract.json", source_protocol)
    monkeypatch.setattr(comparison, "SOURCE_CAMPAIGN", source)
    root = comparison.ROOT / "logs/scissors_source_physics"
    plan = comparison.prepare_comparison(root, target="scissor", session_parent=parent,
        match_source_physics=True, shared_root=comparison.ROOT / "shared")
    task = comparison.read_json(root / "contract.json")["task"]
    assert task["solver_position_iterations"] == 32 and task["solver_velocity_iterations"] == 8
    assert plan["physics_reference"]["contract_sha256"] == comparison.file_sha(source / "contract.json")
    assert plan["session_accounting"]["prior_sessions"] == 1
    assert plan["observation_seed"] == 801 and plan["cases"] == list(range(901, 906))
    assert 1 + 2 + plan["max_manipulation_rollouts"] == 18
    assert comparison.file_sha(parent / "state.json") == before and not launches
    comparison.FrozenComparison(root, simulator=original.simulator).report()
    assert comparison.read_json(root / "report.json")["total_simulator_sessions"] == 1
    parent_plan = comparison.read_json(parent / "plan.json")
    parent_plan["session_accounting"] = dict(prior_sessions=3)
    write_json(parent / "plan.json", parent_plan)
    with pytest.raises(ValueError, match="session parent changed"):
        comparison.FrozenComparison(root)
    with pytest.raises(ValueError, match="20-session cap"):
        comparison.prepare_comparison(comparison.ROOT / "logs/nested_over_cap", target="scissor",
            session_parent=parent, shared_root=comparison.ROOT / "shared")
    parent_plan["session_accounting"] = dict(prior_sessions=2)
    write_json(parent / "plan.json", parent_plan)
    nested = comparison.prepare_comparison(comparison.ROOT / "logs/nested_at_cap", target="scissor",
        session_parent=parent, shared_root=comparison.ROOT / "shared")
    assert nested["session_accounting"]["prior_sessions"] == 3


@pytest.mark.parametrize("phase,error,generated", [
    ("initial_observation", "blank_camera: top", False),
    ("paired_evaluation", "reset_settle_failed: timeout", False),
    ("initial_observation", "reset_settle_failed: timeout", True),
])
def test_reset_session_carry_in_rejects_nonreset_or_generated_run(pilot, phase, error, generated):
    parent = comparison.ROOT / "logs/ineligible_reset"
    write_json(parent / "state.json", dict(status="stopped", phase=phase, sessions_started=1,
        trials=dict(observe=dict(status="error", error=error))))
    write_json(parent / "contract.json", dict(task=dict(target="scissor")))
    if generated:
        write_json(parent / "model/A.request.json", {})
    with pytest.raises(ValueError, match="stopped, motionless"):
        comparison.prepare_comparison(comparison.ROOT / "logs/ineligible_resume", target="scissor",
            session_parent=parent, shared_root=comparison.ROOT / "shared")


def test_source_physics_cannot_be_applied_to_cross_object_pilot(pilot):
    with pytest.raises(ValueError, match="same-object scissors"):
        comparison.prepare_comparison(comparison.ROOT / "logs/cross_object_source_physics", target="scalpel",
            match_source_physics=True, shared_root=comparison.ROOT / "shared")


def test_scalpel_preparation_isolated_from_kelly_with_99_carry_in(pilot, monkeypatch):
    kelly, launches = pilot
    original_hashes = comparison.read_json(kelly.root / "setup_hashes.json")
    parent = comparison.ROOT / "logs/completed_kelly"
    accounting = dict(source_campaign=str(parent), source_state_sha256="completed-kelly-state",
                      prior_requests=99, max_total_requests=150)
    seen = []
    def account(root=None):
        seen.append(root)
        return accounting
    monkeypatch.setattr(comparison, "source_accounting", account)
    root = comparison.ROOT / "logs/scalpel"
    plan = comparison.prepare_comparison(root, target="scalpel", source_root=parent,
                                         shared_root=comparison.ROOT / "shared")
    comparison.verify_accounting(plan["accounting"])
    assert seen == [parent, str(parent)]
    assert plan["target"] == "scalpel"
    assert plan["experiment_type"] == "zero_shot_cross_object_transfer"
    assert plan["accounting"]["prior_requests"] == 99
    assert plan["source_library_campaign"] == str(comparison.SOURCE_CAMPAIGN)
    assert plan["cases"] == list(range(701, 706)) and plan["observation_seed"] == 551
    contract = comparison.read_json(root / "contract.json")
    assert contract["task"]["target"] == "scalpel"
    assert not contract["task"]["allow_evaluator_feedback"]
    assert "'target': 'scalpel'" in (root / "programs/H/frozen_program.py").read_text(encoding="utf-8")
    assert comparison.read_json(root / "programs/B/library.json") == comparison.read_json(kelly.root / "programs/B/library.json")
    campaign = comparison.FrozenComparison(root, simulator=kelly.simulator)
    campaign.observe()
    assert len(launches) == 2 and all(seed == 551 for seed, _, _ in launches)
    payload = campaign.payload("A")
    assert "pick scalpel" in payload["messages"][1]["content"][0]["text"]
    assert "Kelly" not in json.dumps(payload)
    assert "sensor-only scalpel program" in payload["tools"][0]["function"]["description"]
    campaign.generate(response)
    campaign.evaluate()
    assert len(launches) == 17 and campaign.state["sessions_started"] == 17
    kelly.verify(original_hashes)


@pytest.mark.parametrize("detected", [True, False])
def test_scissors_same_object_pilot_is_fresh_and_gated(pilot, monkeypatch, detected):
    original, launches = pilot
    original_hashes = comparison.read_json(original.root / "setup_hashes.json")
    accounting = dict(prior_requests=99, max_total_requests=150)
    monkeypatch.setattr(comparison, "source_accounting", lambda root=None: accounting)
    root = comparison.ROOT / "logs/scissors"
    plan = comparison.prepare_comparison(root, target="scissor", shared_root=comparison.ROOT / "shared")
    assert plan["experiment_type"] == "same_object_frozen_skill_ablation"
    assert plan["observation_seed"] == 801 and plan["cases"] == list(range(901, 906))
    assert not set([801, *plan["cases"]]).intersection(range(1, 126))
    assert plan["accounting"]["prior_requests"] == 99 and plan["max_new_model_requests"] == 2
    assert plan["max_manipulation_rollouts"] == 15 and plan["max_simulator_sessions"] == 20
    assert "perception_mapping" not in plan and plan["perception_check"]["text"] == "scissor"
    contract = comparison.read_json(root / "contract.json")
    assert contract["task"]["target"] == "scissor" and not contract["task"]["allow_evaluator_feedback"]
    assert "sam3_target_prompt" not in contract["task"]
    assert "'target': 'scissor'" in (root / "programs/H/frozen_program.py").read_text(encoding="utf-8")
    assert len(comparison.read_json(root / "programs/B/library.json")) == 3
    assert comparison.read_json(root / "programs/A/library.json") == []

    class Health:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(plan["perception_check"]["expected_service"]).encode()

    class Client:
        def __init__(self, url):
            pass
        def segment(self, rgb, text, **kwargs):
            assert text == "scissor" and kwargs["allow_empty"]
            return [dict(mask=np.ones((4, 4), dtype=bool), box=[0., 0., 4., 4.], score=.9)] if detected else []

    monkeypatch.setattr(comparison.urllib.request, "urlopen", lambda *args, **kwargs: Health())
    monkeypatch.setattr("src.aspire.perception.Sam3Client", Client)
    campaign = comparison.FrozenComparison(root, simulator=original.simulator)
    if not detected:
        with pytest.raises(ValueError, match="two-view target"):
            campaign.observe()
        with pytest.raises(ValueError, match="perception"):
            campaign.generate(lambda payload: pytest.fail("Failed perception must not spend a model request"))
        assert campaign.state["sessions_started"] == 2
    else:
        campaign.observe()
        assert campaign.state["perception_ready"]
        payloads = [campaign.payload(condition) for condition in ("A", "B")]
        for payload in payloads:
            instruction = payload["messages"][1]["content"][0]["text"]
            assert "pick scissors" in instruction and "same-object" in instruction
            assert "were debug-validated on earlier scissors scenes" in instruction
            assert "not scissors-validated" not in instruction
            assert "PRIVATE_TARGET_POSE" not in json.dumps(payload)
        assert "Scissors only" not in json.dumps(payloads[0])
        assert "Scissors only" in json.dumps(payloads[1])
        campaign.generate(response)
        campaign.evaluate()
        assert campaign.state["sessions_started"] == 17 and len(launches) == 17
    original.verify(original_hashes)


def test_requested_recording_is_frozen_and_a_missing_clip_stops_run(pilot):
    original, launches = pilot
    assert "record_screen" not in original.plan
    root = comparison.ROOT / "logs/recorded_scissors"
    plan = comparison.prepare_comparison(root, target="scissor", record_screen=True,
        shared_root=comparison.ROOT / "shared")
    assert plan["record_screen"] and plan["recording"]["fps"] == 4
    assert not plan["recording"]["audio"] and not plan["headless"]
    campaign = comparison.FrozenComparison(root, simulator=original.simulator)
    with pytest.raises(RuntimeError, match="window recording failed"):
        campaign.observe()
    assert campaign.state["sessions_started"] == 1
    assert launches[0][2]["record_screen"]


def test_accounting_change_rejected(pilot, monkeypatch):
    campaign, _ = pilot
    monkeypatch.setattr(comparison, "source_accounting", lambda root: dict(prior_requests=99))
    with pytest.raises(ValueError, match="accounting changed"):
        comparison.verify_accounting(campaign.plan["accounting"])


def test_target_context_mismatch_stops_generation(pilot):
    campaign, launches = pilot
    campaign.observe()
    write_json(campaign.root / "trials/observe/sensor_context.json", dict(task_target="scalpel"))
    with pytest.raises(ValueError, match="Observed target differs"):
        campaign.generate(lambda payload: pytest.fail("Wrong-target generation forbidden"))
    assert len(launches) == 2


def test_failed_perception_gate_blocks_model_request(pilot):
    campaign, launches = pilot
    campaign.observe()
    campaign.save(status="stopped", phase="perception_blocked", perception_ready=False)
    with pytest.raises(ValueError, match="perception preflight"):
        campaign.generate(lambda payload: pytest.fail("No model call after failed localization gate"))
    assert len(launches) == 2
    assert not (campaign.root / "model/A.request.json").exists()
    assert not (campaign.root / "frozen_programs.json").exists()


def response(payload):
    return dict(choices=[dict(finish_reason="tool_calls", message=dict(tool_calls=[dict(function=dict(
        name="submit_program", arguments=json.dumps(dict(code='print("generated")\n', hypothesis="Sensor-only plan"))))]))])


def test_saved_native_tool_finish_recovery_never_regenerates_or_changes_code(pilot):
    from src.aspire.relay import collect_messages_stream
    campaign, launches = pilot
    campaign.observe()
    payloads = []
    original_code = 'print("original B submission")\n'
    def transport(payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return response(payload)
        provider = campaign.root / "provider_000"
        provider.mkdir()
        arguments = json.dumps(dict(code=original_code, hypothesis="Original sensor plan"))
        events = [dict(type="message_start", message=dict(id="native", model="test", usage={})),
            dict(type="content_block_start", index=0, content_block=dict(type="tool_use", id="t", name="submit_program", input={})),
            dict(type="content_block_delta", index=0, delta=dict(type="input_json_delta", partial_json=arguments)),
            dict(type="content_block_stop", index=0),
            dict(type="message_delta", delta=dict(stop_reason="end_turn")), dict(type="message_stop")]
        lines = [("data: " + json.dumps(event) + "\n").encode() for event in events]
        reply = collect_messages_stream(iter(lines), provider / "request_002.stream.sse")
        reply["choices"][0]["finish_reason"] = "stop"
        write_json(provider / "request_002.response.json", reply)
        write_json(provider / "report.json", dict(requests=2, completed=2, pending=0))
        return reply
    with pytest.raises(ValueError, match="Incomplete/non-tool"):
        campaign.generate(transport)
    campaign.save(status="stopped", active=None, error="Incomplete/non-tool response preserved, not executed")
    original_response = comparison.file_sha(campaign.root / "model/B.response.json")
    record = comparison.recover_native_tool_finish(campaign.root)
    assert record["new_model_attempts"] == record["program_changes"] == 0
    assert record["native_stop_reason"] == "end_turn" and len(payloads) == 2
    assert comparison.file_sha(campaign.root / "model/B.response.json") == original_response
    assert comparison.recover_native_tool_finish(campaign.root) == record
    campaign = comparison.FrozenComparison(campaign.root, simulator=campaign.simulator)
    campaign.generate(lambda payload: pytest.fail("Never regenerate a saved native completion"))
    assert (campaign.root / "programs/B/frozen_program.py").read_text(encoding="utf-8") == original_code
    frozen = comparison.read_json(campaign.root / "frozen_programs.json")
    assert "model/B.normalized_response.json" in frozen and "control/native_tool_finish_B.json" in frozen
    assert len(payloads) == 2 and len(launches) == 2
    normalized = campaign.root / record["normalized_response"]
    normalized.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        comparison.recover_native_tool_finish(campaign.root)


def test_native_finish_recovery_rejects_unverified_or_post_outcome_failure(pilot):
    campaign, _ = pilot
    with pytest.raises(ValueError, match="stopped pre-evaluation"):
        comparison.recover_native_tool_finish(campaign.root)
    campaign.save(status="stopped", phase="generation", error="Incomplete/non-tool response preserved, not executed")
    with pytest.raises(ValueError, match="two finalized"):
        comparison.recover_native_tool_finish(campaign.root)
    campaign.state["trials"]["H_s601"] = dict(status="completed", success=False)
    campaign.save()
    with pytest.raises(ValueError, match="stopped pre-evaluation"):
        comparison.recover_native_tool_finish(campaign.root)


def test_boundary_changes_only_two_oracle_functions(pilot):
    campaign, _ = pilot
    original = (comparison.ROOT / "examples/aspire/translated/kelly.py").read_text(encoding="utf-8")
    sanitized = (campaign.root / "programs/H/frozen_program.py").read_text(encoding="utf-8")
    before, after = ast.parse(original), ast.parse(sanitized)
    for tree in (before, after):
        tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef)
                     or node.name not in ("require_lift", "require_place")]
    assert ast.dump(before) == ast.dump(after)
    assert "get_task_feedback" not in sanitized
    assert not comparison.read_json(campaign.root / "contract.json")["task"]["allow_evaluator_feedback"]


def test_physical_success_amendment_preserves_strict_outcomes_and_raw_trials(pilot):
    campaign, launches = pilot
    campaign.observe()
    campaign.generate(response)
    seeds = campaign.plan["cases"]
    cases = [
        dict(status="program_error", execution_ok=False, success=True,
             feedback=dict(lift_verified=True, place_verified=True, reason="verified_pick_place")),
        dict(status="completed", execution_ok=True, success=True,
             feedback=dict(lift_verified=True, place_verified=True)),
        dict(status="completed", execution_ok=True, success=False,
             feedback=dict(lift_verified=True, place_verified=False)),
        dict(status="program_error", execution_ok=False, success=False,
             feedback=dict(lift_verified=False, place_verified=True)),
        dict(status="launching", execution_ok=False, success=False,
             feedback=dict(lift_verified=True, place_verified=True)),
    ]
    for condition in ("H", "A", "B"):
        for seed, result in zip(seeds, cases):
            campaign.state["trials"][f"{condition}_s{seed}"] = result
            write_json(campaign.root / f"trials/{condition}_s{seed}/result.json", result)
    campaign.save(status="running", phase="paired_evaluation", active=f"B_s{seeds[-1]}")
    legacy = campaign.report()
    assert legacy["scoring"]["primary_metric"] == "strict_success"
    assert all(row["success"] == 1 and row["physical_success"] == 2 for row in legacy["counts"].values())
    protected = [campaign.root / "state.json", campaign.root / "report.json",
                 campaign.root / "setup_hashes.json", campaign.root / "frozen_programs.json"]
    protected += list(campaign.root.glob("trials/*/result.json"))
    before = {str(path): comparison.file_sha(path) for path in protected}
    policy = comparison.record_physical_success_policy(campaign.root)
    assert policy["reporting_only"] and policy["post_hoc"] and policy["completed_rollouts_at_recording"] == 12
    assert comparison.record_physical_success_policy(campaign.root) == policy
    report = campaign.report(filename="physical_success_report.json")
    assert report["scoring"]["primary_metric"] == "physical_success" and report["scoring"]["post_hoc"]
    for row in report["counts"].values():
        assert row["completed"] == 4
        assert row["success"] == row["physical_success"] == 2
        assert row["strict_success"] == 1
    for condition in ("H", "A", "B"):
        outcome = report["pairs"][0]["conditions"][condition]
        assert outcome["success"] and outcome["physical_success"] and not outcome["strict_success"]
        assert outcome["status"] == "program_error" and not outcome["execution_ok"]
    assert {str(path): comparison.file_sha(path) for path in protected} == before
    assert len(launches) == 2
    with pytest.raises(ValueError, match="JSON basename"):
        campaign.report(filename="../report.json")
    tampered = dict(policy, conditions=["B"])
    write_json(campaign.root / "control/physical_success_policy.json", tampered)
    with pytest.raises(ValueError, match="Unsupported success"):
        campaign.report(filename="physical_success_report.json")


def test_physical_report_follows_without_overwriting_active_supervisor_report(pilot, monkeypatch):
    from scripts import run_kelly_comparison as runner
    campaign, launches = pilot
    campaign.observe()
    campaign.generate(response)
    campaign.save(status="running", phase="paired_evaluation", active="H_s601")
    campaign.report()
    write_json(campaign.root / "supervisor.json", dict(pid=123, status="running", stage="evaluate"))
    original_report = (campaign.root / "report.json").read_bytes()
    original_supervisor = (campaign.root / "supervisor.json").read_bytes()
    transitions = []
    def running(pid):
        assert pid == 123
        return not transitions
    def advance(seconds):
        assert seconds == 30.
        assert (campaign.root / "report.json").read_bytes() == original_report
        assert (campaign.root / "supervisor.json").read_bytes() == original_supervisor
        assert comparison.read_json(campaign.root / "physical_success_report.json")["scoring"]["primary_metric"] == "physical_success"
        campaign.save(status="completed", phase="completed", active=None)
        transitions.append(True)
    monkeypatch.setattr(runner, "process_is_running", running)
    monkeypatch.setattr(runner.time, "sleep", advance)
    report = runner.report_comparison(campaign.root, physical_success=True, follow=True)
    assert report["status"] == "completed" and report["scoring"]["primary_metric"] == "physical_success"
    assert (campaign.root / "control/final_report_before_physical_policy.json").read_bytes() == original_report
    assert (campaign.root / "supervisor.json").read_bytes() == original_supervisor
    assert len(launches) == 2 and transitions == [True]


def test_reporting_amendment_requires_frozen_programs(pilot):
    campaign, _ = pilot
    with pytest.raises(ValueError, match="already frozen"):
        comparison.record_physical_success_policy(campaign.root)


def test_generation_isolation_and_all_15_frozen_paired_rollouts(pilot):
    campaign, launches = pilot
    campaign.observe()
    payloads = []
    def transport(payload):
        assert len(launches) == 2
        assert campaign.state["phase"] == "generation"
        payloads.append(payload)
        return response(payload)
    campaign.generate(transport)
    assert len(payloads) == 2
    assert "PRIVATE_TARGET_POSE" not in json.dumps(payloads)
    assert "Scissors only" not in json.dumps(payloads[0])
    assert "Scissors only" in json.dumps(payloads[1])
    first = payloads[0]["messages"][1]["content"]
    second = payloads[1]["messages"][1]["content"]
    assert first[1:] == second[1:]
    assert first[0]["text"].split("\nFrozen source repair library:")[0] == second[0]["text"].split("\nFrozen source repair library:")[0]
    assert comparison.read_json(campaign.root / "programs/A/library.json") == []
    assert len(comparison.read_json(campaign.root / "programs/B/library.json")) == 3
    campaign.evaluate()
    assert len(launches) == 17
    assert all(not kwargs["headless"] for _, _, kwargs in launches)
    assert len([item for item in launches if not item[2].get("observe_only")]) == 15
    report = comparison.read_json(campaign.root / "report.json")
    assert all(row["success"] == 5 and row["lift_verified"] == 5 for row in report["counts"].values())
    assert campaign.state["status"] == "completed"
    campaign.evaluate()
    assert len(launches) == 17


@pytest.mark.parametrize("artifact", ["programs/A/library.json", "programs/H/frozen_program.py", "plan.json"])
def test_frozen_setup_rejects_tampering(pilot, artifact):
    campaign, _ = pilot
    (campaign.root / artifact).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        comparison.FrozenComparison(campaign.root)


def test_no_outcome_driven_generation_or_reselection(pilot):
    campaign, _ = pilot
    campaign.observe()
    campaign.state["trials"]["H_s601"] = dict(success=False)
    with pytest.raises(ValueError, match="outcomes already exist"):
        campaign.generate(response)


def test_truncated_and_interrupted_generation_are_not_executed_or_retried(pilot):
    campaign, launches = pilot
    campaign.observe()
    with pytest.raises(ValueError, match="Incomplete"):
        campaign.generate(lambda payload: dict(choices=[dict(finish_reason="length", message=dict(content="partial"))]))
    assert not (campaign.root / "frozen_programs.json").exists()
    assert len(launches) == 2
    with pytest.raises(FileNotFoundError):
        campaign.evaluate()
    (campaign.root / "model/A.response.json").unlink()
    with pytest.raises(RuntimeError, match="Interrupted generation"):
        campaign.generate(lambda payload: pytest.fail("No duplicate request allowed"))


def test_scene_tampering_stops_before_any_new_manipulation(pilot):
    campaign, launches = pilot
    campaign.observe()
    campaign.generate(response)
    campaign.evaluate()
    write_json(campaign.root / "scenes/s601.json", dict(seed=999))
    with pytest.raises(ValueError, match="Saved initial scene changed"):
        campaign.evaluate()
    assert len(launches) == 17


def test_cached_program_hash_normalizes_windows_newlines(pilot):
    campaign, launches = pilot
    campaign.observe()
    code = campaign.root / "observe.py"
    code.write_bytes(code.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    campaign.trial("observe", code, 501)
    assert len(launches) == 2


def test_simulator_hard_cap_includes_preflight_and_failed_starts(pilot):
    campaign, launches = pilot
    campaign.state["sessions_started"] = 20
    with pytest.raises(ValueError, match="hard cap"):
        campaign.observe()
    assert not launches


def test_explicit_preflight_retry_preserves_failure_and_budget(pilot):
    campaign, launches = pilot
    campaign.observe()
    result = campaign.state["trials"]["observe_replay"]
    result["status"] = "error"
    result["error"] = "inference tensor infrastructure failure"
    path = campaign.root / "trials/observe_replay/result.json"
    write_json(path, result)
    digest = comparison.file_sha(path)
    campaign.observe(retry_preflight=True)
    assert len(launches) == 3
    assert campaign.state["sessions_started"] == 3
    assert comparison.file_sha(path) == digest
    assert campaign.state["preflight_replay_identifier"] == "observe_replay_retry_001"
    assert comparison.read_json(campaign.root / "control/observe_replay_retry_001.json")["result_sha256"] == digest
    campaign.generate(response)
    with pytest.raises(ValueError, match="only before"):
        campaign.observe(retry_preflight=True)


def test_preflight_retry_cannot_use_up_remaining_rollout_budget(pilot):
    campaign, _ = pilot
    campaign.observe()
    result = campaign.state["trials"]["observe_replay"]
    result["status"] = "error"
    write_json(campaign.root / "trials/observe_replay/result.json", result)
    campaign.state["sessions_started"] = 5
    with pytest.raises(ValueError, match="including remaining rollouts"):
        campaign.observe(retry_preflight=True)


def test_transport_recovery_keeps_failed_attempt_and_identical_request(pilot):
    campaign, launches = pilot
    campaign.observe()
    def rejected(payload):
        raise RuntimeError("HTTP 400 unsupported transport")
    with pytest.raises(RuntimeError, match="HTTP 400"):
        campaign.generate(rejected)
    request = campaign.root / "model/A.request.json"
    original = comparison.file_sha(request)
    write_json(campaign.root / "provider_000/report.json", dict(requests=1, completed=1, pending=0))
    error = campaign.root / "provider_000/request_001.error.json"
    write_json(error, dict(http_status=400, provider_detail="UnsupportedParamsError: tool_choice"))
    error_digest = comparison.file_sha(error)
    record = comparison.recover_unsupported_transport(campaign.root)
    assert record["extra_attempt_allowance"] == 1
    campaign.state = comparison.read_json(campaign.root / "state.json")
    calls = []
    def native_transport(payload):
        calls.append(payload)
        return response(payload)
    campaign.generate(native_transport)
    assert len(calls) == 2 and len(launches) == 2
    assert campaign.state["transport_replayed"]
    assert comparison.file_sha(request) == original
    assert comparison.file_sha(error) == error_digest
    assert (campaign.root / "frozen_programs.json").exists()
    assert comparison.recover_unsupported_transport(campaign.root) == record


@pytest.mark.parametrize("status,detail", [(500, "UnsupportedParamsError: tool_choice"),
                                            (400, "Model generated invalid code")])
def test_transport_recovery_rejects_other_errors(pilot, status, detail):
    campaign, _ = pilot
    campaign.observe()
    write_json(campaign.root / "provider_000/report.json", dict(requests=1, completed=1, pending=0))
    write_json(campaign.root / "provider_000/request_001.error.json", dict(http_status=status, provider_detail=detail))
    with pytest.raises(ValueError, match="Only the verified"):
        comparison.recover_unsupported_transport(campaign.root)


def test_scene_state_pairing_checks_shapes_assets_and_finiteness():
    state = dict(rigid_object=dict(object=dict(root_pose=[[.1, .2, .3]])))
    assert state_difference(state, state)["matched"]
    with pytest.raises(ValueError, match="mismatch"):
        state_difference(state, dict(rigid_object=dict(object=dict(root_pose=[[.1, .2, .4]]))))
    with pytest.raises(ValueError, match="shape"):
        state_difference(state, dict(rigid_object=dict(object=dict(root_pose=[[.1, .2]]))))
    with pytest.raises(ValueError, match="assets"):
        state_difference(state, dict(rigid_object={}))
    with pytest.raises(ValueError, match="Nonfinite"):
        state_difference(state, dict(rigid_object=dict(object=dict(root_pose=[[.1, np.nan, .3]]))))


def test_restore_scene_refreshes_sensors_without_physics_steps():
    import torch
    state = dict(rigid_object=dict(object=dict(root_pose=torch.tensor([[.1, .2, .3]]))))
    calls = []
    class Scene:
        def get_state(self):
            return state
        def reset_to(self, value):
            calls.append("write")
            assert torch.is_inference_mode_enabled()
            assert encode_state(value) == encode_state(state)
        def reset(self):
            calls.append("sensor_reset")
        def update(self, dt):
            calls.append("update")
    backend = SimpleNamespace(raw=SimpleNamespace(scene=Scene(), device="cpu", sim=SimpleNamespace(
        forward=lambda: calls.append("forward"), render=lambda: calls.append("render"))),
        config=SimpleNamespace(to_dict=lambda: dict(target="kelly")), step_dt=.01)
    snapshot = dict(contract="aspire_initial_state_v1", seed=601, task=dict(target="kelly"), state=encode_state(state))
    assert restore_scene(backend, snapshot, 601)["matched"]
    assert calls == ["write", "sensor_reset", "forward", "render", "render", "render", "update"]
    with pytest.raises(ValueError, match="differs"):
        restore_scene(backend, snapshot, 602)


def test_carry_in_request_count_includes_all_attempts(tmp_path):
    write_json(tmp_path / "state.json", dict(status="completed"))
    write_json(tmp_path / "launch.json", dict(prior_requests=42))
    write_json(tmp_path / "provider_000/report.json", dict(requests=50, completed=50, pending=0))
    write_json(tmp_path / "provider_001/report.json", dict(requests=4, completed=3, pending=1))
    assert comparison.source_accounting(tmp_path)["prior_requests"] == 96
