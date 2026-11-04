"""Run six local scissors development trials; never contact an LLM provider."""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import ROOT, setup_paths
setup_paths()
from src.aspire.artifacts import write_json
from src.aspire.campaign import run_trial
from src.aspire.config import load_protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--initial-trial')
    parser.add_argument('--python', default=r'C:\isaac-sim-450\python.bat')
    args = parser.parse_args()
    directory = Path(args.out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    protocol, _ = load_protocol(ROOT/'configs/aspire/translated/scissor-sam3.json')
    protocol.update(development_seeds=list(range(501, 507)),
                    validation_seeds=list(range(551, 555)), evaluation_seeds=list(range(601, 611)))
    config = directory/'protocol.json'
    write_json(config, protocol)
    source = (ROOT/'examples/aspire/translated/scissor.py').read_text(encoding='utf-8')
    code = directory/'starting_program.py'
    code.write_text(source, encoding='utf-8')
    digest = hashlib.sha256(source.encode()).hexdigest()
    summary = dict(status='baseline_running', target='scissor', perception='sam3',
        information_condition='evaluator-assisted', initial_program_sha256=digest,
        final_evaluation_run=False, final_seeds_reserved=protocol['evaluation_seeds'],
        limitations=['Seed-generated scenes; exact physical scene replay is not implemented.',
                     'Placement evaluator is unchanged; no separate validated two-second hold score.',
                     'Single generation campaign; engineering pilot, not a transfer study.'])
    write_json(directory/'summary.json', summary)
    baseline, evidence = [], {}
    try:
        with urllib.request.urlopen(protocol['task']['sam3_url']+'/health', timeout=10) as response:
            health = json.load(response)
        write_json(directory/'perception_health.json', health)
        if not health.get('ready'):
            raise RuntimeError('SAM3 service is not ready')
        for seed in protocol['development_seeds']:
            trial = directory/f'baseline_seed_{seed}'
            if seed == 501 and args.initial_trial:
                trial = Path(args.initial_trial).resolve()
                result = json.loads((trial/'result.json').read_text(encoding='utf-8'))
                prior, _ = load_protocol(trial/'contract.json')
                if result.get('seed') != seed or result.get('program_sha256') != digest or prior['task'] != protocol['task']:
                    raise ValueError('Initial trial does not match pilot seed, source and task')
            else:
                print(f'baseline seed {seed}: starting', flush=True)
                result = run_trial(args.python, code, config, seed, trial, wall_timeout=600.)
            baseline.append(result)
            evidence[seed] = trial
            write_json(directory/'baseline.json', dict(trial_count=len(baseline),
                success_count=sum(r['success'] for r in baseline), results=baseline,
                trial_directories=[str(p) for p in evidence.values()]))
            print(f'baseline seed {seed}: {result["status"]}, success={result["success"]}', flush=True)
        initialized = [p for p in evidence.values() if (p/'prompt.txt').exists()]
        summary.update(baseline_success_count=sum(r['success'] for r in baseline), baseline_trial_count=len(baseline),
                       initialized_trial_count=len(initialized))
        if not initialized:
            summary.update(status='stopped_before_refinement', reason='No development trial completed scene reset; fix infrastructure first.')
            return 1
        # Reset failures cannot be repaired by generated skill code. Preserve the
        # scheduled cases and diagnose infrastructure before selection/revisions.
        if len(initialized) != len(baseline):
            summary.update(status='stopped_before_refinement', reason='Development reset/startup failures require infrastructure repair before refinement.')
            return 1
        summary.update(status='local_development_completed',
                       reason='Review local development evidence before a separate refinement campaign.')
        return 0
    except Exception as error:
        summary.update(status='error', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        summary['elapsed_s'] = time.monotonic()-started
        write_json(directory/'summary.json', summary)
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
