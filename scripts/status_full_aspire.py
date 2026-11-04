"""Print progress without exposing request contents or credentials."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    root = Path(args.directory)
    state = json.loads((root/'state.json').read_text(encoding='utf-8'))
    contract = json.loads((root/'contract.json').read_text(encoding='utf-8'))
    reports = [json.loads(path.read_text()) for path in sorted(root.glob('provider_*/report.json'))]
    skills = json.loads((root/'skills/index.json').read_text(encoding='utf-8'))
    usage = [json.loads(path.read_text()).get('usage') or {} for path in root.glob('provider_*/*.usage.json')]
    total = reports[-1]['total_requests'] if reports else None
    result = dict(status=state['status'], phase=state['phase'], active=state.get('active'),
        completed_trials=len(state['evidence']), completed_cohorts=len(state['cohorts']),
        successful_trials=sum(row['success'] for cohort in state['cohorts'].values() for row in cohort['rows']),
        provider_attempts_here=sum(row['requests'] for row in reports), cumulative_provider_attempts=total,
        pending_requests=reports[-1]['pending'] if reports else 0,
        historical_pending_attempts=sum(row['pending'] for row in reports[:-1]),
        completed_round=state.get('completed_round'), next_round=state.get('next_round'),
        next_phase=state.get('next_phase'), pause_after_round=state.get('pause_after_round'),
        evaluate_after_round=state.get('evaluate_after_round'),
        heldout_completed=sum(row['split'] == 'heldout' for row in state['evidence'].values()),
        heldout_target=state.get('heldout_trial_limit', len(contract['evaluation_seeds'])),
        reported_input_tokens=sum(row.get('prompt_tokens', 0) for row in usage),
        reported_output_tokens=sum(row.get('completion_tokens', 0) for row in usage),
        working_notes=len(skills['notes']), saved_programs=len(skills['programs']),
        admitted_reusable_skills=len(state.get('admitted_skills', [])),
        error=state.get('error'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
