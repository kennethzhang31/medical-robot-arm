"""Coordinator-owned, persistent repair skills, separate from actor working notes."""
import hashlib
import json
from pathlib import Path
from .artifacts import write_json
from .execution import validate_program

PATTERN_SCHEMA = dict(type='object', properties={
    key: dict(type='string') for key in
    ('failure_signature', 'applicability', 'repair_strategy', 'code_sketch', 'limitations')},
    required=['failure_signature', 'applicability', 'repair_strategy', 'code_sketch', 'limitations'],
    additionalProperties=False)

REVIEW_TOOL = dict(type='function', function=dict(name='review_skills',
    description='Coordinator audit of actor findings; admit only reusable repairs demonstrated by debugging replays.',
    parameters=dict(type='object', properties={'decisions': dict(type='array', items=dict(type='object',
        properties={'candidate': dict(type='integer'), 'admit': dict(type='boolean'), 'reason': dict(type='string')},
        required=['candidate', 'admit', 'reason'], additionalProperties=False))},
        required=['decisions'], additionalProperties=False)))


class SharedSkills:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)

    def context(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in sorted(self.root.glob('*.json'))]

    def admit(self, pattern, *, review, provenance):
        if not review.get('admit') or not review.get('reason', '').strip():
            raise ValueError('Coordinator approval with a reason is required')
        if not provenance.get('debug_repair_pairs'):
            raise ValueError('A successful debugging repair replay is required')
        for field in PATTERN_SCHEMA['required']:
            if not isinstance(pattern.get(field), str) or not pattern[field].strip():
                raise ValueError(f'Missing skill field: {field}')
        # Sketches must be syntactically complete and use the same allowed API policy.
        validate_program(pattern['code_sketch'])
        identifier = hashlib.sha256(json.dumps(dict(pattern=pattern, provenance=provenance), sort_keys=True).encode()).hexdigest()
        path = self.root/f'{identifier}.json'
        if not path.exists():
            write_json(path, dict(id=identifier, pattern=pattern, coordinator_review=review,
                provenance=provenance, status='debug_validated_repair', cross_task_transfer='not_yet_evaluated'))
            text = '\n\n'.join(f'## {key.replace("_", " ").title()}\n\n{value}' for key, value in pattern.items())
            path.with_suffix('.md').write_text(text+'\n', encoding='utf-8')
        return identifier
