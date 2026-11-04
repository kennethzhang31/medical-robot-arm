"""Prepare or run a bounded, sensor-only Kelly, scalpel or scissors H/A/B comparison."""
import argparse
import json
import os
import sys
import time
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import ROOT, setup_paths
setup_paths()
from src.aspire.artifacts import write_json
from src.aspire.comparison import (FrozenComparison, prepare_comparison, read_json, relay_transport,
                                   recover_unsupported_transport, recover_native_tool_finish,
                                   record_physical_success_policy, verify_accounting)
from src.aspire.recovery import SupervisorLock, audit_ledgers, process_is_running


def report_comparison(root, *, physical_success=False, follow=False):
    if physical_success:
        record_physical_success_policy(root)
    while True:
        comparison = FrozenComparison(root)
        if comparison.success_policy() is None:
            raise ValueError("Use --physical-success to explicitly record the reporting amendment first")
        report = comparison.report(filename="physical_success_report.json")
        print(json.dumps(dict(status=report["status"], scoring=report["scoring"], counts=report["counts"])), flush=True)
        if not follow:
            return report
        terminal = comparison.state["status"] in ("completed", "stopped") and comparison.state.get("active") is None
        supervisor_path = root / "supervisor.json"
        alive = process_is_running(read_json(supervisor_path)["pid"]) if supervisor_path.exists() else False
        if terminal and not alive:
            with SupervisorLock(root):
                comparison = FrozenComparison(root)
                if comparison.state["status"] not in ("completed", "stopped") or comparison.state.get("active") is not None:
                    raise RuntimeError("Evaluation resumed; refusing to overwrite its report")
                previous = root / "control/final_report_before_physical_policy.json"
                if not previous.exists():
                    previous.write_bytes((root / "report.json").read_bytes())
                report = comparison.report()
            return report
        time.sleep(30.)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--stage", choices=("prepare", "observe", "generate", "evaluate", "run", "report"), default="prepare")
    parser.add_argument("--cases", type=int, default=5)
    parser.add_argument("--target", choices=("kelly", "scalpel", "scissor"), help="Preparation only; frozen afterward")
    parser.add_argument("--accounting-parent", help="Completed run carrying cumulative attempts; preparation only")
    parser.add_argument("--sam3-target-prompt", choices=("knife",), help="Shared scalpel prompt mapping; preparation only")
    parser.add_argument("--session-parent", help="Preserved stopped motionless same-target preflight carrying simulator starts; preparation only")
    parser.add_argument("--record-screen", action="store_true", help="Freeze per-trial Isaac app-window MP4 recording; preparation only")
    parser.add_argument("--match-source-physics", action="store_true", help="Freeze source scissors solver settings for all H/A/B; preparation only")
    parser.add_argument("--retry-preflight", action="store_true")
    parser.add_argument("--recover-transport", action="store_true")
    parser.add_argument("--recover-native-tool-finish", action="store_true", help="Reparse a complete saved native B submission; never make another model call")
    parser.add_argument("--physical-success", action="store_true", help="Record verified lift and placement as primary success; report stage only")
    parser.add_argument("--follow-report", action="store_true", help="Refresh the physical report and finalize after the evaluation supervisor exits")
    parser.add_argument("--python", default=r"C:\isaac-sim-450\python.bat")
    args = parser.parse_args()
    if args.retry_preflight and args.stage != "observe":
        parser.error("--retry-preflight is only for a motionless --stage observe before generation")
    if args.recover_transport and args.stage not in ("generate", "run"):
        parser.error("--recover-transport requires --stage generate or run")
    if args.recover_native_tool_finish and args.stage not in ("generate", "run"):
        parser.error("--recover-native-tool-finish requires --stage generate or run")
    if (args.physical_success or args.follow_report) and args.stage != "report":
        parser.error("Success reporting options require --stage report; they never change running trials")
    if args.stage != "prepare" and (args.record_screen or args.match_source_physics or any(value is not None for value in
            (args.target, args.accounting_parent, args.sam3_target_prompt, args.session_parent))):
        parser.error("Target and accounting parent are set only at preparation, never on resume")
    root = Path(args.out).resolve()
    if args.stage == "prepare":
        options = dict(cases=args.cases, target=args.target or "kelly")
        if args.sam3_target_prompt is not None:
            options["sam3_target_prompt"] = args.sam3_target_prompt
        if args.record_screen:
            options["record_screen"] = True
        if args.match_source_physics:
            options["match_source_physics"] = True
        if args.session_parent is not None:
            options["session_parent"] = Path(args.session_parent).resolve()
        if args.accounting_parent is not None:
            options["source_root"] = Path(args.accounting_parent).resolve()
        print(json.dumps(prepare_comparison(root, **options), indent=2))
        return 0
    if not root.is_relative_to(ROOT / "logs"):
        parser.error("Output must be an existing comparison under repository logs")
    if args.stage == "report":
        report_comparison(root, physical_success=args.physical_success, follow=args.follow_report)
        return 0
    with SupervisorLock(root):
        if args.recover_transport:
            recover_unsupported_transport(root)
        if args.recover_native_tool_finish:
            recover_native_tool_finish(root)
        comparison = FrozenComparison(root, launcher=args.python)
        plan = comparison.plan
        supervisor = dict(pid=os.getpid(), status="running", stage=args.stage)
        write_json(root / "supervisor.json", supervisor)
        try:
            from src.aspire.config import load_protocol
            from src.aspire.perception import check_perception_service
            _, task = load_protocol(root / "contract.json")
            write_json(root / "perception_health.json", check_perception_service(task))
            if args.stage == "observe":
                comparison.observe(retry_preflight=args.retry_preflight)
                comparison.save(status="observed", phase="ready_for_generation", active=None)
            if args.stage in ("generate", "run") and not (root / "frozen_programs.json").exists():
                verify_accounting(plan["accounting"])
                comparison.observe()
                audit = audit_ledgers(root, prior_requests=plan["accounting"]["prior_requests"] +
                    sum(read_json(path / "report.json")["requests"] for path in root.glob("provider_*") if path.is_dir()),
                    recover_interrupted=False, previous_supervisor=None)
                consumed = audit["attempted_requests"] - plan["accounting"]["prior_requests"]
                recovery = root / "control/transport_recovery.json"
                allowance = recover_unsupported_transport(root)["extra_attempt_allowance"] if recovery.exists() else 0
                remaining = 2+allowance-consumed
                if remaining < 1:
                    def exhausted(payload):
                        raise RuntimeError("Two-request cap exhausted; no extra generation attempt")
                    comparison.generate(exhausted)
                else:
                    from src.aspire.provider import load_credential
                    from src.aspire.relay import ProviderRelay
                    if not load_credential(ROOT / ".env", "API_KEY"):
                        raise RuntimeError("Missing orchestrator API_KEY")
                    with ProviderRelay(root / audit["next_ledger"], base_url=plan["base_url"], model=plan["model"],
                        credential=os.environ["API_KEY"], request_budget=remaining, prior_requests=audit["attempted_requests"],
                        timeout=1800., max_output_tokens=128000, upstream_stream=True, native_messages=True) as relay:
                        comparison.generate(partial(relay_transport, relay.url))
            if args.stage in ("evaluate", "run"):
                comparison.evaluate()
            comparison.report()
            supervisor["status"] = comparison.state["status"]
        except BaseException as error:
            supervisor["status"] = "stopped"
            comparison.save(status="stopped", error_type=type(error).__name__, error=str(error), active=None)
            comparison.report()
            raise
        finally:
            write_json(root / "supervisor.json", supervisor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
