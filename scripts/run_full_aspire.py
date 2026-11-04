"""Credential-owning supervisor for the full surgical ASPIRE learning workflow."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.aspire.bootstrap import setup_paths
setup_paths()
from src.aspire.artifacts import write_json
from src.aspire.full import FullCampaign, plan
from src.aspire.provider import load_credential
from src.aspire.relay import ProviderRelay
from src.aspire.recovery import SupervisorLock, audit_ledgers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT/'configs/aspire/full-scissor-sam3.json'))
    parser.add_argument('--out', required=True)
    parser.add_argument('--base-url', default='https://cgv.cs.nthu.edu.tw:9128/v1')
    parser.add_argument('--model', default='claude-secondary/claude-opus-4-6')
    parser.add_argument('--python', default=r'C:\isaac-sim-450\python.bat')
    parser.add_argument('--request-budget', type=int, default=10)
    parser.add_argument('--prior-requests', type=int, default=28)
    parser.add_argument('--max-total-requests', type=int, default=38)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--prepare-only', action='store_true', help='Run and save the motionless sensor bootstrap without model requests')
    parser.add_argument('--smoke', action='store_true', help='Execute the first full-workflow practice block, saving it for continuation')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--pause-after-round', type=int, choices=range(3),
                        help='Pause after a complete zero-based development round, before freezing or held-out evaluation')
    parser.add_argument('--recover-interrupted', action='store_true',
                        help='Acknowledge crash-interrupted attempts after verifying the previous supervisor is inactive')
    parser.add_argument('--evaluate-after-round', type=int, choices=range(3),
                        help='Skip remaining search and evaluate only complete development cohorts through this round')
    parser.add_argument('--heldout-trials', type=int, choices=range(1,101),
                        help='Campaign-local limit for an already frozen evaluation, using the planned seed prefix')
    parser.add_argument('--revise-heldout-limit', action='store_true',
                        help='Explicitly reduce a saved limit while preserving its history and every completed outcome')
    args = parser.parse_args()
    if args.evaluate_after_round is not None and (not args.resume or args.pause_after_round is not None
                                                or args.smoke or args.prepare_only or args.preflight):
        parser.error('--evaluate-after-round requires --resume and cannot be combined with other stage controls')
    if args.heldout_trials is not None and (not args.resume or args.pause_after_round is not None
                                          or args.smoke or args.prepare_only or args.preflight):
        parser.error('--heldout-trials requires --resume and cannot be combined with other stage controls')
    if args.revise_heldout_limit and args.heldout_trials is None:
        parser.error('--revise-heldout-limit requires an explicit --heldout-trials count')
    directory = Path(args.out).resolve()
    if not directory.is_relative_to(ROOT/'logs'):
        parser.error('All experiment output must be under the repository logs directory')
    if args.request_budget < 1 or args.prior_requests < 0 or args.prior_requests+args.request_budget > args.max_total_requests:
        parser.error('Request count exceeds the explicitly authorized total')
    configuration = plan(args.config)
    if args.preflight:
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory/'preflight_plan.json', configuration)
        print(json.dumps(configuration, indent=2))
        return 0
    if directory.exists() and not args.resume:
        parser.error('Use a fresh output directory or --resume')
    directory.mkdir(parents=True, exist_ok=True)
    with SupervisorLock(directory) as ownership:
        launch_path = directory/'launch.json'
        if launch_path.exists():
            previous = json.loads(launch_path.read_text(encoding='utf-8'))
            if previous['model'] != args.model or Path(previous['config']).resolve() != Path(args.config).resolve():
                parser.error('Resume model/config differs')
            if previous['headless'] != args.headless or Path(previous['python']).resolve() != Path(args.python).resolve():
                parser.error('Resume simulator/display differs')
        audit = audit_ledgers(directory, prior_requests=args.prior_requests,
                              recover_interrupted=args.recover_interrupted, previous_supervisor=ownership.previous)
        from src.aspire.perception import check_perception_service
        from src.aspire.config import load_protocol
        _, task = load_protocol(args.config)
        perception_health = check_perception_service(task)
        write_json(directory/'perception_health.json', perception_health)
        if not load_credential(ROOT/'.env', 'API_KEY'):
            raise RuntimeError('Missing API_KEY')
        if not launch_path.exists():
            write_json(launch_path, vars(args))
        provider_dir = directory/audit['next_ledger']
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        if audit['unrecovered_pending']:
            checkpoint = json.loads((directory/'state.json').read_text(encoding='utf-8'))
            write_json(directory/'recoveries'/f'recovery_{stamp}.json', dict(
                recovered_at_utc=datetime.now(timezone.utc).isoformat(),
                previous_supervisor=ownership.previous, pending_ledgers=audit['unrecovered_pending'],
                checkpoint={key:checkpoint.get(key) for key in ('status', 'phase', 'active', 'updated_at_utc')},
                prior_requests=args.prior_requests, max_total_requests=args.max_total_requests,
                replacement_ledger=audit['next_ledger']))
        write_json(directory/'launches'/f'launch_{provider_dir.name.removeprefix("provider_")}.json', vars(args))
        supervisor = dict(pid=os.getpid(), status='running', started_at_utc=datetime.now(timezone.utc).isoformat(),
                          provider_ledger=provider_dir.name, pause_after_round=args.pause_after_round,
                          evaluate_after_round=args.evaluate_after_round, heldout_trials=args.heldout_trials,
                          revise_heldout_limit=args.revise_heldout_limit)
        write_json(directory/'supervisor.json', supervisor)
        try:
            with ProviderRelay(provider_dir, base_url=args.base_url, model=args.model,
                               credential=os.environ['API_KEY'], request_budget=args.request_budget,
                               prior_requests=args.prior_requests, timeout=1800, max_output_tokens=128000,
                               upstream_stream=True, native_messages=True) as relay:
                campaign = FullCampaign(directory, args.config, relay_url=relay.url,
                    model=args.model, launcher=args.python, headless=args.headless)
                campaign.save(provider_base_url=args.base_url, pause_after_round=args.pause_after_round)
                if args.prepare_only:
                    campaign.trial('observe', "obs = get_observation()\nprint(get_robot_state())\nprint(get_tray_slot())\n",
                                   campaign.protocol['development_seeds'][0], 'development')
                    campaign.save(status='prepared', phase='preflight', active=None)
                else:
                    campaign.run(smoke_only=args.smoke, pause_after_round=args.pause_after_round,
                                 evaluate_after_round=args.evaluate_after_round, heldout_trials=args.heldout_trials,
                                 revise_heldout_limit=args.revise_heldout_limit)
            supervisor['status'] = campaign.state['status']
        except BaseException:
            supervisor['status'] = 'blocked'
            raise
        finally:
            write_json(directory/'supervisor.json', supervisor)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
