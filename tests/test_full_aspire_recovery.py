"""Crash recovery never spends cached calls, repeats finished trials, or crosses a pause."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from src.aspire import full, recovery
from src.aspire.artifacts import write_json
from src.aspire.bootstrap import ROOT
from src.aspire.full import FullCampaign, digest


def make_campaign(tmp_path, **kwargs):
    return FullCampaign(tmp_path/'run', ROOT/'configs/aspire/full-scissor-sam3.json',
        relay_url='unused', model='opus', launcher='unused', shared_directory=tmp_path/'shared', **kwargs)


def evaluation_checkpoint(tmp_path, **kwargs):
    campaign = make_campaign(tmp_path, **kwargs)
    names = ['fix_initial'] + [f'evo_{iteration:02d}_{chr(65+index)}'
                              for iteration in range(2) for index in range(8)]
    names.append('evo_02_A')
    for name in names:
        code = f'print("{name}")\n'
        successes = 25 if name == 'evo_02_A' else 24 if name == 'evo_01_B' else 10
        rows = [dict(seed=seed, success=index < successes, evidence_id=f'{name}_s{seed}')
                for index, seed in enumerate(campaign.protocol['development_seeds'])]
        for row in rows:
            campaign.state['evidence'][row['evidence_id']] = dict(path='unused', split='development')
        campaign.state['cohorts'][name] = dict(id=name, code=code, sha256=digest(code),
                                             split='development', rows=rows, success_count=successes)
    campaign.save(status='paused', phase='evolutionary_search_paused', completed_round=1)
    return campaign


def test_direct_evaluation_skips_search_and_excludes_later_round(tmp_path, monkeypatch):
    trials = []
    def simulator(launcher, source, config, seed, out, **kwargs):
        trials.append((seed, Path(source).read_text()))
        result = dict(seed=seed, status='completed', execution_ok=True, success=seed % 2 == 0,
                      program_sha256=digest(Path(source).read_text()))
        write_json(Path(out)/'result.json', result)
        return result
    campaign = evaluation_checkpoint(tmp_path, trial_runner=simulator)
    def forbidden(*args, **kwargs):
        pytest.fail('Direct evaluation must not generate programs or run development trials')
    monkeypatch.setattr(campaign, 'propose', forbidden)
    monkeypatch.setattr(campaign, 'consolidate', lambda pool, selected, final: None)
    campaign.run(evaluate_after_round=1)
    assert campaign.state['status'] == 'completed'
    assert campaign.state['selected'] == 'evo_01_B'
    assert [seed for seed, _ in trials] == list(range(1, 101))
    assert {code for _, code in trials} == {campaign.state['cohorts']['evo_01_B']['code']}
    report = json.loads((campaign.root/'report.json').read_text())
    assert report['final_success_count'] == 50 and report['final_trial_count'] == 100
    assert report['plan']['T'] == 3 and report['evaluation_plan']['skipped_rounds'] == [2]
    assert 'evo_02_A' not in report['evaluation_plan']['selection_cohorts']
    assert len(report['evaluation_plan']['excluded_development_evidence']) == 25
    campaign.run()
    assert len(trials) == 100


def test_direct_evaluation_resume_keeps_freeze_and_reuses_completed_trials(tmp_path, monkeypatch):
    trials = []
    def simulator(launcher, source, config, seed, out, **kwargs):
        if seed == 3 and len(trials) == 2:
            raise RuntimeError('Interrupted physics worker')
        trials.append(seed)
        result = dict(seed=seed, status='completed', execution_ok=True, success=True,
                      program_sha256=digest(Path(source).read_text()))
        write_json(Path(out)/'result.json', result)
        return result
    campaign = evaluation_checkpoint(tmp_path, trial_runner=simulator)
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(evaluate_after_round=1)
    protected = {name: (campaign.root/name).read_bytes()
                 for name in ('selection.json', 'frozen_program.py', 'frozen_skills.json', 'evaluation_plan.json')}
    with pytest.raises(ValueError, match='boundary changed'):
        campaign.run(evaluate_after_round=2)
    def resumed_simulator(launcher, source, config, seed, out, **kwargs):
        trials.append(seed)
        result = dict(seed=seed, status='completed', execution_ok=True, success=True,
                      program_sha256=digest(Path(source).read_text()))
        write_json(Path(out)/'result.json', result)
        return result
    resumed = make_campaign(tmp_path, trial_runner=resumed_simulator)
    def forbidden(*args, **kwargs):
        pytest.fail('An evaluation resume cannot search or replace frozen memory')
    monkeypatch.setattr(resumed, 'propose', forbidden)
    monkeypatch.setattr(resumed.library, 'context', forbidden)
    monkeypatch.setattr(resumed, 'consolidate', lambda *args: None)
    resumed.run()
    assert trials == list(range(1, 101))
    assert all((resumed.root/name).read_bytes() == data for name, data in protected.items())


def test_heldout_limit_reuses_outcomes_survives_resume_and_stays_campaign_local(tmp_path, monkeypatch):
    trials, interruptions = [], [3, 5]
    def simulator(launcher, source, config, seed, out, **kwargs):
        if seed in interruptions:
            interruptions.remove(seed)
            raise RuntimeError('Interrupted evaluation')
        trials.append(seed)
        result = dict(seed=seed, status='completed', execution_ok=True, success=seed % 2 == 0,
                      program_sha256=digest(Path(source).read_text()))
        write_json(Path(out)/'result.json', result)
        return result
    campaign = evaluation_checkpoint(tmp_path, trial_runner=simulator)
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(evaluate_after_round=1)
    protected = {name: (campaign.root/name).read_bytes() for name in
                 ('selection.json', 'frozen_program.py', 'frozen_skills.json', 'evaluation_plan.json', 'contract.json', 'plan.json')}
    with pytest.raises(ValueError, match='discard'):
        campaign.run(heldout_trials=1)
    assert not (campaign.root/'evaluation_limit.json').exists()
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(heldout_trials=30)
    limit_path = campaign.root/'evaluation_limit.json'
    limit_bytes = limit_path.read_bytes()
    limit = json.loads(limit_bytes)
    assert limit['evaluation_seeds'] == list(range(1, 31))
    assert limit['completed_seeds_before_change'] == [1, 2]
    assert limit['planned_trial_count'] == 100 and limit['heldout_trials'] == 30
    with pytest.raises(ValueError, match='limit changed'):
        campaign.run(heldout_trials=50)
    resumed = make_campaign(tmp_path, trial_runner=simulator)
    monkeypatch.setattr(resumed, 'consolidate', lambda *args: None)
    resumed.run()
    assert trials == list(range(1, 31))
    assert resumed.state['status'] == 'completed' and resumed.state['heldout_trial_limit'] == 30
    assert limit_path.read_bytes() == limit_bytes
    assert all((resumed.root/name).read_bytes() == data for name, data in protected.items())
    report = json.loads((resumed.root/'report.json').read_text())
    assert report['final_trial_count'] == 30 and report['final_success_count'] == 15
    assert report['evaluation_limit'] == limit
    assert '30/100 planned trials' in (resumed.root/'findings.md').read_text()
    resumed.run()
    assert trials == list(range(1, 31))
    other = make_campaign(tmp_path/'other')
    assert len(other.protocol['evaluation_seeds']) == 100
    assert not (other.root/'evaluation_limit.json').exists()


@pytest.mark.parametrize('limit', [0, -1, 101, True, '30', 2.5])
def test_invalid_heldout_limit_does_not_start_work(tmp_path, limit):
    campaign = make_campaign(tmp_path)
    with pytest.raises(ValueError, match='integer'):
        campaign.run(heldout_trials=limit)
    assert campaign.state['status'] == 'initialized'


def test_heldout_limit_requires_a_frozen_program(tmp_path):
    campaign = make_campaign(tmp_path)
    with pytest.raises(ValueError, match='already frozen'):
        campaign.run(heldout_trials=30)
    assert campaign.state['status'] == 'initialized'
    assert not (campaign.root/'evaluation_limit.json').exists()


def test_heldout_limit_cannot_truncate_a_finished_evaluation(tmp_path):
    campaign = evaluation_checkpoint(tmp_path)
    write_json(campaign.root/'selection.json', dict(sha256='already frozen'))
    campaign.save(status='completed')
    with pytest.raises(ValueError, match='completed evaluation'):
        campaign.run(heldout_trials=30)
    assert not (campaign.root/'evaluation_limit.json').exists()


def test_explicit_heldout_revision_preserves_history_and_finishes_at_20(tmp_path, monkeypatch):
    trials, interruptions = [], [3, 5, 7]
    def simulator(launcher, source, config, seed, out, **kwargs):
        if seed in interruptions:
            interruptions.remove(seed)
            raise RuntimeError('Interrupted evaluation')
        trials.append(seed)
        result = dict(seed=seed, status='completed', execution_ok=True, success=seed % 2 == 0,
                      program_sha256=digest(Path(source).read_text()))
        write_json(Path(out)/'result.json', result)
        return result
    campaign = evaluation_checkpoint(tmp_path, trial_runner=simulator)
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(evaluate_after_round=1)
    protected = {name: (campaign.root/name).read_bytes() for name in
                 ('selection.json', 'frozen_program.py', 'frozen_skills.json', 'evaluation_plan.json', 'contract.json', 'plan.json')}
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(heldout_trials=30)
    limit_path = campaign.root/'evaluation_limit.json'
    previous_bytes = limit_path.read_bytes()
    with pytest.raises(ValueError, match='only reduce'):
        campaign.run(heldout_trials=40, revise_heldout_limit=True)
    with pytest.raises(ValueError, match='discard'):
        campaign.run(heldout_trials=3, revise_heldout_limit=True)
    assert limit_path.read_bytes() == previous_bytes
    with pytest.raises(RuntimeError, match='Interrupted'):
        campaign.run(heldout_trials=20, revise_heldout_limit=True)
    revised = json.loads(limit_path.read_bytes())
    assert revised['heldout_trials'] == 20 and revised['planned_trial_count'] == 100
    assert revised['evaluation_seeds'] == list(range(1, 21))
    assert revised['completed_seeds_before_change'] == [1, 2, 3, 4]
    assert revised['previous_trial_count'] == 30
    assert (campaign.root/revised['previous_limit_archive']).read_bytes() == previous_bytes
    import hashlib
    assert hashlib.sha256(previous_bytes).hexdigest() == revised['previous_limit_sha256']
    resumed = make_campaign(tmp_path, trial_runner=simulator)
    monkeypatch.setattr(resumed, 'consolidate', lambda *args: None)
    resumed.run()
    assert trials == list(range(1, 21))
    assert resumed.state['status'] == 'completed' and resumed.state['heldout_trial_limit'] == 20
    assert all((resumed.root/name).read_bytes() == data for name, data in protected.items())
    report = json.loads((resumed.root/'report.json').read_text())
    assert report['final_trial_count'] == 20 and report['evaluation_limit'] == revised
    assert '20/100 planned trials' in (resumed.root/'findings.md').read_text()


@pytest.mark.parametrize('retry', [False, True])
def test_heldout_revision_cannot_discard_uncheckpointed_terminal_results(tmp_path, retry):
    campaign = evaluation_checkpoint(tmp_path)
    selected = campaign.state['cohorts']['evo_01_B']
    write_json(campaign.root/'selection.json', dict(sha256=selected['sha256']))
    campaign._set_heldout_limit(30)
    limit_path = campaign.root/'evaluation_limit.json'
    previous_bytes = limit_path.read_bytes()
    directory = campaign.root/'trials/heldout_s21'
    if retry:
        write_json(directory/'result.json', dict(seed=21, status='worker_wall_timeout'))
        directory = directory/'attempt_001'
    write_json(directory/'result.json', dict(seed=21, status='program_error', execution_ok=False,
                                             success=False, program_sha256=selected['sha256']))
    with pytest.raises(ValueError, match='discard'):
        campaign._set_heldout_limit(20, revise=True)
    assert limit_path.read_bytes() == previous_bytes
    assert not (campaign.root/'control/evaluation_limits').exists()


def test_heldout_revision_requires_an_explicit_count_and_saved_limit(tmp_path):
    campaign = make_campaign(tmp_path)
    with pytest.raises(ValueError, match='explicit trial count'):
        campaign.run(revise_heldout_limit=True)
    with pytest.raises(ValueError, match='saved limit'):
        campaign.run(heldout_trials=20, revise_heldout_limit=True)
    assert campaign.state['status'] == 'initialized'


@pytest.mark.parametrize('damage', ['missing_candidate', 'duplicate_seed', 'changed_program', 'incorrect_score'])
def test_direct_evaluation_rejects_incomplete_or_corrupt_development(tmp_path, damage):
    campaign = evaluation_checkpoint(tmp_path)
    candidate = campaign.state['cohorts']['evo_01_H']
    if damage == 'missing_candidate':
        del campaign.state['cohorts']['evo_01_H']
    elif damage == 'duplicate_seed':
        candidate['rows'][0]['seed'] = candidate['rows'][1]['seed']
    elif damage == 'changed_program':
        candidate['code'] += 'print("changed")\n'
    else:
        candidate['success_count'] += 1
    with pytest.raises(ValueError, match='development'):
        campaign.run(evaluate_after_round=1)
    assert not (campaign.root/'selection.json').exists()
    assert not (campaign.root/'evaluation_plan.json').exists()


@pytest.mark.parametrize('bound', [-1, 3, True, '1'])
def test_invalid_direct_evaluation_does_not_start_work(tmp_path, bound):
    campaign = make_campaign(tmp_path)
    with pytest.raises(ValueError, match='zero-based'):
        campaign.run(evaluate_after_round=bound)
    assert campaign.state['status'] == 'initialized'


@pytest.mark.parametrize('bound', [-1, 3, True, '1'])
def test_invalid_pause_does_not_start_work(tmp_path, bound):
    campaign = make_campaign(tmp_path)
    with pytest.raises(ValueError, match='zero-based'):
        campaign.run(pause_after_round=bound)
    assert campaign.state['status'] == 'initialized'


@pytest.mark.parametrize('bound', [0, 1, 2])
def test_early_success_cannot_bypass_pause_into_heldout(tmp_path, monkeypatch, bound):
    campaign = make_campaign(tmp_path)
    monkeypatch.setattr(campaign, 'trial', lambda *args: dict(success=True))
    def propose(identifier, instruction, evidence, parents, count, **kwargs):
        return dict(programs=[dict(code=f'print("{identifier}_{index}")', hypothesis='Distinct strategy')
                              for index in range(count)])
    def cohort(identifier, source, split='development'):
        assert split == 'development'
        rows = [dict(evidence_id=f'{identifier}_{seed}', success=True) for seed in range(101, 126)]
        return dict(id=identifier, code=source, rows=rows, success_count=25, sha256=digest(source))
    monkeypatch.setattr(campaign, 'propose', propose)
    monkeypatch.setattr(campaign, 'cohort', cohort)
    campaign.run(pause_after_round=bound)
    assert campaign.state['status'] == 'paused' and campaign.state['completed_round'] == 0
    assert not (campaign.root/'selection.json').exists()
    assert not (campaign.root/'frozen_program.py').exists()
    assert not (campaign.root/'iter_01_summary.json').exists()


def test_interrupted_actor_reuses_cached_inspections_and_original_request(tmp_path, monkeypatch):
    calls, inspections = [], []
    def inspect(*args, **kwargs):
        inspections.append(1)
        return [dict(type='text', text='Saved sensor evidence')]
    monkeypatch.setattr(full, 'inspect', inspect)
    def model(payload):
        calls.append(payload)
        if len(calls) == 4:
            raise RuntimeError('Shutdown during stream')
        if len(calls) <= 3:
            name, arguments = 'inspect_evidence', dict(evidence_id='dev', view='trace')
        else:
            name = 'submit_practice'
            arguments = dict(analysis='Inspected evidence', skills=[], programs=[dict(
                code=f'print({index})', hypothesis=f'Independent strategy {index}') for index in range(8)])
        return dict(choices=[dict(message=dict(tool_calls=[dict(id=f'turn{len(calls)}',
            type='function', function=dict(name=name, arguments=json.dumps(arguments)))]))])
    campaign = make_campaign(tmp_path, model_transport=model)
    directory = campaign.root/'trials/dev'
    write_json(directory/'result.json', dict(seed=101, success=False, status='completed', execution_ok=True))
    campaign.state['evidence']['dev'] = dict(path='trials/dev', split='development')
    campaign.save()
    with pytest.raises(RuntimeError, match='Shutdown'):
        campaign.propose('evo_01', 'Generate eight strategies', ['dev'], [], 8, evolution=True)
    request_path = campaign.root/'model/evo_01_3.request.json'
    original = request_path.read_bytes()
    assert len(inspections) == 3
    assert not (campaign.root/'model/evo_01_3.response.json').exists()
    resumed = make_campaign(tmp_path, model_transport=model)
    result = resumed.propose('evo_01', 'Generate eight strategies', ['dev'], [], 8, evolution=True)
    assert len(result['programs']) == 8 and len(calls) == 5
    assert len(inspections) == 3 and request_path.read_bytes() == original
    assert calls[3] == calls[4]


def test_changed_interrupted_request_is_rejected_without_model_call(tmp_path):
    calls = []
    campaign = make_campaign(tmp_path, model_transport=lambda payload: calls.append(payload))
    write_json(campaign.root/'model/pending.request.json', dict(messages=['original']))
    with pytest.raises(ValueError, match='request changed'):
        campaign.request('pending', dict(messages=['different']))
    assert not calls


@pytest.mark.parametrize('already_finished', [False, True])
def test_retry_preserves_crash_and_uses_correct_trace_without_repeating(tmp_path, already_finished):
    calls = []
    code = 'print(1)'
    def simulator(launcher, source, config, seed, out, **kwargs):
        calls.append(str(out))
        result = dict(status='completed', seed=seed, success=True, execution_ok=True, program_sha256=digest(code))
        write_json(Path(out)/'result.json', result)
        write_json(Path(out)/'trace.json', [dict(function='close_gripper', attempt='successful')])
        return result
    campaign = make_campaign(tmp_path, trial_runner=simulator)
    directory = campaign.root/'trials/dev'
    crash = dict(status='worker_crashed', seed=101, success=False, execution_ok=False)
    write_json(directory/'result.json', crash)
    write_json(directory/'trace.json', [dict(attempt='crashed')])
    original = (directory/'result.json').read_bytes()
    if already_finished:
        (directory/'result.attempt001.json').write_bytes(original)
        simulator('unused', None, None, 101, directory/'attempt_001')
        calls.clear()
    row = campaign.trial('dev', code, 101, 'development')
    assert row['success']
    assert len(calls) == (0 if already_finished else 1)
    assert (directory/'result.attempt001.json').read_bytes() == original
    public, evidence_directory = campaign.public_trial('dev')
    assert evidence_directory == directory/'attempt_001'
    assert public['trace'][0]['attempt'] == 'successful'
    resumed = make_campaign(tmp_path, trial_runner=simulator)
    resumed.trial('dev', code, 101, 'development')
    assert len(calls) == (0 if already_finished else 1)
    assert resumed.public_trial('dev')[1] == evidence_directory


def make_ledgers(tmp_path):
    write_json(tmp_path/'launch.json', dict(prior_requests=42))
    for index, requests, completed in [(0, 15, 15), (1, 0, 0), (2, 0, 0), (3, 21, 21), (4, 4, 3)]:
        write_json(tmp_path/f'provider_{index:03d}/report.json', dict(
            requests=requests, completed=completed, pending=requests-completed))
    return dict(pid=12345, status='running')


def test_interrupted_accounting_preserves_82_attempts_and_pending_report(tmp_path, monkeypatch):
    previous = make_ledgers(tmp_path)
    monkeypatch.setattr(recovery, 'process_is_running', lambda pid: False)
    report_path = tmp_path/'provider_004/report.json'
    original = report_path.read_bytes()
    with pytest.raises(ValueError, match='explicit'):
        recovery.audit_ledgers(tmp_path, prior_requests=82, recover_interrupted=False, previous_supervisor=previous)
    with pytest.raises(ValueError, match='omits'):
        recovery.audit_ledgers(tmp_path, prior_requests=81, recover_interrupted=True, previous_supervisor=previous)
    audit = recovery.audit_ledgers(tmp_path, prior_requests=82, recover_interrupted=True, previous_supervisor=previous)
    assert audit['attempted_requests'] == 82 and audit['next_ledger'] == 'provider_005'
    assert audit['pending_ledgers'][0]['report']['pending'] == 1
    assert report_path.read_bytes() == original
    write_json(tmp_path/'recoveries/recovery_test.json', dict(pending_ledgers=audit['pending_ledgers']))
    subsequent = recovery.audit_ledgers(tmp_path, prior_requests=82, recover_interrupted=False, previous_supervisor=previous)
    assert not subsequent['unrecovered_pending']
    assert subsequent['attempted_requests'] == 82


def test_pending_recovery_rejects_live_or_unknown_owner(tmp_path, monkeypatch):
    previous = make_ledgers(tmp_path)
    monkeypatch.setattr(recovery, 'process_is_running', lambda pid: True)
    for owner in (previous, None):
        with pytest.raises(ValueError, match='inactive'):
            recovery.audit_ledgers(tmp_path, prior_requests=82, recover_interrupted=True, previous_supervisor=owner)


def test_supervisor_lock_excludes_overlap_and_releases(tmp_path):
    with recovery.SupervisorLock(tmp_path):
        with pytest.raises(RuntimeError, match='owns'):
            with recovery.SupervisorLock(tmp_path):
                pytest.fail('Overlapping ownership was accepted')
    with recovery.SupervisorLock(tmp_path):
        pass
    write_json(tmp_path/'supervisor.json', dict(pid=os.getpid(), status='running'))
    with pytest.raises(RuntimeError, match='still alive'):
        with recovery.SupervisorLock(tmp_path):
            pytest.fail('Live owner was ignored')


@pytest.mark.parametrize('stage_flag, stage_key', [('--pause-after-round', 'pause_after_round'),
                                                ('--evaluate-after-round', 'evaluate_after_round'),
                                                ('--heldout-trials', 'heldout_trials')])
def test_supervisor_cli_recovers_without_mutating_old_ledger(tmp_path, monkeypatch, stage_flag, stage_key):
    from scripts import run_full_aspire as runner
    from src.aspire import perception
    directory = tmp_path/'logs/run'
    previous = make_ledgers(directory)
    configuration = str(ROOT/'configs/aspire/full-scissor-sam3.json')
    launch = dict(prior_requests=42, model='opus', config=configuration, headless=False,
                  python='unused', base_url='https://llm.igvi.cs.nthu.edu.tw/v1')
    write_json(directory/'launch.json', launch)
    write_json(directory/'supervisor.json', previous)
    write_json(directory/'state.json', dict(status='running', phase='evolutionary_search', active='model:evo_01_3'))
    original = (directory/'provider_004/report.json').read_bytes()
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(recovery, 'process_is_running', lambda pid: False)
    monkeypatch.setattr(perception, 'check_perception_service', lambda task: dict(ready=True))
    monkeypatch.setattr(runner, 'load_credential', lambda *args: 'test-only')
    monkeypatch.setenv('API_KEY', 'test-only')
    relays = []
    class FakeRelay:
        def __init__(self, path, **kwargs):
            relays.append(kwargs)
            path.mkdir()
            self.url = 'unused'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class FakeCampaign:
        def __init__(self, *args, **kwargs):
            self.state = dict(status='running')
        def save(self, **updates):
            self.state.update(updates)
        def run(self, **kwargs):
            assert kwargs[stage_key] == 1
            assert kwargs['revise_heldout_limit'] == (stage_key == 'heldout_trials')
            self.state['status'] = 'paused'
    monkeypatch.setattr(runner, 'ProviderRelay', FakeRelay)
    monkeypatch.setattr(runner, 'FullCampaign', FakeCampaign)
    arguments = ['run_full_aspire.py', '--out', str(directory), '--resume',
        '--config', configuration, '--model', 'opus', '--python', 'unused',
        '--prior-requests', '82', '--request-budget', '68', '--max-total-requests', '150',
        stage_flag, '1', '--recover-interrupted']
    if stage_key == 'heldout_trials':
        arguments.append('--revise-heldout-limit')
    monkeypatch.setattr(sys, 'argv', arguments)
    assert runner.main() == 0
    assert relays[0]['prior_requests'] == 82 and relays[0]['request_budget'] == 68
    assert (directory/'provider_004/report.json').read_bytes() == original
    records = list((directory/'recoveries').glob('recovery_*.json'))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record['replacement_ledger'] == 'provider_005'
    assert record['previous_supervisor'] == previous
    assert record['pending_ledgers'][0]['report']['pending'] == 1
    assert json.loads((directory/'supervisor.json').read_text())['status'] == 'paused'


def test_supervisor_cli_rejects_model_switch_before_service_or_credentials(tmp_path, monkeypatch):
    from scripts import run_full_aspire as runner
    from src.aspire import perception
    directory = tmp_path/'logs/run'
    configuration = str(ROOT/'configs/aspire/full-scissor-sam3.json')
    write_json(directory/'launch.json', dict(model='opus', config=configuration))
    def forbidden(*args, **kwargs):
        pytest.fail('Services or credentials were accessed before rejecting the model change')
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(perception, 'check_perception_service', forbidden)
    monkeypatch.setattr(runner, 'load_credential', forbidden)
    monkeypatch.setattr(sys, 'argv', ['run_full_aspire.py', '--out', str(directory), '--resume',
        '--config', configuration, '--model', 'different'])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    assert not list(directory.glob('provider_*'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows continuation launcher')
@pytest.mark.parametrize('stage_switch, stage_flag', [('-PauseAfterRound', '--pause-after-round'),
                                                   ('-EvaluateAfterRound', '--evaluate-after-round'),
                                                   ('-HeldoutTrials', '--heldout-trials')])
def test_continuation_preserves_model_endpoint_display_and_pause(tmp_path, stage_switch, stage_flag):
    scripts = tmp_path/'scripts'
    scripts.mkdir()
    shutil.copyfile(ROOT/'scripts/continue_full_aspire.ps1', scripts/'continue_full_aspire.ps1')
    launcher = scripts/'fake_python.ps1'
    launcher.write_text('$args | ConvertTo-Json -Compress\nexit 0\n')
    campaign = tmp_path/'logs/run'
    make_ledgers(campaign)
    write_json(campaign/'state.json', dict(status='running'))
    write_json(campaign/'launch.json', dict(prior_requests=42, model='chatgpt1/gpt-6.1-sol',
        base_url='https://llm.igvi.cs.nthu.edu.tw/v1', python=str(launcher), config='frozen.json', headless=False))
    arguments = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', str(scripts/'continue_full_aspire.ps1'), '-Out', str(campaign),
        '-MaxTotalRequests', '150', stage_switch, '1', '-RecoverInterrupted']
    if stage_flag == '--heldout-trials':
        arguments.append('-ReviseHeldoutLimit')
    process = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    arguments = json.loads(process.stdout)
    expected = {'--model': 'chatgpt1/gpt-6.1-sol', '--base-url': 'https://llm.igvi.cs.nthu.edu.tw/v1',
                '--prior-requests': '82', '--request-budget': '68', '--max-total-requests': '150',
                stage_flag: '1', '--python': str(launcher)}
    for flag, value in expected.items():
        assert str(arguments[arguments.index(flag)+1]) == value
    assert '--recover-interrupted' in arguments and '--headless' not in arguments
    assert ('--revise-heldout-limit' in arguments) == (stage_flag == '--heldout-trials')
