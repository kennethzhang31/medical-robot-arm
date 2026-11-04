"""ASPIRE's coding-agent Fix Loop and Evolutionary Search, ported to surgery.

The pinned runbooks are supplied verbatim. A separate binding document maps
their simulator, tools, seeds and budgets to this workspace. The host enforces
stage boundaries; the configured model diagnoses observations, writes programs and maintains
Markdown skills. This is not the CAP single-trial ensemble/synthesis loop.
"""
import ast
import base64
import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import write_json
from .bootstrap import ROOT, UPSTREAM, setup_paths, upstream_revision
from .campaign import run_trial
from .config import load_protocol
from .execution import validate_program
from .inspection import INSPECT_TOOL, inspect
from .skill_admission import PATTERN_SCHEMA, REVIEW_TOOL, SharedSkills

FIX = UPSTREAM / 'aspire/sim/.claude/robosuite/fix-loop'
EVO = UPSTREAM / 'aspire/sim/.claude/robosuite/evosearch'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def image_url(path):
    path = Path(path)
    mime = 'image/png' if path.suffix == '.png' else 'image/jpeg'
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()


def validate_sensor_program(source):
    tree = validate_program(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'get_task_feedback':
            raise ValueError('The full protocol uses sensors for control; evaluator feedback is trial-level only')
    return tree


def plan(config, *, candidates=8, iterations=3):
    protocol, task = load_protocol(config)
    if candidates != 8 or iterations != 3:
        raise ValueError('This approved surgical protocol is K=8, T=3')
    if task.allow_evaluator_feedback:
        raise ValueError('Full protocol requires allow_evaluator_feedback=false')
    if 'validation_seeds' in protocol:
        raise ValueError('Use the paper two-partition protocol; the 6/4/10 pilot is retired')
    dev, evaluation = (len(protocol[key]) for key in ('development_seeds', 'evaluation_seeds'))
    return dict(protocol='ASPIRE surgical Fix Loop + Evolutionary Search v3',
        target=task.target, perception_backend=task.perception_backend,
        K=candidates, T=iterations, exploration_blocks=5,
        fix_refinements=5, split=dict(development=protocol['development_seeds'],
        heldout=protocol['evaluation_seeds']),
        max_simulator_trials=1+5+6*dev+candidates*iterations*dev+evaluation,
        provider_attempt_cap='explicit launch budget; inspection turns also count', timeout_s=1800, max_output_tokens=128000,
        visual_feedback='actor-selected primitive traces, pre/post sensor keyframes and perception overlays',
        skills='task-local working memory; coordinator-reviewed debug-validated repairs in a shared library',
        selection='best development program frozen before one held-out cohort; extract and review skills afterward',
        deviations=['Isaac Sim 4.5 on Windows instead of Robosuite/MuJoCo on Linux',
                    f'Surgical RGB-D/{task.perception_backend} and Cartesian motor API; not Robosuite GraspNet/PyRoKi/Molmo',
                    f'User-selected K=8, T=3; campaign declares {dev} debug / {evaluation} held-out seeds',
                    'Native Opus tool-loop actor and separate coordinator review instead of Claude Code CLI; context capacity unverified',
                    'Sequential simulation on one GPU; scissors is the first task',
                    'Seed resets are not saved physical scene snapshots; no exact matched-scene claim',
                    'Local task evaluation, not a reproduction of paper benchmark numbers'])


class SkillRepository:
    """Persistent, evidence-linked learning, including lessons from failures."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / 'index.json'
        if not self.index.exists():
            write_json(self.index, dict(notes=[], programs=[]))

    def read(self):
        return json.loads(self.index.read_text(encoding='utf-8'))

    def context(self):
        state = self.read()
        notes = [dict(row, markdown=(self.root/row['path']).read_text(encoding='utf-8')) for row in state['notes']]
        # Keep all evidence notes and the three best executable programs.
        programs = sorted(state['programs'], key=lambda r: (-r['success_count'], r['sha256']))[:3]
        programs = [dict(row, code=(self.root/row['path']).read_text(encoding='utf-8')) for row in programs]
        context = dict(notes=notes, programs=programs)
        return dict(context=context, sha256=digest(json.dumps(context, sort_keys=True)))

    def learn(self, notes, evidence, version):
        state = self.read()
        allowed = set(evidence)
        for index, note in enumerate(notes):
            refs = note.get('evidence_ids', [])
            if not refs or not set(refs) <= allowed:
                raise ValueError('Every learned note must cite existing development evidence')
            name = f'{version}_{index:02d}.md'
            text = note['markdown']
            existing = next((row for row in state['notes'] if row['path'] == name), None)
            if existing:
                if existing['sha256'] != digest(text) or existing['evidence_ids'] != refs:
                    raise ValueError('Cannot overwrite a previously recorded skill version')
                continue
            (self.root/name).write_text(text, encoding='utf-8')
            state['notes'].append(dict(path=name, sha256=digest(text), evidence_ids=refs,
                status='development_observation_not_independently_validated'))
        write_json(self.index, state)

    def record_program(self, source, rows, identifier):
        state = self.read()
        successes = sum(bool(row['success'] and row['execution_ok']) for row in rows)
        if not successes:
            return
        sha = digest(source)
        if any(row['sha256'] == sha for row in state['programs']):
            return
        filename = f'{identifier}.py'
        (self.root/filename).write_text(source, encoding='utf-8')
        state['programs'].append(dict(path=filename, sha256=sha,
            success_count=successes, trial_count=len(rows),
            evidence_ids=[row['evidence_id'] for row in rows],
            status='passed_all_development' if successes == len(rows) else 'partially_successful'))
        write_json(self.index, state)


PROGRAM_SCHEMA = dict(type='object', properties={
    'name': dict(type='string'), 'parent': dict(type='string'),
    'hypothesis': dict(type='string'), 'code': dict(type='string')},
    required=['name', 'parent', 'hypothesis', 'code'], additionalProperties=False)
SUBMIT_TOOL = dict(type='function', eager_input_streaming=True, function=dict(name='submit_practice',
    description='Submit task analysis, evidence-linked skill updates, and the requested standalone programs.',
    parameters=dict(type='object', properties={
        'analysis': dict(type='string'),
        'skills': dict(type='array', items=dict(type='object', properties={
            'markdown': dict(type='string'), 'evidence_ids': dict(type='array', items=dict(type='string')),
            'pattern': PATTERN_SCHEMA},
            required=['markdown', 'evidence_ids'], additionalProperties=False)),
        'programs': dict(type='array', items=PROGRAM_SCHEMA)},
        required=['analysis', 'skills', 'programs'], additionalProperties=False)))


class FullCampaign:
    def __init__(self, directory, config, *, relay_url, model, launcher,
                 headless=False, timeout=1800, trial_runner=run_trial, model_transport=None, shared_directory=None):
        self.root = Path(directory).resolve()
        self.config = Path(config).resolve()
        self.protocol, self.task = load_protocol(config)
        self.plan = plan(config)
        if (self.root/'plan.json').exists():
            old_plan = json.loads((self.root/'plan.json').read_text(encoding='utf-8'))
            if old_plan['protocol'] != self.plan['protocol']:
                raise ValueError('Protocol changed; preserve the old campaign and use a fresh output directory')
        self.relay_url, self.model, self.launcher = relay_url, model, launcher
        self.headless, self.timeout, self.trial_runner = headless, timeout, trial_runner
        self.model_transport = model_transport
        self.library = SkillRepository(self.root/'skills')
        self.state_path = self.root/'state.json'
        self.state = (json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists()
                      else dict(status='initialized', phase='preflight', evidence={}, cohorts={}, requests={}, vdms={}))
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root/'contract.json').exists():
            if json.loads((self.root/'contract.json').read_text(encoding='utf-8')) != self.protocol:
                raise ValueError('Resume config differs from frozen contract')
        write_json(self.root/'contract.json', self.protocol)
        write_json(self.root/'plan.json', self.plan)
        self.snapshot_runbooks()
        self.shared = SharedSkills(shared_directory or ROOT/'logs/aspire_shared_skills'/self.task.perception_backend)
        shared_snapshot = self.root/'inherited_skills.json'
        if not shared_snapshot.exists():
            write_json(shared_snapshot, self.shared.context())
        # An actor's initial library is immutable across restarts and held-out evaluation.
        self.inherited_skills = json.loads(shared_snapshot.read_text(encoding='utf-8'))

    def save(self, **updates):
        self.state.update(updates)
        self.state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        if updates.get('status') == 'running':
            self.state.pop('error', None)
            self.state.pop('error_type', None)
        write_json(self.state_path, self.state)
        print(json.dumps({k:self.state.get(k) for k in ('status', 'phase', 'active', 'selected')}), flush=True)

    def snapshot_runbooks(self):
        destination = self.root/'upstream'
        destination.mkdir(exist_ok=True)
        files = [FIX/'subagent-prompt.md', EVO/'subagent-prompt.md']
        files.extend(FIX/'skills'/f'{name}.md' for name in ('grasp', 'localize', 'transport', 'manipulation'))
        manifest = []
        for path in files:
            name = ('evo_' if path.parent == EVO else 'fix_') + path.name
            data = path.read_bytes()
            (destination/name).write_bytes(data)
            manifest.append(dict(source=str(path.relative_to(UPSTREAM)), path=name,
                                 sha256=hashlib.sha256(data).hexdigest()))
        write_json(destination/'manifest.json', dict(commit=upstream_revision(), files=manifest))

    def api_prompt(self):
        from types import SimpleNamespace
        from .control import SurgicalControlApi
        return SurgicalControlApi(SimpleNamespace(config=self.task)).combined_doc()

    def binding(self):
        if self.task.perception_backend == 'rfdetr':
            perception = (f'ACTIVE PERCEPTION: trained five-class RF-DETR. Use exact class {self.task.target}. '
                'Outputs are detection boxes; the adapter constructs a region using measured depth within the box. '
                'These are not learned segmentation masks. Free-text synonyms and point prompts are unsupported. '
                'No SAM3 service is used.')
        else:
            perception = ('ACTIVE PERCEPTION: SAM3 text masks and visual box prompts. '
                'Text may miss unfamiliar instruments. get_tabletop_candidates supplies class-agnostic depth '
                'regions and boxes from the current RGB-D image. Inspect visible appearance/shape to select '
                'the requested tool, then optionally call segment_instrument(box=...) to refine its mask. '
                'A depth-component mask can also be passed directly to mask_to_robot_points/estimate_grasp. '
                'Neither candidate order nor box-prompt confidence identifies the target. '
                'Never memorize image coordinates. Point prompts are unsupported.')
        active = f'ACTIVE TASK: {self.task.target}; model: {self.model}. The appended plan defines the actual seed partitions and trial counts.'
        return (ROOT/'docs/ASPIRE_SURGICAL_BINDING.md').read_text(encoding='utf-8') + '\n' + active + '\n' + perception + '\n' + json.dumps(self.plan)

    def request(self, identifier, payload):
        path = self.root/'model'/f'{identifier}.response.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        request_path = path.with_name(f'{identifier}.request.json')
        if request_path.exists():
            if json.loads(request_path.read_text(encoding='utf-8')) != payload:
                raise ValueError('Interrupted model request changed; preserve the original conversation')
        else:
            write_json(request_path, payload)
        self.save(active=f'model:{identifier}')
        if self.model_transport:
            result = self.model_transport(payload)
        else:
            request = urllib.request.Request(self.relay_url+'/chat/completions',
                data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout+30) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as error:
                detail = error.read(16384).decode('utf-8', errors='replace')
                write_json(path.with_name(f'{identifier}.error.json'), dict(status=error.code, detail=detail))
                raise RuntimeError(f'Model relay returned HTTP {error.code}: {detail}') from error
        write_json(path, result)
        if result['choices'][0].get('finish_reason') == 'length':
            raise RuntimeError('Truncated response preserved; not executed')
        return result

    def public_trial(self, evidence_id, *, admission=False):
        item = self.state['evidence'][evidence_id]
        if item['split'] != 'development' and not (admission and self.state['phase'] == 'skill_admission'
                and (self.root/'frozen_program.py').exists()):
            raise ValueError('Only development evidence may enter learning')
        directory = self.root/item['path']
        result = json.loads((directory/'result.json').read_text(encoding='utf-8'))
        # Exclude evaluator geometry, per-step evaluator feedback, assets and private state.
        public = {key:result[key] for key in ('seed', 'success', 'execution_ok', 'status', 'stdout', 'stderr') if key in result}
        public['success'] = bool(public.get('success') and public.get('execution_ok'))
        public['evidence_id'] = evidence_id
        if (directory/'trace.json').exists():
            public['trace'] = json.loads((directory/'trace.json').read_text(encoding='utf-8'))
        if evidence_id in self.state['vdms']:
            public['visual_difference'] = self.state['vdms'][evidence_id]
        return public, directory

    def visual_difference(self, evidence_id, *, initial=False):
        key = 'initial_scene' if initial else evidence_id
        if key in self.state['vdms']:
            return self.state['vdms'][key]
        _, directory = self.public_trial(evidence_id)
        setup_paths()
        from aspire.sim.cap.envs import trial
        from aspire.sim.cap.llm.client import ModelQueryArgs
        # Use upstream builders exactly; route their query through the durable request ledger.
        original = trial._query_model
        def query(args, prompt):
            reply = self.request('vdm_'+key, dict(model=self.model, max_tokens=128000, messages=prompt))
            return reply['choices'][0]['message']
        trial._query_model = query
        try:
            args = ModelQueryArgs(model=self.model, server_url=self.relay_url+'/chat/completions', api_key=None)
            task = f'Pick the {self.task.target} and place it in its designated tray lane.'
            if initial:
                value = trial._describe_initial_scene(args, task, image_url(directory/'initial/top.png'),
                                                      image_url(directory/'initial/wrist.png'))
            else:
                value = trial._get_visual_differencing_feedback(args, task,
                    [image_url(directory/f'{stage}/top.png') for stage in ('initial', 'final')],
                    [image_url(directory/f'{stage}/wrist.png') for stage in ('initial', 'final')])
        finally:
            trial._query_model = original
        self.state['vdms'][key] = value
        self.save()
        return value

    def propose(self, identifier, instruction, evidence_ids, parents, count, *, evolution=False, admission=False):
        if admission and (count != 0 or self.state['phase'] != 'skill_admission'):
            raise ValueError('Held-out inspection is only allowed for post-freeze findings, never program generation')
        output = self.root/'proposals'/f'{identifier}.json'
        if output.exists():
            return json.loads(output.read_text(encoding='utf-8'))
        runbook = (EVO if evolution else FIX)/'subagent-prompt.md'
        skills = self.library.context()
        skills['shared_skills'] = self.inherited_skills
        references = '\n\n'.join((FIX/'skills'/f'{name}.md').read_text(encoding='utf-8')
                                  for name in ('grasp', 'localize', 'transport', 'manipulation'))
        public = [self.public_trial(eid, admission=admission)[0] for eid in evidence_ids]
        for row in public:
            row['trace_entries'] = len(row.pop('trace', []))
        text = dict(instruction=instruction, expected_programs=count, parents=parents,
                    evidence=public, learned_skills=skills, initial_scene=self.state['vdms'].get('initial_scene'))
        content = [dict(type='text', text=json.dumps(text))]
        messages = [dict(role='system', content=self.binding()),
                    dict(role='user', content=runbook.read_text(encoding='utf-8')),
                    dict(role='user', content='Upstream skill references (verbatim):\n'+references),
                    dict(role='user', content='Surgical public API:\n'+self.api_prompt()),
                    dict(role='user', content=content)]
        write_json(self.root/'model'/f'{identifier}.retrieval.json', skills)
        # Agent-directed inspection, with a bounded conversation and one schema correction.
        corrections = 0
        for attempt in range(10):
            response = self.request(f'{identifier}_{attempt}', dict(model=self.model, max_tokens=128000,
                messages=messages, tools=[SUBMIT_TOOL, INSPECT_TOOL], tool_choice='required'))
            message = response['choices'][0]['message']
            calls = message.get('tool_calls', [])
            if calls and all(call['function']['name'] == 'inspect_evidence' for call in calls):
                messages.append(dict(message, role='assistant'))
                inspection_path = self.root/'model'/f'{identifier}_{attempt}.inspection.json'
                if inspection_path.exists():
                    inspected = json.loads(inspection_path.read_text(encoding='utf-8'))
                    if (len(inspected) != len(calls) or any(row.get('role') != 'tool' or
                            row.get('tool_call_id') != call['id'] for row, call in zip(inspected, calls))):
                        raise ValueError('Cached inspection does not match the model tool calls')
                    messages.extend(inspected)
                else:
                    for call in calls:
                        try:
                            arguments = json.loads(call['function']['arguments'])
                            result = inspect(self, arguments, evidence_ids, admission=admission)
                        except (ValueError, KeyError, TypeError) as error:
                            result = [dict(type='text', text=json.dumps(dict(error=str(error))))]
                        messages.append(dict(role='tool', tool_call_id=call['id'], content=result))
                    write_json(inspection_path, messages[-len(calls):])
                continue
            try:
                if len(calls) != 1 or calls[0]['function']['name'] != 'submit_practice':
                    raise ValueError('Expected one submit_practice tool call')
                value = json.loads(calls[0]['function']['arguments'])
                if not isinstance(value['analysis'], str) or len(value['programs']) != count:
                    raise ValueError(f'Expected analysis and {count} programs')
                # Candidate A is inserted by the host in the first population;
                # B-H must also be distinct from that verbatim baseline.
                hashes = {digest(parents[0]['code'])} if evolution and count == 7 else set()
                for program in value['programs']:
                    validate_sensor_program(program['code'])
                    if digest(program['code']) in hashes:
                        raise ValueError('Duplicate candidate programs')
                    hashes.add(digest(program['code']))
                    if not program['hypothesis'].strip():
                        raise ValueError('Candidate lacks a mechanistic hypothesis')
                for note in value['skills']:
                    if not note.get('evidence_ids') or not set(note['evidence_ids']) <= set(evidence_ids):
                        raise ValueError('Skill notes must cite supplied development evidence IDs')
                # A final consolidation must leave evidence-linked lessons even if all attempts failed.
                if count == 0 and evidence_ids and not value['skills']:
                    raise ValueError('Consolidation must record evidence-linked findings, including failures')
                break
            except (ValueError, KeyError, TypeError, SyntaxError) as error:
                if corrections:
                    raise
                corrections += 1
                # Keep the malformed reply in its artifact; request a complete corrected submission.
                messages.append(dict(role='user', content=f'Submission rejected: {error}. Resubmit the complete requested payload.'))
        else:
            raise RuntimeError('Actor inspection turn limit reached; evidence preserved, no program executed')
        # Final findings may cite held-out evidence; they are not actor working memory.
        if not admission:
            self.library.learn(value['skills'], evidence_ids, identifier)
        write_json(output, value)
        (self.root/'task_analysis.md').write_text(value['analysis'], encoding='utf-8')
        return value

    def consolidate(self, pool, selected, heldout):
        evidence = list(dict.fromkeys(row['evidence_id'] for candidate in pool for row in candidate['rows']))
        evidence += [row['evidence_id'] for row in heldout['rows']]
        findings = self.propose('consolidation',
            'The selected program is frozen and held-out evaluation has finished. No new programs or repairs. '
            'Report failure modes, demonstrated repairs, transferable patterns, task-specific quirks, and actual '
            'debug and held-out success rates. Each reusable skill candidate must include a structured pattern '
            '(failure_signature, applicability, repair_strategy, complete code_sketch, limitations), and cite '
            'both failed and successfully repaired DEVELOPMENT replays. Held-out traces may qualify limitations '
            'but cannot establish a debugging repair. Do not propose unverified hypotheses as validated skills. '
            'If no reusable repair was demonstrated, save only a candid Markdown finding without a pattern.',
            evidence, [dict(id=selected['id'], code=selected['code'])], 0, evolution=True, admission=True)
        candidates = []
        for index, note in enumerate(findings['skills']):
            if 'pattern' not in note:
                continue
            refs = note['evidence_ids']
            debug = [self.public_trial(eid)[0] for eid in refs if self.state['evidence'][eid]['split'] == 'development']
            pairs = []
            for failed in debug:
                for repaired in debug:
                    if failed['success'] or not repaired['success'] or failed['seed'] != repaired['seed']:
                        continue
                    def code_sha(eid):
                        path = self.root/self.state['evidence'][eid]['path']
                        return json.loads((path/'result.json').read_text(encoding='utf-8'))['program_sha256']
                    if code_sha(failed['evidence_id']) != code_sha(repaired['evidence_id']):
                        pairs.append(dict(failed=failed['evidence_id'], repaired=repaired['evidence_id'], seed=failed['seed']))
            error = None
            try:
                for field in PATTERN_SCHEMA['required']:
                    if not isinstance(note['pattern'].get(field), str) or not note['pattern'][field].strip():
                        raise ValueError('Incomplete structured pattern')
                validate_sensor_program(note['pattern']['code_sketch'])
                if not pairs:
                    raise ValueError('No cited failure-to-success debugging replay with changed code on the same seed')
            except (ValueError, SyntaxError) as exc:
                error = str(exc)
            candidates.append(dict(candidate=index, pattern=note['pattern'], findings=note['markdown'],
                debug_repair_pairs=pairs, eligibility_error=error))
        eligible = [row for row in candidates if row['eligibility_error'] is None]
        decisions = []
        if eligible:
            # Independent coordinator context: findings and verified outcomes, no actor chat or raw trajectories.
            reply = self.request('coordinator_review', dict(model=self.model, max_tokens=128000, messages=[
                dict(role='system', content=self.binding()),
                dict(role='user', content=(FIX/'main-agent-prompt.md').read_text(encoding='utf-8')),
                dict(role='user', content='Additional surgical coordinator context: actor work and evaluation are complete. '
                    'Audit the structured findings for reusable, debug-validated repairs and allowed API compliance. '
                    'Do not generate or repair task programs. Reject task-instance coordinates, seed-specific tricks, '
                    'unverified claims, and whole-task programs disguised as skills. Cross-task transfer remains '
                    'untested. Return one decision for each candidate.\n'+json.dumps(dict(candidates=eligible,
                        development=dict(successes=selected['success_count'], trials=len(selected['rows'])),
                        heldout=dict(successes=heldout['success_count'], trials=len(heldout['rows'])))))],
                tools=[REVIEW_TOOL], tool_choice=dict(type='function', function=dict(name='review_skills'))))
            calls = reply['choices'][0]['message'].get('tool_calls', [])
            if len(calls) != 1 or calls[0]['function']['name'] != 'review_skills':
                raise ValueError('Expected one coordinator review')
            decisions = json.loads(calls[0]['function']['arguments'])['decisions']
            if (len(decisions) != len(eligible) or {d['candidate'] for d in decisions} != {c['candidate'] for c in eligible}
                    or any(type(d.get('admit')) is not bool or not d.get('reason', '').strip() for d in decisions)):
                raise ValueError('Incomplete coordinator decisions')
        admitted = []
        for decision in decisions:
            if not decision['admit']:
                continue
            candidate = next(row for row in eligible if row['candidate'] == decision['candidate'])
            admitted.append(self.shared.admit(candidate['pattern'], review=decision,
                provenance=dict(campaign=str(self.root), task=self.task.target, backend=self.task.perception_backend,
                    protocol=self.plan['protocol'], debug_repair_pairs=candidate['debug_repair_pairs'],
                    selected_program_sha256=selected['sha256'], heldout_successes=heldout['success_count'],
                    heldout_trials=len(heldout['rows']))))
        write_json(self.root/'skill_admission.json', dict(candidates=candidates, decisions=decisions, admitted=admitted))
        self.save(admitted_skills=admitted)

    def trial(self, identifier, code, seed, split):
        directory = self.root/'trials'/identifier
        source = directory.parent/f'{identifier}.py'
        source.parent.mkdir(exist_ok=True)
        if source.exists() and source.read_text(encoding='utf-8') != code:
            raise ValueError('Refusing to change a previously attempted program')
        source.write_text(code, encoding='utf-8')
        result_path = directory/'result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding='utf-8'))
            finished = result.get('status') in ('completed', 'program_error')
            if (result.get('program_sha256', None if finished else digest(code)) != digest(code)
                    or result.get('seed') != seed):
                raise ValueError('Saved trial identity mismatch')
            if not finished:
                recovered = None
                for retry_result in sorted(directory.glob('attempt_*/result.json'), reverse=True):
                    saved = json.loads(retry_result.read_text(encoding='utf-8'))
                    if saved.get('status') in ('completed', 'program_error'):
                        if saved.get('program_sha256') != digest(code) or saved.get('seed') != seed:
                            raise ValueError('Saved retry identity mismatch')
                        recovered = saved
                        retry_directory = retry_result.parent
                        break
                if recovered is None:
                    attempt = 1
                    while ((directory/f'result.attempt{attempt:03d}.json').exists() or
                           (directory/f'attempt_{attempt:03d}').exists()):
                        attempt += 1
                    (directory/f'result.attempt{attempt:03d}.json').write_text(
                        result_path.read_text(encoding='utf-8'), encoding='utf-8')
                    self.save(active=f'trial:{identifier}:retry{attempt:03d}')
                    retry_directory = directory/f'attempt_{attempt:03d}'
                    recovered = self.trial_runner(self.launcher, source, self.config, seed, retry_directory,
                                                  headless=self.headless, wall_timeout=600)
                result = dict(recovered, evidence_path=str(retry_directory.relative_to(self.root)))
                write_json(result_path, result)
        else:
            self.save(active=f'trial:{identifier}')
            result = self.trial_runner(self.launcher, source, self.config, seed, directory,
                                       headless=self.headless, wall_timeout=600)
        if result['status'] not in ('completed', 'program_error'):
            raise RuntimeError(f'Infrastructure failure at {identifier}: {result["status"]}; repair before resuming')
        # Program errors are genuine failures even if a last motion happened to trip the reward.
        result['success'] = bool(result.get('success') and result.get('execution_ok'))
        result['evidence_id'] = identifier
        evidence_directory = (self.root/result.get('evidence_path', str(directory.relative_to(self.root)))).resolve()
        if not evidence_directory.is_relative_to(directory.resolve()):
            raise ValueError('Saved evidence path is outside the trial directory')
        self.state['evidence'][identifier] = dict(path=str(evidence_directory.relative_to(self.root)), split=split)
        self.save()
        return result

    def cohort(self, identifier, source, split='development'):
        partition = dict(development='development_seeds', heldout='evaluation_seeds')[split]
        seeds = self.protocol[partition]
        limit_path = self.root/'evaluation_limit.json'
        if split == 'heldout' and limit_path.exists():
            seeds = json.loads(limit_path.read_text(encoding='utf-8'))['evaluation_seeds']
        if identifier in self.state['cohorts']:
            saved = self.state['cohorts'][identifier]
            if (saved['sha256'] != digest(source) or saved['split'] != split
                    or [row['seed'] for row in saved['rows']] != seeds):
                raise ValueError('Cohort identity mismatch')
            return saved
        rows = [self.trial(f'{identifier}_s{seed}', source, seed, split) for seed in seeds]
        value = dict(id=identifier, code=source, sha256=digest(source), split=split,
                     success_count=sum(row['success'] for row in rows), rows=rows)
        self.state['cohorts'][identifier] = value
        if split == 'development':
            self.library.record_program(source, rows, identifier)
        self.save()
        return value

    @staticmethod
    def rank(pool):
        # Simplicity tie break, as in upstream Evolutionary Search.
        return sorted(pool, key=lambda row: (-row['success_count'],
            sum(bool(line.strip()) and not line.lstrip().startswith('#') for line in row['code'].splitlines()), row['id']))

    def diagnose(self, cohort):
        rows = cohort['rows']
        representative = next((row for row in rows if not row['success']), rows[0])
        return self.visual_difference(representative['evidence_id'])

    def run(self, *, smoke_only=False, pause_after_round=None, evaluate_after_round=None, heldout_trials=None,
            revise_heldout_limit=False):
        if pause_after_round is not None and (type(pause_after_round) is not int or not 0 <= pause_after_round < self.plan['T']):
            raise ValueError('pause_after_round must be a zero-based round from 0 to 2')
        evaluation_path = self.root/'evaluation_plan.json'
        if evaluation_path.exists():
            boundary = json.loads(evaluation_path.read_text(encoding='utf-8'))['evaluate_after_round']
            if evaluate_after_round is not None and evaluate_after_round != boundary:
                raise ValueError('Evaluation boundary changed after selection')
            evaluate_after_round = boundary
        if evaluate_after_round is not None:
            if type(evaluate_after_round) is not int or not 0 <= evaluate_after_round < self.plan['T']:
                raise ValueError('evaluate_after_round must be a zero-based round from 0 to 2')
            if smoke_only or pause_after_round is not None:
                raise ValueError('Direct evaluation cannot be combined with smoke or pause')
        if self.state['status'] == 'stopped_backend_switch':
            raise RuntimeError('This campaign was retired after a perception-backend change; use a fresh campaign')
        self._set_heldout_limit(heldout_trials, smoke_only=smoke_only, pause_after_round=pause_after_round,
                                revise=revise_heldout_limit)
        if self.state['status'] in ('completed', 'unsolved'):
            return self.state
        if self.state['status'] == 'paused' and pause_after_round is not None:
            if (self.state['completed_round'] >= pause_after_round or self.state['next_phase'] == 'selection'):
                return self.state
        try:
            if evaluate_after_round is not None:
                return self._run_evaluation(evaluate_after_round)
            return self._run(smoke_only=smoke_only, pause_after_round=pause_after_round)
        except Exception as error:
            self.save(status='blocked', error_type=type(error).__name__, error=str(error))
            raise

    def _set_heldout_limit(self, trials, *, smoke_only=False, pause_after_round=None, revise=False):
        planned = self.protocol['evaluation_seeds']
        if trials is not None and (type(trials) is not int or not 1 <= trials <= len(planned)):
            raise ValueError('heldout_trials must be an integer within the planned evaluation count')
        if revise and trials is None:
            raise ValueError('Revising a held-out limit requires an explicit trial count')
        limit_path = self.root/'evaluation_limit.json'
        saved = None
        if limit_path.exists():
            saved = json.loads(limit_path.read_text(encoding='utf-8'))
            previous_trials = saved['heldout_trials']
            if type(previous_trials) is not int or not 1 <= previous_trials <= len(planned):
                raise ValueError('Saved held-out trial limit is outside the planned evaluation count')
            if saved['evaluation_seeds'] != planned[:previous_trials]:
                raise ValueError('Saved held-out seeds differ from the planned prefix')
            if trials is None:
                trials = previous_trials
            elif trials != previous_trials:
                if not revise:
                    raise ValueError('Held-out trial limit changed after it was saved')
                if trials > previous_trials:
                    raise ValueError('An explicit held-out revision can only reduce the trial count')
        elif revise:
            raise ValueError('Revising a held-out limit requires a saved limit')
        if trials is None:
            return
        if smoke_only or pause_after_round is not None:
            raise ValueError('A held-out limit cannot be combined with smoke or pause')
        selection_path = self.root/'selection.json'
        if not selection_path.exists():
            raise ValueError('A held-out limit requires an already frozen evaluation program')
        selection = json.loads(selection_path.read_text(encoding='utf-8'))
        if saved is not None:
            if saved['selected_program_sha256'] != selection['sha256']:
                raise ValueError('Held-out trial limit belongs to a different frozen program')
        if saved is None or trials != saved['heldout_trials']:
            if self.state['status'] in ('completed', 'unsolved') or 'heldout' in self.state['cohorts']:
                raise ValueError('Cannot truncate a completed evaluation')
            result_paths = {self.root/evidence['path']/'result.json'
                            for evidence in self.state['evidence'].values() if evidence['split'] == 'heldout'}
            result_paths.update((self.root/'trials').glob('heldout_s*/result.json'))
            result_paths.update((self.root/'trials').glob('heldout_s*/attempt_*/result.json'))
            completed = set()
            for path in sorted(result_paths):
                result = json.loads(path.read_text(encoding='utf-8'))
                if result['status'] in ('completed', 'program_error'):
                    if result['seed'] not in planned[:trials]:
                        raise ValueError('Trial limit would discard an already completed held-out outcome')
                    if result['program_sha256'] != selection['sha256']:
                        raise ValueError('Completed held-out outcome belongs to a different frozen program')
                    completed.add(result['seed'])
            updated = dict(mode='user_requested_trial_limit', heldout_trials=trials,
                planned_trial_count=len(planned), evaluation_seeds=planned[:trials],
                selected_program_sha256=selection['sha256'], completed_seeds_before_change=sorted(completed),
                active_before_change=self.state.get('active'), requested_at_utc=datetime.now(timezone.utc).isoformat())
            if saved is not None:
                previous_bytes = limit_path.read_bytes()
                previous_hash = hashlib.sha256(previous_bytes).hexdigest()
                archive = self.root/'control/evaluation_limits'/f'limit_{saved["heldout_trials"]}_{previous_hash}.json'
                archive.parent.mkdir(parents=True, exist_ok=True)
                if archive.exists() and archive.read_bytes() != previous_bytes:
                    raise ValueError('Previous held-out limit archive was changed')
                archive.write_bytes(previous_bytes)
                updated.update(previous_trial_count=saved['heldout_trials'],
                    previous_limit_archive=str(archive.relative_to(self.root)), previous_limit_sha256=previous_hash)
            write_json(limit_path, updated)
        self.state['heldout_trial_limit'] = trials

    def _run_evaluation(self, after_round):
        names = ['fix_initial'] + [f'fix_{index:02d}' for index in range(self.plan['fix_refinements'])
                                  if f'fix_{index:02d}' in self.state['cohorts']]
        names.extend(f'evo_{iteration:02d}_{chr(65+index)}'
                     for iteration in range(after_round+1) for index in range(self.plan['K']))
        if self.state.get('completed_round', -1) < after_round or any(name not in self.state['cohorts'] for name in names):
            raise ValueError('Direct evaluation requires complete development rounds through the requested boundary')
        pool = [self.state['cohorts'][name] for name in names]
        for candidate in pool:
            if (candidate['split'] != 'development' or candidate['sha256'] != digest(candidate['code'])
                    or sorted(row['seed'] for row in candidate['rows']) != self.protocol['development_seeds']
                    or candidate['success_count'] != sum(bool(row['success']) for row in candidate['rows'])):
                raise ValueError('Direct evaluation requires intact complete development cohorts')
        evaluation_path = self.root/'evaluation_plan.json'
        if not evaluation_path.exists():
            if (self.root/'selection.json').exists() or any(row['split'] == 'heldout' for row in self.state['evidence'].values()):
                raise ValueError('Cannot change the search boundary after evaluation was frozen or started')
            write_json(evaluation_path, dict(mode='user_requested_early_evaluation',
                evaluate_after_round=after_round, planned_rounds=self.plan['T'],
                skipped_rounds=list(range(after_round+1, self.plan['T'])), selection_cohorts=names,
                excluded_development_evidence=[name for name in self.state['evidence']
                    if any(name.startswith(f'evo_{iteration:02d}_') for iteration in range(after_round+1, self.plan['T']))]))
        elif json.loads(evaluation_path.read_text(encoding='utf-8'))['selection_cohorts'] != names:
            raise ValueError('Development selection pool changed after the evaluation boundary was saved')
        self.save(status='running', phase='selection', active=None, evaluate_after_round=after_round,
                  next_round=None, next_phase=None, pause_after_round=None, pause_reason=None)
        fixed = self.rank([row for row in pool if row['id'].startswith('fix_')])[0]
        return self._evaluate(pool, fixed)

    def _run(self, *, smoke_only=False, pause_after_round=None):
        self.save(status='running', phase='exploration', pause_after_round=pause_after_round,
                  next_round=None, next_phase=None, pause_reason=None)
        seed = self.protocol['development_seeds'][0]
        # Motionless observation bootstrap; no external hand-authored manipulation baseline.
        bootstrap = "obs = get_observation()\nprint(get_robot_state())\nprint(get_tray_slot())\n"
        probe = self.trial('observe', bootstrap, seed, 'development')
        evidence = ['observe']
        current = bootstrap
        for index in range(5):
            name = f'explore_{index:02d}'
            submission = self.propose(name,
                f'Stage 0 exploration block {index}/4. Extend or revise the accumulated program after inspecting the previous replay. '
                'Return ONE complete cumulative program, with # Code block N sections. Every replay starts from reset. '
                'Use this block to gather useful sensor evidence or advance the task, guided by observed results.',
                evidence, [dict(id='current', code=current)], 1)
            current = submission['programs'][0]['code']
            row = self.trial(name, current, seed, 'development')
            evidence.append(name)
            if smoke_only:
                self.save(status='prepared', phase='exploration_smoke_complete', active=None)
                return self.state
            if row['success']:
                break
        self.save(phase='fix_loop')
        fixed = self.cohort('fix_initial', current)
        fix_pool = [fixed]
        for index in range(self.plan['fix_refinements']):
            if fixed['success_count'] == len(self.protocol['development_seeds']):
                break
            evidence = [row['evidence_id'] for candidate in fix_pool for row in candidate['rows']]
            proposal = self.propose(f'fix_{index:02d}',
                'Stage 1 Fix Loop. Diagnose failed development trials and write ONE generalizable standalone repair. '
                'It will be replayed on every development seed, including previous successes. Update reusable skill notes.',
                evidence, [dict(id=row['id'], code=row['code']) for row in self.rank(fix_pool)[:3]], 1)
            fixed = self.cohort(f'fix_{index:02d}', proposal['programs'][0]['code'])
            fix_pool.append(fixed)
        fixed = self.rank(fix_pool)[0]
        (self.root/'fix_code.py').write_text(fixed['code'], encoding='utf-8')
        write_json(self.root/'fix_result.json', dict(selected=fixed['id'],
            success_count=fixed['success_count'], trial_count=len(fixed['rows'])))
        self.save(phase='evolutionary_search')
        pool = list(fix_pool)
        completed_round = -1
        for iteration in range(3):
            leaders = self.rank(pool)[:3]
            # Always evaluate a complete first K population, even if Fix Loop solved all dev seeds.
            if iteration and leaders[0]['success_count'] == len(self.protocol['development_seeds']):
                break
            # Algorithm 1 supplies the history as well as the top-three parents.
            evidence = list(dict.fromkeys(row['evidence_id'] for candidate in pool for row in candidate['rows']))
            proposed_count = 7 if iteration == 0 else 8
            proposal = self.propose(f'evo_{iteration:02d}',
                'Stage 1 Evolutionary Search. Write '+str(proposed_count)+' structurally distinct candidate programs. '
                + ('The host will copy fix_code.py verbatim as candidate A; submit candidates B-H.' if iteration == 0 else
                   'Use the top-three survivors and retain at least one structurally novel hypothesis.')
                + ' Each program needs a hypothesis docstring, parent, differences and expected falsifying trace evidence. '
                'Diagnose prior failures and update reusable skills. Do not make eight small parameter variations.',
                evidence, [dict(id=row['id'], code=row['code']) for row in leaders], proposed_count, evolution=True)
            programs = proposal['programs']
            if iteration == 0:
                programs = [dict(code=fixed['code'], hypothesis='Verbatim Fix Loop baseline', parent=fixed['id'])] + programs
            iteration_rows = []
            for index, program in enumerate(programs):
                name = f'evo_{iteration:02d}_{chr(65+index)}'
                write_json(self.root/'lineage'/f'{name}.json', program)
                candidate = self.cohort(name, program['code'])
                iteration_rows.append(candidate)
            pool.extend(iteration_rows)
            write_json(self.root/f'iter_{iteration:02d}_summary.json', [dict(id=row['id'],
                success_count=row['success_count'], sha256=row['sha256']) for row in self.rank(iteration_rows)])
            completed_round = iteration
            self.save(completed_round=iteration)
            if pause_after_round is not None and iteration >= pause_after_round:
                self.save(status='paused', phase='evolutionary_search_paused', active=None,
                          pause_after_round=pause_after_round, completed_round=iteration,
                          next_round=iteration+1 if iteration+1 < self.plan['T'] else None,
                          next_phase='evolutionary_search' if iteration+1 < self.plan['T'] else 'selection')
                return self.state
        if pause_after_round is not None:
            self.save(status='paused', phase='evolutionary_search_paused', active=None,
                      pause_after_round=pause_after_round, completed_round=completed_round,
                      next_round=None, next_phase='selection', pause_reason='development_solved')
            return self.state
        return self._evaluate(pool, fixed)

    def _evaluate(self, pool, fixed):
        selected = self.rank(pool)[0]
        frozen = self.root/'frozen_program.py'
        selection_path = self.root/'selection.json'
        skills_path = self.root/'frozen_skills.json'
        selection = dict(id=selected['id'], sha256=selected['sha256'],
            development_successes=selected['success_count'], selection_uses='development_only')
        if selection_path.exists():
            if json.loads(selection_path.read_text(encoding='utf-8')) != selection:
                raise ValueError('Refusing to reselect a program after the evaluation freeze')
            if not frozen.exists() or not skills_path.exists():
                raise ValueError('Frozen evaluation artifacts are missing')
        elif any(row['split'] == 'heldout' for row in self.state['evidence'].values()):
            raise ValueError('Held-out evidence exists without a selection freeze')
        if frozen.exists() and digest(frozen.read_text(encoding='utf-8')) != selected['sha256']:
            raise ValueError('Selected program changed after the evaluation freeze')
        if not selection_path.exists():
            frozen.write_text(selected['code'], encoding='utf-8')
            if not skills_path.exists():
                write_json(skills_path, self.library.context())
            write_json(selection_path, selection)
        frozen_skills = json.loads(skills_path.read_text(encoding='utf-8'))
        evaluation_path = self.root/'evaluation_plan.json'
        evaluation_plan = json.loads(evaluation_path.read_text(encoding='utf-8')) if evaluation_path.exists() else None
        limit_path = self.root/'evaluation_limit.json'
        evaluation_limit = json.loads(limit_path.read_text(encoding='utf-8')) if limit_path.exists() else None
        if not selected['success_count']:
            (self.root/'findings.md').write_text(
                f'# {self.task.target.replace("_", " ").title()} ASPIRE findings\n\nNo development program succeeded. '
                'Held-out evaluation was skipped (Appendix E.4). No validated skills were admitted. '
                'See task_analysis.md, proposals and development traces for failed hypotheses.\n', encoding='utf-8')
            self.save(status='unsolved', phase='search_exhausted', active=None,
                      reason='All development programs failed; Appendix E.4 skips held-out evaluation')
            return self.state
        self.save(phase='heldout_evaluation', selected=selected['id'])
        final = self.cohort('heldout', selected['code'], 'heldout')
        if digest(frozen.read_text(encoding='utf-8')) != selected['sha256']:
            raise RuntimeError('Selected program changed after the evaluation freeze')
        self.save(phase='skill_admission')
        self.consolidate(pool, selected, final)
        write_json(self.root/'report.json', dict(status='completed', final_success_count=final['success_count'],
            final_trial_count=len(final['rows']), selected_program_sha256=selected['sha256'],
            skill_sha256=frozen_skills['sha256'], notes=len(self.library.read()['notes']),
            programs=len(self.library.read()['programs']), plan=self.plan, evaluation_plan=evaluation_plan,
            evaluation_limit=evaluation_limit))
        findings = (f"# {self.task.target.replace('_', ' ').title()} ASPIRE findings\n\n"
            f"Fix Loop: {fixed['success_count']}/{len(fixed['rows'])} development successes.\n\n"
            f"Selected program: {selected['id']} ({selected['sha256']}).\n\n"
            f"Development: {selected['success_count']}/{len(selected['rows'])}. "
            f"Held-out evaluation: {final['success_count']}/{len(final['rows'])}.\n\n"
            f"Skills: {len(self.library.read()['notes'])} evidence-linked notes; "
            f"{len(self.library.read()['programs'])} programs with at least one successful development replay. "
            "Partial success is not a claim of generalization.\n\n"
            "See task_analysis.md and skills/index.json for diagnoses, evidence and remaining limitations. "
            "See plan.json for all protocol substitutions.\n")
        if evaluation_plan is not None:
            findings += (f"\nUser-requested early evaluation after round {evaluation_plan['evaluate_after_round']}; "
                         f"skipped rounds: {evaluation_plan['skipped_rounds']}. "
                         "Later-round evidence is excluded from selection. This is not a complete T=3 search.\n")
        if evaluation_limit is not None:
            findings += (f"\nUser-requested held-out limit: {len(final['rows'])}/"
                         f"{evaluation_limit['planned_trial_count']} planned trials, using the fixed seed prefix. "
                         "This is a reduced evaluation, not the full planned benchmark.\n")
        (self.root/'findings.md').write_text(findings, encoding='utf-8')
        self.save(status='completed', phase='completed', active=None)
        return self.state



