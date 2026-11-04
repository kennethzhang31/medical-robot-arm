"""Exercise the complete workflow with fake model/physics, real protocol logic."""
import json
from pathlib import Path
import pytest
from PIL import Image
from src.aspire.artifacts import write_json
from src.aspire.bootstrap import ROOT
from src.aspire.full import FullCampaign, SkillRepository, digest, validate_sensor_program


def test_full_practice_search_skills_reuse_and_frozen_evaluation(tmp_path):
    calls, trials, retrievals = [], [], []
    def model(payload):
        calls.append(payload)
        if not payload.get('tools'):
            return dict(choices=[dict(finish_reason='stop', message=dict(content='Observed movement; completion is uncertain.'))])
        context = json.loads(payload['messages'][-1]['content'][0]['text'])
        retrievals.append(context['learned_skills'])
        evidence = context['evidence']
        assert all(row['seed'] in range(101, 126) for row in evidence) if context['expected_programs'] else True
        assert 'PRIVATE_GEOMETRY' not in json.dumps(payload)
        count = context['expected_programs']
        value = dict(analysis='Tested reusable diagnosis',
            skills=[dict(markdown='Inspect the observed tool motion before transport.',
                         evidence_ids=[evidence[0]['evidence_id']])],
            programs=[dict(name=f'p{i}', parent='current', hypothesis=f'Structural hypothesis {i}',
                           code=f'print("candidate {len(calls)} {i}")\n') for i in range(count)])
        return dict(choices=[dict(finish_reason='tool_calls', message=dict(tool_calls=[dict(
            id='call_test', type='function', function=dict(name='submit_practice', arguments=json.dumps(value)))]))])

    def simulator(launcher, source, config, seed, out, **kwargs):
        out = Path(out)
        trials.append((str(out), seed, Path(source).read_text()))
        out.mkdir(parents=True)
        for stage in ('initial', 'final'):
            (out/stage).mkdir()
            for camera in ('top', 'wrist'):
                Image.new('RGB', (8, 8)).save(out/stage/f'{camera}.png')
        row = dict(seed=seed, status='completed', execution_ok=True,
            success=seed%2 == 0, program_sha256=digest(Path(source).read_text()),
            stdout='sensor information', stderr='', reset_diagnostics='PRIVATE_GEOMETRY')
        write_json(out/'result.json', row)
        write_json(out/'trace.json', [dict(function='get_robot_state', result=dict(position=[0, 0, 1]))])
        return row

    campaign = FullCampaign(tmp_path/'run', ROOT/'configs/aspire/full-scissor-sam3.json',
        relay_url='http://unused', model='opus', launcher='unused', trial_runner=simulator, model_transport=model, shared_directory=tmp_path/'shared')
    campaign.run(smoke_only=True)
    assert campaign.state['phase'] == 'exploration_smoke_complete'
    assert len(trials) == 2 and len(calls) == 1
    campaign.run(pause_after_round=1)
    assert campaign.state['status'] == 'paused'
    assert campaign.state['completed_round'] == 1 and campaign.state['next_round'] == 2
    assert len(trials) == 556 and len(campaign.state['cohorts']) == 22
    assert all(seed >= 101 for _, seed, _ in trials)
    assert not (campaign.root/'iter_02_summary.json').exists()
    assert not (campaign.root/'selection.json').exists()
    assert not (campaign.root/'frozen_program.py').exists()
    assert campaign.plan['T'] == 3
    before = len(calls), len(trials)
    campaign = FullCampaign(campaign.root, campaign.config, relay_url='http://unused', model='opus',
        launcher='unused', trial_runner=simulator, model_transport=model, shared_directory=tmp_path/'shared')
    campaign.run(pause_after_round=1)
    assert before == (len(calls), len(trials))
    campaign.run()
    assert campaign.state['status'] == 'completed'
    assert len(trials) == 856
    assert len(campaign.state['cohorts']) == 6+24+1
    assert len(calls) <= 40
    assert any(item['context']['notes'] and item['context']['programs'] for item in retrievals)
    assert len(campaign.library.read()['notes']) == 13
    final = campaign.state['cohorts']['heldout']
    assert final['success_count'] == 50 and len(final['rows']) == 100
    first_heldout = next(i for i, (_, seed, _) in enumerate(trials) if seed <= 100)
    assert all(seed <= 100 for _, seed, _ in trials[first_heldout:])
    assert {code for _, seed, code in trials if seed <= 100} == {final['code']}
    frozen = json.loads((campaign.root/'frozen_skills.json').read_text())
    assert frozen['sha256'] == campaign.library.context()['sha256']
    before = len(calls), len(trials)
    campaign.run()
    assert before == (len(calls), len(trials))
    # Verbatim first candidate, separately evaluated, not synthesized from eight proposals.
    assert campaign.state['cohorts']['evo_00_A']['code'] == (campaign.root/'fix_code.py').read_text()
    with pytest.raises(ValueError, match='development'):
        campaign.public_trial('heldout_s1')


def test_failed_program_not_promoted_but_failure_lesson_saved(tmp_path):
    library = SkillRepository(tmp_path/'skills')
    library.record_program('print(1)', [dict(success=False, execution_ok=True, evidence_id='dev')], 'failed')
    library.learn([dict(markdown='Observed air grasp; hypothesis remains unverified.', evidence_ids=['dev'])], ['dev'], 'v1')
    assert not library.read()['programs']
    assert library.context()['context']['notes'][0]['evidence_ids'] == ['dev']
    with pytest.raises(ValueError, match='development evidence'):
        library.learn([dict(markdown='unsubstantiated', evidence_ids=['heldout'])], ['dev'], 'v2')


def test_sensor_only_policy_rejects_reward_queries():
    with pytest.raises(ValueError, match='evaluator feedback'):
        validate_sensor_program('print(get_task_feedback())')


def test_rfdetr_binding_and_service_gate(monkeypatch, tmp_path):
    import io
    from src.aspire.config import load_protocol
    from src.aspire.perception import check_perception_service
    from src.aspire.config import INSTRUMENTS
    config = ROOT/'configs/aspire/full-scissor-rfdetr.json'
    _, task = load_protocol(config)
    assert task.perception_backend == 'rfdetr' and task.sam3_url is None
    campaign = FullCampaign(tmp_path/'rfdetr', config, relay_url='http://unused', model='opus', launcher='unused')
    assert 'ACTIVE PERCEPTION: trained five-class RF-DETR' in campaign.binding()
    health = dict(ready=True, backend='rfdetr', classes=list(INSTRUMENTS),
                  output='boxes', rfdetr='1.11.0', checkpoint_sha256='a'*64)
    monkeypatch.setattr('src.aspire.perception.urllib.request.urlopen',
                        lambda *args, **kwargs: io.BytesIO(json.dumps(health).encode()))
    assert check_perception_service(task)['checkpoint_sha256'] == 'a'*64
    health['classes'] = ['person']
    with pytest.raises(RuntimeError, match='five-class'):
        check_perception_service(task)
    health['classes'] = list(INSTRUMENTS)
    health.pop('checkpoint_sha256')
    with pytest.raises(RuntimeError, match='checkpoint'):
        check_perception_service(task)


def test_stream_reassembles_tool_arguments_and_rejects_interrupted_output(tmp_path):
    from src.aspire.relay import collect_stream
    events = [dict(model='opus', choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0,
        id='call1', function=dict(name='submit_practice', arguments='{"analysis":'))]))]),
        dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, function=dict(arguments='"ok"}'))]))]),
        dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')], usage=dict(total_tokens=42))]
    lines = [('data: '+json.dumps(event)+'\n\n').encode() for event in events]
    result = collect_stream(iter(lines+[b'data: [DONE]\n\n']), tmp_path/'complete.sse')
    tool = result['choices'][0]['message']['tool_calls'][0]
    assert json.loads(tool['function']['arguments']) == dict(analysis='ok')
    assert result['usage']['total_tokens'] == 42
    with pytest.raises(RuntimeError, match='Incomplete'):
        collect_stream(iter(lines[:-1]), tmp_path/'interrupted.sse')


def test_native_transport_preserves_prompts_images_and_streamed_tool_json(tmp_path):
    from src.aspire.relay import messages_payload, collect_messages_stream
    from src.aspire.full import SUBMIT_TOOL
    original = dict(model='opus', max_tokens=128000, timeout=1800, stream_timeout=1800, messages=[dict(role='system', content='binding'),
        dict(role='user', content=[dict(type='text', text='VERBATIM RUNBOOK\n'),
                                  dict(type='image_url', image_url=dict(url='data:image/png;base64,AAAA'))])],
        tools=[SUBMIT_TOOL], tool_choice=dict(function=dict(name='submit_practice')))
    mapped = messages_payload(original)
    assert mapped['messages'][0]['content'][0]['text'] == 'VERBATIM RUNBOOK\n'
    assert mapped['messages'][0]['content'][1]['source']['media_type'] == 'image/png'
    assert mapped['tools'][0]['eager_input_streaming'] is True
    assert mapped['timeout'] == mapped['stream_timeout'] == 1800
    events = [dict(type='message_start', message=dict(id='m', model='opus', usage=dict(input_tokens=10))),
        dict(type='content_block_start', index=0, content_block=dict(type='tool_use', id='t', name='submit_practice', input={})),
        dict(type='content_block_delta', index=0, delta=dict(type='input_json_delta', partial_json='{"ok":true}')),
        dict(type='content_block_stop', index=0),
        dict(type='message_delta', delta=dict(stop_reason='tool_use'), usage=dict(output_tokens=3)),
        dict(type='message_stop')]
    lines = [('data: '+json.dumps(event)+'\n').encode() for event in events]
    result = collect_messages_stream(iter(lines), tmp_path/'native.sse')
    assert result['usage']['total_tokens'] == 13
    assert result['choices'][0]['finish_reason'] == 'tool_calls'
    assert json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments']) == dict(ok=True)
    with pytest.raises(RuntimeError, match='Incomplete'):
        collect_messages_stream(iter(lines[:-1]), tmp_path/'incomplete.sse')


@pytest.mark.parametrize('finish,closed,arguments,expected', [
    ('end_turn', True, '{"ok":true}', 'tool_calls'),
    ('max_tokens', True, '{"ok":true}', 'length'),
    ('end_turn', False, '{"ok":true}', 'Incomplete native tool'),
    ('end_turn', True, '{"ok":', 'Malformed native tool'),
])
def test_native_finish_label_requires_closed_complete_tool_blocks(tmp_path, finish, closed, arguments, expected):
    from src.aspire.relay import collect_messages_stream
    events = [dict(type='message_start', message=dict(id='m', model='test', usage={})),
        dict(type='content_block_start', index=0, content_block=dict(type='tool_use', id='t', name='submit_program', input={})),
        dict(type='content_block_delta', index=0, delta=dict(type='input_json_delta', partial_json=arguments))]
    if closed:
        events.append(dict(type='content_block_stop', index=0))
    events += [dict(type='message_delta', delta=dict(stop_reason=finish)), dict(type='message_stop')]
    lines = [('data: ' + json.dumps(event) + '\n').encode() for event in events]
    if expected in ('tool_calls', 'length'):
        reply = collect_messages_stream(iter(lines), tmp_path / 'native.sse')
        assert reply['choices'][0]['finish_reason'] == expected
    else:
        with pytest.raises(RuntimeError, match=expected):
            collect_messages_stream(iter(lines), tmp_path / 'native.sse')


def test_full_trace_uses_upstream_logger_and_survives_program_error(tmp_path):
    from tests.test_aspire import FakeBackend
    from src.aspire.artifacts import Artifacts
    from src.aspire.config import TaskConfig
    from src.aspire.environment import SurgicalEnv
    from src.aspire.execution import SurgicalExecutionEnv
    sink = Artifacts(tmp_path)
    env = SurgicalEnv(FakeBackend(), TaskConfig(allow_evaluator_feedback=False), artifact_sink=sink)
    execution = SurgicalExecutionEnv(env)
    execution.reset(seed=501)
    assert 'get_task_feedback' not in execution._exec_globals
    _, _, _, _, info = execution.step('obs = get_observation()\nstate = get_robot_state()\nraise ValueError("test error")')
    assert info['sandbox_rc'] != 0
    trace = json.loads((tmp_path/'trace.json').read_text())
    assert [row['function'] for row in trace] == ['get_observation', 'get_robot_state']
    assert list((tmp_path/'keyframes').glob('*.jpg'))
    assert all(row['before_images'] and row['after_images'] for row in trace)
    sink.close()


def test_actor_selects_trace_and_image_and_native_tool_roundtrip(tmp_path):
    from src.aspire.relay import messages_payload
    from src.aspire.inspection import inspect
    requests = []
    def response(name, args, identifier):
        return dict(choices=[dict(finish_reason='tool_calls', message=dict(role='assistant', content=None,
            tool_calls=[dict(id=identifier, type='function', function=dict(name=name, arguments=json.dumps(args)))]))])
    def model(payload):
        requests.append(payload)
        native = messages_payload(payload)
        if len(requests) == 1:
            return response('inspect_evidence', dict(evidence_id='dev', view='trace', start=1, limit=1), 'trace_call')
        if len(requests) == 2:
            result = native['messages'][-1]['content'][0]
            assert result['type'] == 'tool_result' and result['tool_use_id'] == 'trace_call'
            assert json.loads(result['content'][0]['text'])['entries'] == [dict(function='close_gripper')]
            return response('inspect_evidence', dict(evidence_id='dev', view='images', images=['keyframes/chosen.jpg']), 'image_call')
        assert native['messages'][-1]['content'][0]['content'][1]['type'] == 'image'
        return response('submit_practice', dict(analysis='Inspected chosen primitive and frame', skills=[],
            programs=[dict(name='repair', parent='base', hypothesis='Repair observed grasp', code='print(1)')]), 'submit')
    campaign = FullCampaign(tmp_path/'run', ROOT/'configs/aspire/full-scissor-sam3.json',
        relay_url='unused', model='opus', launcher='unused', model_transport=model, shared_directory=tmp_path/'shared')
    directory = campaign.root/'trials/dev'
    write_json(directory/'result.json', dict(seed=101, success=False, execution_ok=True, status='completed'))
    write_json(directory/'trace.json', [dict(function='get_observation'), dict(function='close_gripper')])
    (directory/'keyframes').mkdir()
    Image.new('RGB', (8, 8)).save(directory/'keyframes/chosen.jpg')
    campaign.state['evidence']['dev'] = dict(path='trials/dev', split='development')
    result = campaign.propose('actor', 'Repair the grasp', ['dev'], [], 1)
    assert result['programs'][0]['code'] == 'print(1)' and len(requests) == 3
    with pytest.raises(ValueError, match='allowlist'):
        inspect(campaign, dict(evidence_id='dev', view='images', images=['../../private.png']), ['dev'])
    campaign.state['evidence']['heldout'] = dict(path='trials/dev', split='heldout')
    with pytest.raises(ValueError, match='development'):
        inspect(campaign, dict(evidence_id='heldout', view='trace'), ['heldout'])
    with pytest.raises(ValueError, match='post-freeze'):
        campaign.propose('leak', 'repair', ['heldout'], [], 1, admission=True)


def test_coordinator_admits_only_debug_repair_and_future_actor_retrieves(tmp_path, monkeypatch):
    from src.aspire.skill_admission import PATTERN_SCHEMA
    pattern = {key: 'Observed failure and reusable repair' for key in PATTERN_SCHEMA['required']}
    pattern['code_sketch'] = 'print(get_robot_state())'
    reviews = []
    def reviewer(payload):
        reviews.append(payload)
        return dict(choices=[dict(finish_reason='tool_calls', message=dict(tool_calls=[dict(
            function=dict(name='review_skills', arguments=json.dumps(dict(decisions=[dict(candidate=0, admit=True,
                reason='Sensor-based grasp verification is reusable; debugging replay succeeded.')]))))]))])
    campaign = FullCampaign(tmp_path/'run', ROOT/'configs/aspire/full-scissor-sam3.json',
        relay_url='unused', model='opus', launcher='unused', model_transport=reviewer, shared_directory=tmp_path/'shared')
    rows = []
    for eid, code, success in [('failed', 'print(0)', False), ('repaired', 'print(1)', True)]:
        directory = campaign.root/'trials'/eid
        row = dict(seed=101, success=success, execution_ok=True, status='completed',
                   program_sha256=digest(code), evidence_id=eid)
        write_json(directory/'result.json', row)
        campaign.state['evidence'][eid] = dict(path=f'trials/{eid}', split='development')
        rows.append(row)
    findings = dict(skills=[dict(markdown='Verified correction', pattern=pattern, evidence_ids=['failed','repaired'])])
    monkeypatch.setattr(campaign, 'propose', lambda *args, **kwargs: findings)
    pool = [dict(id='best', code='print(1)', sha256=digest('print(1)'), rows=rows, success_count=1)]
    heldout = dict(rows=[], success_count=0)
    campaign.consolidate(pool, pool[0], heldout)
    assert len(campaign.shared.context()) == 1 and len(reviews) == 1
    assert campaign.inherited_skills == []  # cannot alter an already dispatched actor's initial context
    # Rejected/unverified observations cannot become shared skills.
    findings['skills'][0]['evidence_ids'] = ['failed']
    campaign.consolidate(pool, pool[0], heldout)
    assert len(campaign.shared.context()) == 1 and len(reviews) == 1
    next_actor = FullCampaign(tmp_path/'next', ROOT/'configs/aspire/full-scissor-sam3.json',
        relay_url='unused', model='opus', launcher='unused', shared_directory=tmp_path/'shared')
    assert len(next_actor.inherited_skills) == 1
    assert next_actor.inherited_skills[0]['cross_task_transfer'] == 'not_yet_evaluated'
