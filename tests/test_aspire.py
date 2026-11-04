"""Contract tests with real upstream ASPIRE execution and a deterministic fake robot."""
import json
import numpy as np
import pytest
# This adapter is optional in ordinary recorder/test environments.
pytest.importorskip("gymnasium", reason="Run scripts/test_aspire.py with the Isaac Sim launcher")
pytest.importorskip("omegaconf")
pytest.importorskip("cloudpickle")
from src.aspire.config import TaskConfig, load_protocol
from src.aspire.evaluator import Measurement, TaskEvaluator
from src.aspire.geometry import mask_to_points, relative_point, rotate, topdown_quaternion
from src.aspire.environment import EpisodeStopped, SurgicalEnv
from src.aspire.execution import SurgicalExecutionEnv, validate_program
from src.aspire.control import SurgicalControlApi
from src.aspire.artifacts import Artifacts
from src.aspire.campaign import worker_environment


@pytest.mark.parametrize("obstacle", [False, True])
def test_rfdetr_api_uses_requested_class_and_rejects_overlapping_tools(monkeypatch, obstacle):
    from src.aspire.perception import RfDetrClient
    backend = FakeBackend()
    env = SurgicalEnv(backend, TaskConfig(rfdetr_url="http://localhost:8115"))
    env.reset(seed=101)
    camera = backend.observation()["cameras"]["top"]
    camera["images"]["depth"][:] = 1.
    camera["images"]["depth"][20:30, 20:30] = .99
    camera["pose_mat"] = np.diag([1., -1., -1., 1.])
    camera["pose_mat"][2, 3] = 1.
    monkeypatch.setattr(env, "get_observation", lambda: dict(cameras=dict(top=camera)))
    rows = [dict(box=[19., 19., 31., 31.], label="scissor", score=.9),
            dict(box=[25., 25., 35., 35.] if obstacle else [50., 50., 60., 60.],
                 label="kelly", score=.8)]
    monkeypatch.setattr(RfDetrClient, "detect", lambda self, rgb: rows)
    api = SurgicalControlApi(env)
    result = api.segment_instrument(allow_empty=True)
    if obstacle:
        assert result == []
        with pytest.raises(RuntimeError, match="no isolated target"):
            api.segment_instrument()
    else:
        assert len(result) == 1 and result[0]["label"] == "scissor"
        assert result[0]["mask"].sum() == 100
        assert result[0]["mask_source"] == "box_depth_foreground"
    with pytest.raises(ValueError, match="point prompts"):
        api.segment_instrument(point=(22, 22))
    with pytest.raises(ValueError, match="five trained"):
        api.segment_instrument(text="anything metallic")


def test_sam3_backend_remains_explicitly_selectable(monkeypatch):
    from src.aspire.perception import Sam3Client
    env = SurgicalEnv(FakeBackend(), TaskConfig(perception_backend="sam3", sam3_url="http://localhost:8114"))
    env.reset(seed=101)
    calls = []
    def segment(self, rgb, text, **kwargs):
        calls.append((text, kwargs))
        return []
    monkeypatch.setattr(Sam3Client, "segment", segment)
    assert SurgicalControlApi(env).segment_instrument(allow_empty=True) == []
    assert calls == [("scissor", dict(point=None, allow_empty=True))]


def test_sam3_visual_box_bypasses_target_text_mapping(monkeypatch):
    from src.aspire.perception import Sam3Client
    env = SurgicalEnv(FakeBackend(), TaskConfig(target='scalpel', perception_backend='sam3',
                     sam3_url='http://localhost:8114', sam3_target_prompt='knife'))
    env.reset(seed=101)
    calls = []
    def segment(self, rgb, text, **kwargs):
        calls.append((text, kwargs))
        return []
    monkeypatch.setattr(Sam3Client, 'segment', segment)
    SurgicalControlApi(env).segment_instrument(box=[1, 2, 10, 20], allow_empty=True)
    assert calls == [(None, dict(point=None, box=[1, 2, 10, 20], allow_empty=True))]


def test_depth_candidates_execute_and_trace_without_serializing_full_masks(monkeypatch):
    backend = FakeBackend()
    env = SurgicalEnv(backend, TaskConfig(perception_backend='sam3', sam3_url='http://localhost:8114'))
    execution = SurgicalExecutionEnv(env)
    execution.reset(seed=101)
    camera = backend.observation()['cameras']['top']
    camera['images']['depth'][:] = 1.
    camera['images']['depth'][20:25, 10:35] = .99
    camera['intrinsics'] = np.array([[200., 0, 224], [0, 200., 224], [0, 0, 1]])
    camera['pose_mat'] = np.diag([1., -1., -1., 1.])
    camera['pose_mat'][2, 3] = 1.
    monkeypatch.setattr(env, 'get_observation', lambda: dict(cameras=dict(top=camera, front=camera, wrist=camera)))
    _, _, _, _, info = execution.step("c = get_tabletop_candidates()\nprint(len(c))\n")
    assert info['sandbox_rc'] == 0
    entry = execution._apis['surgical-control'].trace.entries[-1]
    assert entry['perception_mode'] == 'depth_components'
    assert len(entry['candidates']) == 1
    assert entry['candidates'][0]['point_count'] == 125
    assert 'mask' not in entry['candidates'][0]


def test_sam3_target_mapping_preserves_candidates_and_explicit_other_prompts(monkeypatch):
    from src.aspire.perception import Sam3Client
    config = TaskConfig(target="scalpel", perception_backend="sam3", sam3_url="http://localhost:8114",
                        sam3_target_prompt="knife")
    env = SurgicalEnv(FakeBackend(), config)
    env.reset(seed=101)
    calls = []
    candidates = [dict(label="knife", score=.6), dict(label="knife", score=.57)]
    def segment(self, rgb, text, **kwargs):
        calls.append(text)
        return candidates
    monkeypatch.setattr(Sam3Client, "segment", segment)
    api = SurgicalControlApi(env)
    for prompt in (None, "scalpel", "knife", "surgical scalpel", "scalpel_type2"):
        assert api.segment_instrument(text=prompt) is candidates
    assert calls == ["knife", "knife", "knife", "surgical scalpel", "scalpel_type2"]
    assert config.to_dict()["sam3_target_prompt"] == "knife"
    assert "sam3_target_prompt" not in TaskConfig().to_dict()


@pytest.mark.parametrize("prompt,backend", [("", "sam3"), (" knife ", "sam3"), (False, "sam3"), ("knife", "rfdetr")])
def test_invalid_sam3_target_mapping_rejected(prompt, backend):
    with pytest.raises(ValueError, match="sam3_target_prompt"):
        TaskConfig(sam3_target_prompt=prompt, perception_backend=backend)


@pytest.mark.parametrize("yaw", [-2.3, .4, 2.7])
def test_scissor_shape_resolves_tip_direction_and_density_biased_center(yaw):
    from src.aspire.geometry import estimate_topdown_grasp
    # Broad handles at negative X have far more pixels than the narrow tip.
    handles = np.array([[x, y, .01] for x in np.linspace(-.07, -.03, 30)
                        for y in np.linspace(-.012, .012, 12)])
    blades = np.array([[x, y, .01] for x in np.linspace(-.03, .07, 20)
                       for y in (-.002, .002)])
    cloud = np.vstack((handles, blades))
    rotation = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    cloud[:, :2] = cloud[:, :2] @ rotation.T + [.4, -.2]
    grasp = estimate_topdown_grasp(cloud, 0., ring_handles=True)
    assert np.linalg.norm(grasp["position"][:2]-[.4, -.2]) < .003
    assert np.dot([np.cos(grasp["long_axis_yaw"]), np.sin(grasp["long_axis_yaw"])],
                  [np.cos(yaw), np.sin(yaw)]) > .999


def test_scissor_shape_rejects_invisible_handle_direction():
    from src.aspire.geometry import estimate_topdown_grasp
    points = np.array([[x, y, .01] for x in np.linspace(-.07, .07, 30) for y in (-.003, .003)])
    with pytest.raises(ValueError, match="ambiguous"):
        estimate_topdown_grasp(points, 0., ring_handles=True)


def test_verified_success_stops_further_motor_commands_without_program_error():
    env = SurgicalEnv(FakeBackend(), TaskConfig())
    env.reset(seed=1)
    env._evaluator.place_verified = True
    env._evaluator.phase = "success"
    api = SurgicalControlApi(env)
    before = env.get_observation()["robot"]
    api.goto_pose([.4, .2, .3], [1., 0., 0., 0.])
    api.close_gripper()
    api.open_gripper()
    api.wait(.5)
    assert env._sim_step_count == 0 and env.task_completed()
    np.testing.assert_array_equal(api.get_robot_state()["position"], before["position"])


def test_failed_episode_is_not_treated_as_terminal_success():
    env = SurgicalEnv(FakeBackend(), TaskConfig())
    env.reset(seed=1)
    env._evaluator.fail("target_slipped_during_transport")
    with pytest.raises(EpisodeStopped, match="target_slipped"):
        SurgicalControlApi(env).goto_pose([.4, .2, .3], [1., 0., 0., 0.])


def measurement(center=(.3, .2, .005), tcp=(.3, .2, .08), *, bottom=0., inside=False,
                error=.2, angle=90., speed=0., fingers=(.04, .04), preloaded=True):
    return Measurement(np.array(tcp), np.array([1.,0.,0.,0.]), np.array(center), bottom,
        np.array(fingers), dict(inside_slot=inside, center_error_m=error, axis_error_deg=angle,
                              bottom_m=bottom), .01, preloaded, speed)


class FakeBackend:
    step_dt = .02
    table_z_base = 0.
    def __init__(self, stuck=False):
        self.stuck = stuck
        self.closed = False
        self.reset(seed=0, options={})
    def reset(self, *, seed, options):
        self.pos = np.array([.3,.2,.2]); self.q = np.array([1.,0.,0.,0.])
        self.fingers = np.array([.04,.04],dtype=np.float32); self.seed = seed
    def robot_state(self):
        return dict(position=self.pos.copy(), quaternion_wxyz=self.q.copy(), finger_positions=self.fingers.copy())
    def observation(self):
        cameras = {name:dict(images=dict(rgb=self.rgb(name), depth=np.ones((448,448),dtype=np.float32)),
                    intrinsics=np.eye(3,dtype=np.float32), pose_mat=np.eye(4))
                   for name in ("front", "wrist", "top", "left", "right", "tray")}
        return dict(cameras=cameras, robot=self.robot_state(), proprio=np.r_[np.zeros(9),self.pos,self.q])
    def rgb(self, name):
        return np.arange(448*448*3, dtype=np.uint8).reshape(448,448,3)
    def measure(self):
        return measurement(tcp=self.pos, fingers=self.fingers)
    def constrain_pose(self, position, quaternion):
        return position
    def set_precision(self, skill):
        self.skill = skill
    def validate_action(self, action):
        assert np.isfinite(action).all()
    def advance(self, action):
        if not self.stuck:
            self.pos, self.q = action[:3].copy(), action[3:7].copy()
            self.fingers[:] = .01 if action[-1] < 0 else .04
    def tray_slot(self):
        return dict(center=[.2,-.7,.01], long_axis=[0.,1.,0.], rim_z=.03, size=[.2,.104], slot_id=1)
    def close(self):
        self.closed = True


class TranslationBackend(FakeBackend):
    """Kinematic fixture for stage/offset contracts, not grasp-physics evidence."""
    def __init__(self, target="scissor", *, missed_grasp=False, table=.0):
        self.target = target
        self.missed_grasp = missed_grasp
        self.table_z_base = table
        super().__init__()

    def reset(self, *, seed, options):
        super().reset(seed=seed, options=options)
        self.q = topdown_quaternion(.1)
        self.center = np.array([.4, .2, self.table_z_base+.006])
        self.axis = np.array([np.cos(.4), np.sin(.4), 0.])
        self.attached = False
        self.released = False
        self.anchor = None
        self.commands = []

    def constrain_pose(self, position, quaternion):
        p = np.asarray(position).copy()
        p[2] = max(p[2], self.table_z_base+.005)
        return p

    def advance(self, action):
        super().advance(action)
        self.commands.append(action.copy())
        if action[-1] < 0 and not self.attached and not self.released and not self.missed_grasp:
            assert np.linalg.norm(self.pos[:2]-self.center[:2]) < .01
            inverse = self.q.copy(); inverse[1:] *= -1
            self.anchor = rotate(inverse, self.center-self.pos)
            self.local_axis = rotate(inverse, self.axis)
            self.attached = True
        if self.attached:
            self.center = self.pos+rotate(self.q, self.anchor)
            self.axis = rotate(self.q, self.local_axis)
            if action[-1] > 0:
                self.attached, self.released = False, True
                self.center[2] = self.tray_slot()["center"][2]+.006

    def measure(self):
        slot = self.tray_slot()
        error = float(np.linalg.norm(self.center[:2]-slot["center"][:2]))
        angle = float(np.degrees(np.arccos(np.clip(self.axis @ slot["long_axis"], -1., 1.))))
        return Measurement(self.pos.copy(), self.q.copy(), self.center.copy(), self.center[2]-.006,
                           self.fingers.copy(), dict(inside_slot=error < .02, center_error_m=error,
                                                     axis_error_deg=angle, bottom_m=self.center[2]-.006),
                           slot["center"][2], True, 0.)


@pytest.mark.parametrize("target", ["scalpel", "scissor", "love_retractor", "kelly", "scalpel_type2"])
def test_translated_full_stage_program_executes_with_upstream_and_offset_placement(target, monkeypatch):
    from src.aspire.translation import render_skill, render_protocol, ROOT
    backend = TranslationBackend(target, table=.02)
    env = SurgicalEnv(backend, TaskConfig(target=target))
    executor = SurgicalExecutionEnv(env)
    executor.reset(seed=501)
    # Synthetic asymmetric cloud with broad handles at negative long-axis X.
    points = np.array([[x, y, .006] for x in np.linspace(-.07, .07, 40)
                       for y in np.linspace(-(.012 if x < -.025 else .002),
                                            (.012 if x < -.025 else .002), 8)])
    rotation = np.array([[np.cos(.4), -np.sin(.4)], [np.sin(.4), np.cos(.4)]])
    points[:, :2] = points[:, :2] @ rotation.T + [.4, .2]
    points[:, 2] += backend.table_z_base
    mask = np.ones((3, 3), dtype=bool)
    monkeypatch.setattr(SurgicalControlApi, "segment_instrument",
                        lambda self, **kwargs: [dict(mask=mask, score=.9)])
    monkeypatch.setattr(SurgicalControlApi, "mask_to_robot_points", lambda self, mask, **kwargs: points.copy())
    code = render_skill(target)
    assert (ROOT/f"examples/aspire/translated/{target}.py").read_text(encoding="utf-8") == code
    for perception in ("rfdetr", "sam3"):
        protocol, config = load_protocol(ROOT/f"configs/aspire/translated/{target}-{perception}.json")
        assert config.target == target and config.perception_backend == perception
        assert set(protocol["development_seeds"]).isdisjoint(protocol["evaluation_seeds"])
        assert json.dumps(json.loads(render_protocol(target, perception=perception))) == json.dumps(protocol)
    validate_program(code)
    _, reward, terminated, truncated, info = executor.step(code)
    assert info["sandbox_rc"] == 0, (info["stderr"], backend.measure())
    assert reward == 1. and terminated and not truncated
    assert info["feedback"]["place_verified"]
    assert np.linalg.norm(backend.center[:2]-backend.tray_slot()["center"][:2]) < 1e-6
    for stage in ("OPEN_HOVER", "LOWER_PRE", "LOWER_GRASP", "CLOSE", "LIFT_CLEAR",
                  "VERIFY_LIFT", "MOVE_TO_TARGET_DETOUR", "MOVE_TO_TARGET", "VERIFY_HOLD",
                  "LOWER_PLACE", "OPEN", "RETREAT", "SETTLE", "VERIFY_PLACE"):
        assert "STAGE_END " + target.upper() + "_" + stage in info["stdout"]


def test_translation_aborts_after_missed_lift_before_transfer(monkeypatch):
    from src.aspire.translation import render_skill
    backend = TranslationBackend(missed_grasp=True)
    env = SurgicalEnv(backend, TaskConfig())
    executor = SurgicalExecutionEnv(env)
    executor.reset(seed=501)
    mask = np.ones((3, 3), dtype=bool)
    points = np.array([[x, y, .006] for x in np.linspace(.33, .47, 40)
                       for y in (.19, .21)])
    monkeypatch.setattr(SurgicalControlApi, "segment_instrument",
                        lambda self, **kwargs: [dict(mask=mask, score=.9)])
    monkeypatch.setattr(SurgicalControlApi, "mask_to_robot_points", lambda self, mask, **kwargs: points.copy())
    monkeypatch.setattr(SurgicalControlApi, "estimate_grasp", lambda self, mask, **kwargs:
                        dict(position=[.4, .2, .006], quaternion_wxyz=topdown_quaternion(0.),
                             long_axis_yaw=0., point_count=len(points)))
    _, reward, _, _, info = executor.step(render_skill("scissor"))
    assert info["sandbox_rc"] == 1 and reward == 0.
    assert "SCISSOR_VERIFY_LIFT: Physical lift not verified" in info["stderr"]
    assert "STAGE_BEGIN SCISSOR_MOVE_TO_TARGET" not in info["stdout"]


def test_translated_skill_rejects_wrong_target_before_motion():
    from src.aspire.translation import render_skill
    backend = TranslationBackend("kelly")
    env = SurgicalEnv(backend, TaskConfig(target="kelly"))
    executor = SurgicalExecutionEnv(env)
    executor.reset(seed=501)
    before = len(backend.commands)
    _, _, _, _, info = executor.step(render_skill("scissor"))
    assert info["sandbox_rc"] == 1 and "Skill target does not match task" in info["stderr"]
    assert len(backend.commands) == before


def test_fixture_floor_query_is_motionless_and_uses_robot_and_fixture_only():
    backend = TranslationBackend(table=.02)
    env = SurgicalEnv(backend, TaskConfig())
    env.reset(seed=501)
    api = SurgicalControlApi(env)
    before = len(backend.commands)
    assert api.get_table_height() == .02
    assert api.get_tcp_floor(topdown_quaternion(0.)) == pytest.approx(.025)
    assert api.get_tcp_floor(topdown_quaternion(0.), surface="tray") == pytest.approx(.0395)
    assert len(backend.commands) == before
    assert set(api.get_task_feedback()) == {"phase", "reason", "lift_verified", "place_verified", "measured_steps", "sim_steps"}
    with pytest.raises(ValueError, match="surface must"):
        api.get_tcp_floor(topdown_quaternion(0.), surface="object")


def test_translation_rejects_ambiguous_axis_before_approach(monkeypatch):
    from src.aspire.translation import render_skill
    backend = TranslationBackend("kelly")
    env = SurgicalEnv(backend, TaskConfig(target="kelly"))
    executor = SurgicalExecutionEnv(env)
    executor.reset(seed=501)
    mask = np.ones((3, 3), dtype=bool)
    points = np.array([[x, y, .006] for x in np.linspace(.33, .47, 40)
                       for y in (.19, .21)])
    monkeypatch.setattr(SurgicalControlApi, "segment_instrument",
                        lambda self, **kwargs: [dict(mask=mask, score=.9)])
    monkeypatch.setattr(SurgicalControlApi, "mask_to_robot_points", lambda self, mask, **kwargs: points.copy())
    _, _, _, _, info = executor.step(render_skill("kelly"))
    assert info["sandbox_rc"] == 1 and "Instrument direction ambiguous" in info["stderr"]
    assert "STAGE_BEGIN KELLY_OPEN_HOVER" not in info["stdout"]


def test_translation_does_not_hide_perception_service_error(monkeypatch):
    from src.aspire.translation import render_skill
    backend = TranslationBackend()
    env = SurgicalEnv(backend, TaskConfig())
    executor = SurgicalExecutionEnv(env)
    executor.reset(seed=501)
    def unavailable(self, **kwargs):
        raise RuntimeError("perception service unavailable")
    monkeypatch.setattr(SurgicalControlApi, "segment_instrument", unavailable)
    _, _, _, _, info = executor.step(render_skill("scissor"))
    assert info["sandbox_rc"] == 1 and "SCISSOR_PERCEIVE: perception service unavailable" in info["stderr"]
    assert "STAGE_BEGIN SCISSOR_OPEN_HOVER" not in info["stdout"]


def test_backprojection_uses_metric_depth_and_optical_pose():
    mask = np.ones((3,3), dtype=bool)
    k = np.array([[2.,0.,1.],[0.,2.,1.],[0.,0.,1.]])
    transform = np.eye(4); transform[:3,3] = [.1,.2,.3]
    points = mask_to_points(mask, np.full((3,3),.5), k, transform)
    np.testing.assert_allclose(points[4], [.1,.2,.8])
    np.testing.assert_allclose(points[0], [-.15,-.05,.8])
    with pytest.raises(ValueError, match="Insufficient"):
        mask_to_points(mask, np.full((3,3),np.nan), k, transform)


def test_robot_base_round_trip_and_downward_tcp():
    q = np.array([np.sqrt(.5),0.,0.,np.sqrt(.5)])
    base = np.array([.1,-.2,.003]); point = np.array([.3,.2,.1])
    np.testing.assert_allclose(relative_point(rotate(q, point)+base,base,q), point, atol=1e-12)
    np.testing.assert_allclose(rotate(topdown_quaternion(.3), [0.,0.,1.]), [0.,0.,-1.], atol=1e-12)


@pytest.mark.parametrize("yaw", [0., .3, 1.5])
def test_grasp_fingers_close_across_measured_instrument_axis(yaw):
    closing = rotate(topdown_quaternion(yaw), [0.,1.,0.])
    axis = np.array([np.cos(yaw),np.sin(yaw),0.])
    assert abs(float(closing@axis)) < 1e-12


def test_evaluator_requires_lift_release_support_retreat():
    evaluator = TaskEvaluator(); evaluator.reset(measurement())
    # Even an aligned object already in the tray is not a verified pick/place.
    for _ in range(10):
        evaluator.update(measurement(inside=True,error=0,angle=0,bottom=.01), 1.)
    assert not evaluator.place_verified
    evaluator.update(measurement(center=(.3,.2,.06),tcp=(.3,.2,.13),bottom=.055), -1.)
    assert evaluator.lift_verified
    evaluator.update(measurement(center=(.2,-.7,.03),tcp=(.2,-.7,.10),bottom=.025), -1.)
    assert not evaluator.failed
    evaluator.update(measurement(center=(.2,-.7,.03),tcp=(.2,-.7,.10),bottom=.025), 1.)
    for _ in range(8):
        evaluator.update(measurement(center=(.2,-.7,.015),tcp=(.2,-.7,.16),bottom=.01,
                                     inside=True,error=.001,angle=2.), 1.)
    assert evaluator.place_verified and evaluator.reason == "verified_pick_place"


@pytest.mark.parametrize("change,reason", [
    ({"bottom":-.03},"target_fell_off_table"),
    ({"preloaded":False},"preloaded_instrument_displaced"),
    ({"tcp":(np.nan,0.,.1)},"nonfinite_measured_state")])
def test_evaluator_fails_on_measured_faults(change, reason):
    evaluator = TaskEvaluator(); evaluator.reset(measurement())
    evaluator.update(measurement(**change), -1.)
    assert evaluator.failed and evaluator.reason == reason


def test_hold_slip_and_failed_release():
    evaluator = TaskEvaluator(); evaluator.reset(measurement())
    evaluator.update(measurement(center=(.3,.2,.06),tcp=(.3,.2,.13),bottom=.055), -1.)
    for _ in range(2):
        evaluator.update(measurement(center=(.3,.2,.06),tcp=(.4,.2,.13),bottom=.055), -1.)
    assert evaluator.reason == "target_slipped_during_transport"
    evaluator.reset(measurement())
    evaluator.update(measurement(center=(.3,.2,.06),tcp=(.3,.2,.13),bottom=.055), -1.)
    evaluator.update(measurement(center=(.3,.2,.06),tcp=(.3,.2,.13),bottom=.055), 1.)
    evaluator.update(measurement(center=(.3,.2,.12),tcp=(.3,.2,.19),bottom=.115), 1.)
    assert evaluator.reason == "target_still_attached_after_open"


def test_real_upstream_execution_bindings_reset_and_tracebacks():
    low = SurgicalEnv(FakeBackend(), TaskConfig())
    execution = SurgicalExecutionEnv(low)
    obs, _ = execution.reset(seed=12)
    assert "goto_pose" in json.dumps(obs["full_prompt"])
    assert not ({"target_pose","grid","spawn","slot_measurement"} & set(obs))
    assert set(obs["cameras"]["top"]) == {"images","intrinsics","pose_mat"}
    _, reward, _, _, info = execution.step("marker = 7\nclose_gripper()\nopen_gripper()\nwait(.04)\nprint(marker)")
    assert reward == 0 and info["sandbox_rc"] == 0 and "7" in info["stdout"]
    assert low._sim_step_count > 0
    _, _, _, _, info = execution.step("raise RuntimeError('intentional failure')")
    assert info["sandbox_rc"] == 1 and "intentional failure" in info["stderr"]
    execution.reset(seed=13)
    _, _, _, _, info = execution.step("print(marker)")
    assert info["sandbox_rc"] == 1 and "NameError" in info["stderr"]
    execution.close(); assert low._backend.closed


def test_motor_convergence_and_timeout_use_measured_state():
    env = SurgicalEnv(FakeBackend(), TaskConfig())
    env.reset(seed=1); api = SurgicalControlApi(env)
    state = api.goto_pose([.3,.2,.3], [1.,0.,0.,0.], duration_s=.1, timeout_s=.4)
    np.testing.assert_allclose(state["position"], [.3,.2,.3])
    env = SurgicalEnv(FakeBackend(stuck=True), TaskConfig())
    env.reset(seed=1); api = SurgicalControlApi(env)
    with pytest.raises(RuntimeError, match="pose_timeout"):
        api.goto_pose([.3,.2,.3], [1.,0.,0.,0.], duration_s=.1, timeout_s=.4)


def test_budget_and_invalid_commands():
    env = SurgicalEnv(FakeBackend(), TaskConfig(max_steps=2))
    env.reset(seed=1); api = SurgicalControlApi(env)
    with pytest.raises(ValueError):
        api.goto_pose([0.,0.,0.], [0.,0.,0.,0.])
    with pytest.raises(ValueError):
        env.step([.3,.2,.2,1.,0.,0.,0.,0.])
    with pytest.raises(EpisodeStopped, match="budget"):
        api.wait(.2)
    assert env._sim_step_count == 2 and env.compute_reward() == 0
    env.reset(seed=2); assert env._sim_step_count == 0


def test_gym_step_reports_physical_failure_as_terminal():
    class DroppingBackend(FakeBackend):
        def advance(self, action):
            super().advance(action)
            self.dropped = True
        def measure(self):
            return measurement(bottom=-.03) if getattr(self,"dropped",False) else super().measure()
    env = SurgicalEnv(DroppingBackend(), TaskConfig())
    env.reset(seed=1)
    _, reward, terminal, truncated, info = env.step([.3,.2,.2,1.,0.,0.,0.,1.])
    assert terminal and not truncated and reward == 0
    assert info["reason"] == "target_fell_off_table"


@pytest.mark.parametrize("code", ["env.scene", "APIS", "import os", "open('a')", "get_robot_state.__globals__", "from numpy import random as __private", "np.load('a')", "from numpy import save as writer"])
def test_program_boundary(code):
    with pytest.raises(ValueError):
        validate_program(code)


def test_seed_protocol_rejects_overlap(tmp_path):
    protocol = dict(contract="surgical_aspire_v1", development_seeds=[1], evaluation_seeds=[1], task={})
    filename = tmp_path/"config.json"; filename.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="disjoint"):
        load_protocol(filename)


def test_reset_without_seed_passes_a_concrete_seed_to_backend():
    env = SurgicalEnv(FakeBackend(), TaskConfig())
    _, info = env.reset()
    assert type(info["seed"]) is int and env._backend.seed == info["seed"]


def test_sensor_observation_matches_declared_gym_space():
    env = SurgicalEnv(FakeBackend(), TaskConfig())
    observation, _ = env.reset(seed=1)
    assert env.observation_space.contains(observation)


def test_artifacts_keep_sensors_and_actions(tmp_path):
    sink = Artifacts(tmp_path)
    env = SurgicalEnv(FakeBackend(), TaskConfig(video_stride=2), artifact_sink=sink)
    env.reset(seed=1); SurgicalControlApi(env).wait(.04)
    sink.observation("final", env.get_observation()); sink.close()
    assert (tmp_path/"initial/top.png").exists() and (tmp_path/"final/tray_depth.npy").exists()
    assert len((tmp_path/"actions.jsonl").read_text().splitlines()) == 2
    calibration = json.loads((tmp_path/"initial/observation.json").read_text())
    assert "target_center_w" not in calibration and "pose_mat" in calibration["cameras"]["top"]


def test_provider_credentials_stay_in_parent():
    assert worker_environment({"OPENAI_API_KEY":"sensitive", "AWS_SECRET_ACCESS_KEY":"sensitive",
                               "GITHUB_TOKEN":"sensitive", "PATH":"path"}) == {"PATH":"path", "PYTHONUNBUFFERED":"1"}


@pytest.mark.parametrize("development_only", [False, True])
def test_refinement_freezes_program_before_held_out_trials(tmp_path, monkeypatch, development_only):
    from src.aspire import campaign
    monkeypatch.setenv("ASPIRE_TEST_KEY", "fake-test-credential")
    protocol = dict(contract="surgical_aspire_v1", development_seeds=[101,102], evaluation_seeds=[1,2], task={})
    config = tmp_path/"config.json"; config.write_text(json.dumps(protocol))
    source = tmp_path/"program.py"; source.write_text("print('initial')\n")
    seen = []
    def fake_trial(launcher, code, config, seed, out, **kwargs):
        out.mkdir()
        program = code.read_text()
        seen.append((seed, program))
        result = dict(seed=seed, success="refined" in program, execution_ok=True, status="completed")
        (out/"result.json").write_text(json.dumps(result))
        return result
    monkeypatch.setattr(campaign,"run_trial",fake_trial)
    monkeypatch.setattr(campaign,"refine_program",lambda *a,**k: "print('refined')\n")
    report = campaign.refine("unused",source,config,tmp_path/"campaign",rounds=2,model="unused",
                             base_url="unused",api_key_env="ASPIRE_TEST_KEY",
                             development_only=development_only)
    assert [seed for seed,_ in seen] == [101,102,101,102] + ([] if development_only else [1,2])
    assert (tmp_path/"campaign/evaluation").exists() != development_only
    frozen = (tmp_path/"campaign/frozen_program.py").read_text()
    assert "refined" in frozen and all(code==frozen for seed,code in seen if seed < 100)
    assert report["success_count"] == report["trial_count"] == 2


def test_local_provider_credential_is_selective_and_worker_isolated(tmp_path, monkeypatch):
    from src.aspire.provider import load_credential
    monkeypatch.delenv("ASPIRE_TEST_API_KEY", raising=False)
    monkeypatch.delenv("ASPIRE_UNUSED_SECRET", raising=False)
    credential = tmp_path/".env"
    credential.write_text('ASPIRE_UNUSED_SECRET=unused\nexport ASPIRE_TEST_API_KEY="test-only-value" # comment\n')
    assert load_credential(credential, "ASPIRE_TEST_API_KEY")
    import os
    assert os.environ["ASPIRE_TEST_API_KEY"] == "test-only-value"
    assert "ASPIRE_UNUSED_SECRET" not in os.environ
    assert "ASPIRE_TEST_API_KEY" not in worker_environment()
    credential.write_text('ASPIRE_TEST_API_KEY=replacement\n')
    assert load_credential(credential, "ASPIRE_TEST_API_KEY")
    assert os.environ["ASPIRE_TEST_API_KEY"] == "test-only-value"
    monkeypatch.delenv("ASPIRE_TEST_API_KEY")
    credential.write_text('ASPIRE_TEST_API_KEY=unquoted # comment\n')
    assert load_credential(credential, "ASPIRE_TEST_API_KEY")
    assert os.environ["ASPIRE_TEST_API_KEY"] == "unquoted"


@pytest.mark.parametrize("content,finish,accepted", [
    ("print('candidate')", "stop", True),
    ("print('candidate')", "length", False),
    (None, "stop", False),
])
def test_provider_completion_contract(tmp_path, monkeypatch, content, finish, accepted):
    from src.aspire import campaign
    monkeypatch.setenv("ASPIRE_TEST_API_KEY", "test-credential")
    trial = tmp_path/"trial"
    trial.mkdir()
    (trial/"prompt.txt").write_text("Public sensor API")
    (trial/"result.json").write_text(json.dumps(dict(seed=301, success=False,
        status="completed", feedback={"reason":"not_lifted"}, private_pose=[1,2,3])))
    (trial/"initial").mkdir()
    (trial/"initial/top.png").write_bytes(b"synthetic-image")
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(dict(model="test-model", usage={"total_tokens":123},
                choices=[dict(finish_reason=finish, message={"content":content})])).encode()
    def request(req, timeout):
        calls.append(req)
        return Response()
    monkeypatch.setattr(campaign.urllib.request, "urlopen", request)
    kwargs = dict(usage_path=tmp_path/"usage.json", reasoning_effort="low")
    if accepted:
        assert campaign.refine_program("test-model", "https://example.test/v1", "ASPIRE_TEST_API_KEY",
            "print('starting')", [trial], **kwargs) == "print('candidate')\n"
    else:
        with pytest.raises(RuntimeError):
            campaign.refine_program("test-model", "https://example.test/v1", "ASPIRE_TEST_API_KEY",
                "print('starting')", [trial], **kwargs)
    payload = json.loads(calls[0].data)
    assert calls[0].full_url == "https://example.test/v1/chat/completions"
    assert payload["max_tokens"] == 128000
    assert payload["reasoning_effort"] == "low"
    assert payload["messages"][0]["content"][-1]["type"] == "image_url"
    assert "private_pose" not in json.dumps(payload)
    usage = (tmp_path/"usage.json").read_text()
    assert "test-credential" not in usage and json.loads(usage)["usage"]["total_tokens"] == 123


def test_worker_startup_failure_remains_a_trial(tmp_path, monkeypatch):
    from src.aspire import campaign
    class Crashed:
        def __init__(self,*args,**kwargs):
            pass
        def wait(self,timeout):
            return 9
    monkeypatch.setattr(campaign.subprocess,"Popen",Crashed)
    result = campaign.run_trial("python.exe",tmp_path/"program.py",tmp_path/"config.json",101,tmp_path/"trial")
    assert result["status"] == "worker_crashed" and not result["success"]
    assert json.loads((tmp_path/"trial/result.json").read_text())["worker_returncode"] == 9
    assert (tmp_path/"trial/worker.log").exists()


def test_validation_partition_cannot_overlap_development_or_final(tmp_path):
    protocol = dict(contract="surgical_aspire_v1", development_seeds=[501],
                    validation_seeds=[551], evaluation_seeds=[601], task={})
    config = tmp_path/"config.json"
    config.write_text(json.dumps(protocol))
    assert load_protocol(config)[0]["validation_seeds"] == [551]
    for invalid in ([501], [601], [], [551,551]):
        protocol["validation_seeds"] = invalid
        config.write_text(json.dumps(protocol))
        with pytest.raises(ValueError):
            load_protocol(config)


def test_validation_selects_candidate_without_leaking_into_revision_or_final(tmp_path, monkeypatch):
    from src.aspire import campaign
    monkeypatch.setenv("ASPIRE_TEST_KEY", "fake-test-credential")
    protocol = dict(contract="surgical_aspire_v1", development_seeds=[501],
                    validation_seeds=[551], evaluation_seeds=[601], task={})
    config = tmp_path/"config.json"; config.write_text(json.dumps(protocol))
    code = tmp_path/"start.py"; code.write_text("print('initial')\n")
    seen, requests = [], []
    def trial(launcher, source, config, seed, out, **kwargs):
        out.mkdir()
        program = source.read_text()
        seen.append((seed, program))
        # Revision improves development but overfits: validation selects initial.
        success = (seed == 501 and 'revision' in program) or (seed == 551 and 'initial' in program)
        result = dict(seed=seed, success=success, execution_ok=True, status='completed')
        (out/'result.json').write_text(json.dumps(result))
        return result
    def revision(*args, **kwargs):
        requests.append(args[4])
        return "print('revision')\n"
    monkeypatch.setattr(campaign, 'run_trial', trial)
    monkeypatch.setattr(campaign, 'refine_program', revision)
    report = campaign.refine('unused', code, config, tmp_path/'campaign', rounds=2,
        model='unused', base_url='unused', api_key_env='ASPIRE_TEST_KEY', development_only=True)
    assert [seed for seed, _ in seen] == [501,551,501,551]
    assert report['split'] == 'validation' and report['success_count'] == 1
    assert "initial" in (tmp_path/'campaign/frozen_program.py').read_text()
    assert len(requests) == 1 and len(requests[0]) == 1
    assert requests[0][0].name == 'round_0_seed_501'


def test_refinement_images_include_later_failed_trial_and_stage_context(tmp_path, monkeypatch):
    from src.aspire import campaign
    monkeypatch.setenv('ASPIRE_TEST_KEY', 'fake-test-credential')
    trials = []
    for seed, success in ((501, True), (502, False)):
        trial = tmp_path/f'seed_{seed}'; trial.mkdir()
        (trial/'prompt.txt').write_text('Public API')
        (trial/'result.json').write_text(json.dumps(dict(seed=seed, success=success,
            status='completed' if success else 'program_error',
            stdout='STAGE_BEGIN SCISSOR_LIFT_CLEAR', feedback=dict(reason='slip'),
            private_geometry='must_not_leak')))
        (trial/'initial').mkdir(); (trial/'initial/top.png').write_bytes(b'image')
        (trial/'frames').mkdir(); (trial/'frames/000040_wrist.jpg').write_bytes(b'frame')
        trials.append(trial)
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps(dict(choices=[dict(finish_reason='stop',
                message=dict(content="print('candidate')"))])).encode()
    def request(req, timeout):
        requests.append(json.loads(req.data))
        return Response()
    monkeypatch.setattr(campaign.urllib.request, 'urlopen', request)
    campaign.refine_program('unused', 'https://example.test/v1', 'ASPIRE_TEST_KEY',
        "print('initial')", trials, usage_path=tmp_path/'usage.json')
    payload = json.dumps(requests[0])
    assert 'Development seed 502' in payload and 'Development seed 501' in payload
    assert payload.index('Development seed 502') < payload.index('Development seed 501')
    assert '000040_wrist.jpg' in payload and 'SCISSOR_LIFT_CLEAR' in payload
    assert 'must_not_leak' not in payload


def test_compatibility_wrappers_match_original_hashes():
    from src.aspire.assets import compatible_assets
    assert len(compatible_assets()) == 3


def test_population_search_budget_counts_initial_separately():
    from src.aspire.search import search_plan
    from src.aspire.bootstrap import ROOT
    from src.aspire.translation import render_search_protocol
    for target in ("scissor", "scalpel", "kelly", "love_retractor", "scalpel_type2"):
        for perception in ("sam3", "rfdetr"):
            config = ROOT/f"configs/aspire/search/{target}-{perception}.json"
            assert config.read_text(encoding="utf-8") == render_search_protocol(target, perception=perception)
            plan = search_plan(config, candidates=8, iterations=5, development_only=False)
            assert plan["max_total_programs"] == 41
            assert plan["max_provider_requests"] == 40
            assert plan["max_development_trials"] == 246
            assert plan["max_validation_trials"] == 164
            assert plan["max_total_trials"] == 420 and plan["max_worker_wait_hours"] == 70


def install_search_fixture(tmp_path, monkeypatch, *, all_success=False, infrastructure_failure=False):
    from src.aspire import campaign
    from src.aspire.search import search
    protocol = dict(contract="surgical_aspire_v1", development_seeds=[501,502],
                    validation_seeds=[551,552], evaluation_seeds=[601], task={})
    config = tmp_path/"config.json"; config.write_text(json.dumps(protocol))
    code = tmp_path/"start.py"; code.write_text("print('initial')\n")
    events, contexts, requests = [], [], []
    def fake_trial(launcher, source, config, seed, out, **kwargs):
        import hashlib
        out.mkdir()
        text = source.read_text()
        index = 0 if 'initial' in text else int(text.split('candidate_')[1].split("'")[0])
        events.append(('trial', seed, index))
        success = (index > 0 and all_success) or (seed == 501 and index > 0) or (seed == 551 and index == 40)
        failed_reset = infrastructure_failure and seed == 502
        result = dict(seed=seed, success=success and not failed_reset,
            execution_ok=not failed_reset, status='error' if failed_reset else 'completed',
            program_sha256=hashlib.sha256(text.encode()).hexdigest(),
            feedback=dict(reason='VALIDATION_ONLY' if seed in (551,552) else 'development_failure'),
            private_geometry='private_pose_must_not_leak')
        (out/'result.json').write_text(json.dumps(result))
        (out/'contract.json').write_text(config.read_text())
        if not failed_reset:
            (out/'prompt.txt').write_text('Public sensor API')
        return result
    def fake_proposal(*args, **kwargs):
        index = len(requests)+1
        events.append(('generate', index))
        requests.append(args[4])
        contexts.append(kwargs['repair_context'])
        return f"print('candidate_{index}')\n"
    monkeypatch.setattr(campaign, 'run_trial', fake_trial)
    monkeypatch.setattr(campaign, 'refine_program', fake_proposal)
    def run(iterations=5, **kwargs):
        out = kwargs.pop('out', tmp_path/'search')
        return search('unused', code, config, out, candidates=8, iterations=iterations,
            model='synthetic-opus', base_url='https://example.test/v1', api_key_env='TEST_KEY', **kwargs)
    return run, events, contexts, requests


def test_resume_baseline_preserves_request_budget_and_skips_old_trials(tmp_path, monkeypatch):
    from src.aspire import campaign
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch)
    original = campaign.refine_program
    def timeout(*args, **kwargs):
        raise TimeoutError('synthetic provider timeout')
    monkeypatch.setattr(campaign, 'refine_program', timeout)
    stopped = run(iterations=3)
    assert stopped['status'] == 'stopped_proposal_error'
    assert len(events) == 4
    monkeypatch.setattr(campaign, 'refine_program', original)
    report = run(iterations=3, resume_baseline=tmp_path/'search', out=tmp_path/'resumed', provider_timeout=900)
    assert report['status'] == 'search_completed'
    assert report['completed_revision_rounds'] == 2 and report['provider_requests'] == 17
    assert len(requests) == 16 and len(events) == 4+16+16*4
    assert report['attempted_trial_count'] == 4+16*4
    assert report['stop_reason'] == 'insufficient_request_budget_for_full_population'
    assert all(len(row['candidates']) == 8 for row in report['history'])
    assert (tmp_path/'search/report.json').read_text().find('stopped_proposal_error') >= 0
    assert not (tmp_path/'resumed/initial').exists()
    assert all(all(path.parent == tmp_path/'search/initial' for path in evidence) for evidence in requests[:8])
    assert 'VALIDATION_ONLY' not in json.dumps(contexts)
    assert 'private_pose_must_not_leak' not in json.dumps(contexts)


@pytest.mark.parametrize('tamper', ['program', 'evidence'])
def test_resume_rejects_changed_baseline_before_requests(tmp_path, monkeypatch, tamper):
    from src.aspire import campaign
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch)
    def timeout(*args, **kwargs):
        raise TimeoutError('synthetic provider timeout')
    monkeypatch.setattr(campaign, 'refine_program', timeout)
    run(iterations=3)
    if tamper == 'program':
        (tmp_path/'search/initial/program.py').write_text("print('changed')\n")
    else:
        path = tmp_path/'search/initial/dev_seed_501/result.json'
        data = json.loads(path.read_text()); data['success'] = True
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='differs'):
        run(iterations=3, resume_baseline=tmp_path/'search', out=tmp_path/'resumed')
    assert not (tmp_path/'resumed').exists()
    assert not requests and len(events) == 4


def test_three_round_budget_and_population_stop_at_requested_cap(tmp_path, monkeypatch):
    from src.aspire.search import search_plan
    from src.aspire.bootstrap import ROOT
    plan = search_plan(ROOT/'configs/aspire/search/scissor-sam3.json')
    assert plan['max_revision_rounds'] == 3 and plan['max_provider_requests'] == 24
    assert plan['max_total_programs'] == 25 and plan['max_total_trials'] == 250
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch)
    report = run(iterations=3)
    assert report['status'] == 'search_completed' and report['completed_revision_rounds'] == 3
    assert report['provider_requests'] == 24 and len(report['programs']) == 25
    assert report['attempted_trial_count'] == 100 and not report['evaluation_run']


@pytest.mark.parametrize('name,invalid', [
    ('solver_position_iterations', 0), ('solver_position_iterations', 65),
    ('solver_position_iterations', True), ('solver_velocity_iterations', 33),
    ('solver_velocity_iterations', 1.5),
])
def test_physics_solver_audit_is_opt_in_and_bounded(name, invalid):
    assert TaskConfig().solver_position_iterations is None
    assert TaskConfig().solver_velocity_iterations is None
    assert TaskConfig(solver_position_iterations=32, solver_velocity_iterations=8).solver_velocity_iterations == 8
    with pytest.raises(ValueError):
        TaskConfig(**{name:invalid})


def test_population_search_runs_eight_by_five_and_freezes_before_final(tmp_path, monkeypatch):
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch)
    report = run(development_only=False)
    assert report['status'] == 'search_completed'
    assert report['completed_revision_rounds'] == 5 and report['provider_requests'] == 40
    assert report['attempted_trial_count'] == 41*4+1
    assert len(report['programs']) == 41 and len(report['history']) == 5
    assert all(len(h['candidates']) == 8 for h in report['history'])
    # Each generation population is complete before any of its rollouts.
    for start in range(1, 41, 8):
        offset = events.index(('generate', start))
        assert events[offset:offset+8] == [('generate', i) for i in range(start, start+8)]
    assert events[-1] == ('trial', 601, 40)
    frozen = (tmp_path/'search/frozen_program.py').read_text()
    assert frozen == "print('candidate_40')\n"
    assert report['program_sha256'] == report['evaluation_report']['program_sha256']
    assert report['selected_program_id'] == 'round_05_candidate_08'
    assert 'VALIDATION_ONLY' not in json.dumps(contexts)
    assert 'private_pose_must_not_leak' not in json.dumps(contexts)
    assert all(all(p.name.startswith('dev_seed_') for p in request) for request in requests)
    assert contexts[8]['parent_id'] == 'round_01_candidate_01'
    assert len(contexts[8]['top_development_programs']) == 3


def test_population_search_stops_before_model_calls_when_reset_fails(tmp_path, monkeypatch):
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch, infrastructure_failure=True)
    report = run()
    assert report['status'] == 'stopped_infrastructure'
    assert report['provider_requests'] == 0 and report['attempted_trial_count'] == 2
    assert len(report['programs'][0]['results']) == 2
    assert not requests and not (tmp_path/'search/evaluation').exists()
    assert [event[1] for event in events] == [501,502]


def test_population_search_finishes_whole_round_before_success_stop(tmp_path, monkeypatch):
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch, all_success=True)
    report = run(development_only=False)
    assert report['completed_revision_rounds'] == 1 and report['provider_requests'] == 8
    assert len(report['history'][0]['candidates']) == 8 and len(report['programs']) == 9
    assert report['stop_reason'] == 'all_development_and_validation_cases_solved'
    assert report['attempted_trial_count'] == 9*4+1
    assert events[-1] == ('trial', 601, 1)


@pytest.mark.parametrize('proposal,status', [
    ("print('initial')\n", 'stopped_duplicate_proposal'),
    ("open('private_file')\n", 'stopped_proposal_error'),
])
def test_rejected_population_proposal_is_retained_without_execution(tmp_path, monkeypatch, proposal, status):
    from src.aspire import campaign
    run, events, contexts, requests = install_search_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(campaign, 'refine_program', lambda *args, **kwargs: proposal)
    report = run()
    assert report['status'] == status and report['provider_requests'] == 1
    assert report['attempted_trial_count'] == 4 and len(events) == 4
    assert report['completed_revision_rounds'] == 0
    assert report['programs'][-1]['round'] == 1
    assert (tmp_path/'search/frozen_program.py').read_text() == "print('initial')\n"


@pytest.mark.parametrize('supplied_program', [False, True])
def test_native_upstream_ensemble_extracts_code_and_repairs_syntax(tmp_path, monkeypatch, supplied_program):
    import threading
    from types import SimpleNamespace
    from src.aspire.native import NativeSurgicalExecutionEnv, native_trial_config, upstream_regeneration_prompt
    from aspire.sim.cap.llm import client
    from aspire.sim.cap.envs.trial import _run_single_trial
    requests, lock = [], threading.Lock()
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return dict(choices=[dict(message=dict(content=self.content))])
    def post(url, headers, data, timeout):
        payload = json.loads(data)
        with lock:
            requests.append(payload)
        assert timeout == 1800
        synthesis = str(payload['messages'][0]['content']).startswith('You are synthesizing')
        multi_turn = 'REGENERATE' in str(payload['messages'])
        response = Response()
        if synthesis and not multi_turn:
            response.content = 'Explanation — outside code.\n```python\nthis is invalid python!\n```'
        elif multi_turn:
            response.content = "REGENERATE\n```python\nprint('native repair')\n```"
        else:
            response.content = "Analysis — outside code.\n```python\nprint('proposal')\n```"
        return response
    monkeypatch.setattr(client.requests, 'post', post)
    args = SimpleNamespace(model='synthetic-native', server_url='https://example.test/v1/chat/completions',
        api_key=None, temperature=1., max_tokens=128000, reasoning_effort='medium',
        request_timeout_s=1800., ensemble_size=8, debug=False,
        visual_differencing_model='synthetic-native', visual_differencing_model_server_url='unused',
        visual_differencing_model_api_key=None, use_legacy_multi_turn_decision_prompt=False)
    executor = NativeSurgicalExecutionEnv(SurgicalEnv(FakeBackend(), TaskConfig()), remaining_requests=lambda: 22)
    config = native_trial_config(tmp_path, revisions=1)
    if supplied_program:
        executor.oracle_code = "raise RuntimeError('supplied program failure')"
        config['use_oracle_code'] = True
    summary = _run_single_trial(executor, 501, args, config, upstream_regeneration_prompt())
    assert len(requests) == (9 if supplied_program else 18) and executor.execution_turns == 2
    assert summary.num_regenerations == 1 and summary.sandbox_rc == 0
    assert summary.reward == 0 and not summary.task_completed
    assert ('supplied program failure' if supplied_program else 'SyntaxError') in json.dumps(requests)
    assert (tmp_path/'all_responses.json').exists()
    assert any(('supplied program failure' if supplied_program else 'Explanation') in path.read_text()
               for path in tmp_path.rglob('raw_response.sh'))
    assert all(request['max_tokens'] == 128000 for request in requests)


def test_native_budget_stops_before_partial_ensemble():
    from src.aspire.native import NativeSurgicalExecutionEnv
    executor = NativeSurgicalExecutionEnv(SurgicalEnv(FakeBackend(), TaskConfig()),
        remaining_requests=lambda: 8, generation_requests=9)
    executor.reset(seed=501)
    _, reward, _, truncated, info = executor.step("print('no placement')")
    assert info['sandbox_rc'] == 0 and reward == 0
    assert truncated and executor.budget_stopped


def test_native_reset_consumes_upstream_trial_metadata_only(monkeypatch):
    from src.aspire.native import NativeSurgicalExecutionEnv
    backend = FakeBackend()
    original = backend.reset
    calls = []
    def reset(*, seed, options):
        assert not options
        calls.append(seed)
        original(seed=seed, options=options)
    monkeypatch.setattr(backend, 'reset', reset)
    executor = NativeSurgicalExecutionEnv(SurgicalEnv(backend, TaskConfig()))
    executor.reset(seed=501, options={'trial':501})
    assert calls == [501]
    with pytest.raises(ValueError):
        executor.reset(seed=501, options={'trial':502})
    with pytest.raises(ValueError):
        executor.reset(seed=501, options={'target_cell':0})
    assert calls == [501]


def test_native_export_uses_final_artifact_instead_of_initial_snapshot(tmp_path):
    from src.aspire.native import last_executed_source
    (tmp_path/'all_responses.json').write_text(json.dumps([dict(code_blocks=["print('initial')"])]))
    final = tmp_path/'trial_final'; final.mkdir()
    (final/'all_responses.json').write_text(json.dumps([
        dict(code_blocks=["print('initial')"]),
        dict(code_blocks=["print('repaired')"]), dict(decision='finish')]))
    assert last_executed_source(final/'code.py') == "print('repaired')"


def test_native_relay_saves_raw_output_and_bounds_external_requests(tmp_path, monkeypatch):
    import urllib.request
    import urllib.error
    from src.aspire.relay import ProviderRelay
    original = urllib.request.urlopen
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps(dict(choices=[dict(finish_reason='stop', message=dict(content='raw — response'))],
                usage=dict(total_tokens=42))).encode()
    def open_request(request, **kwargs):
        if isinstance(request, urllib.request.Request) and request.full_url.startswith('https://example.test'):
            calls.append(request)
            return Response()
        return original(request, **kwargs)
    monkeypatch.setattr(urllib.request, 'urlopen', open_request)
    with ProviderRelay(tmp_path/'provider', base_url='https://example.test/v1', model='synthetic',
            credential='fake-test-secret', request_budget=1, prior_requests=2) as relay:
        def request():
            return urllib.request.Request(relay.url+'/chat/completions',
                data=json.dumps(dict(model='synthetic', messages=[dict(role='user', content='development')], max_tokens=1)).encode(),
                headers={'Content-Type':'application/json'})
        with original(request(), timeout=5) as response:
            assert json.load(response)['choices'][0]['message']['content'] == 'raw — response'
        with pytest.raises(urllib.error.HTTPError) as blocked:
            original(request(), timeout=5)
        assert blocked.value.code == 400
    assert len(calls) == 1
    assert calls[0].headers['Authorization'] == 'Bearer fake-test-secret'
    assert json.loads(calls[0].data)['max_tokens'] == 128000
    assert (tmp_path/'provider/request_001.response.json').exists()
    assert 'fake-test-secret' not in ''.join(path.read_text() for path in (tmp_path/'provider').glob('*.json'))
    assert json.loads((tmp_path/'provider/report.json').read_text())['total_requests'] == 3


def test_native_upstream_prompt_templates_are_unchanged():
    import ast
    import subprocess
    from src.aspire.bootstrap import UPSTREAM
    relative = 'aspire/sim/cap/llm/client.py'
    original = subprocess.check_output(['git', '-C', str(UPSTREAM), 'show', f'HEAD:{relative}'], text=True)
    current = (UPSTREAM/relative).read_text(encoding='utf-8')
    def prompts(source):
        return [ast.dump(node.value) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                target.id in ('synthesis_system_prompt', 'synthesis_user_prompt') for target in node.targets)]
    assert prompts(original) == prompts(current)
    for relative in ('aspire/sim/cap/utils/launch_utils.py',
                     'aspire/sim/env_configs/robosuite/cube_lifting_multimodel_aspire_traced.yaml'):
        original = subprocess.check_output(['git', '-C', str(UPSTREAM), 'show', f'HEAD:{relative}'])
        assert original.replace(b'\r\n', b'\n') == (UPSTREAM/relative).read_bytes().replace(b'\r\n', b'\n')
