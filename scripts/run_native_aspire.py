"""Credential-owning supervisor for a bounded native ASPIRE scissors trial."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import ROOT, setup_paths
setup_paths()
from src.aspire.artifacts import write_json
from src.aspire.campaign import launcher_command, worker_environment
from src.aspire.provider import load_credential
from src.aspire.relay import ProviderRelay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=501)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--revisions", type=int, default=3)
    parser.add_argument("--model", default="claude-secondary/claude-opus-4-6")
    parser.add_argument("--base-url", default="https://cgv.cs.nthu.edu.tw:9128/v1")
    parser.add_argument("--provider-timeout", type=float, default=1800.)
    parser.add_argument("--max-output-tokens", type=int, default=128000)
    parser.add_argument("--prior-requests", type=int, default=2)
    parser.add_argument("--request-budget", type=int, default=22)
    parser.add_argument("--max-total-requests", type=int, default=24,
                        help="Explicitly authorized total cap, including prior requests")
    parser.add_argument("--initial-code", help="Replay a saved program before native refinement")
    parser.add_argument("--python", default=r"C:\isaac-sim-450\python.bat")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.candidates <= 16 or not 0 <= args.revisions <= 3:
        parser.error("Use K=1..16 and at most three revision rounds")
    if not 0 <= args.prior_requests <= args.max_total_requests or not args.candidates+1 <= args.request_budget <= args.max_total_requests-args.prior_requests:
        parser.error("Request budget must fit one ensemble and stay within the authorized total cap")
    if not 10 <= args.provider_timeout <= 1800 or not 1024 <= args.max_output_tokens <= 128000:
        parser.error("Unsupported timeout/output limit")
    if args.initial_code:
        from src.aspire.execution import validate_program
        validate_program(Path(args.initial_code).read_text(encoding="utf-8"))
    directory = Path(args.out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    if not load_credential(ROOT/".env", "API_KEY"):
        raise RuntimeError("Missing provider credential")
    write_json(directory/"launch.json", {key:value for key,value in vars(args).items()})
    with ProviderRelay(directory/"provider", base_url=args.base_url, model=args.model,
            credential=os.environ["API_KEY"], request_budget=args.request_budget,
            prior_requests=args.prior_requests, timeout=args.provider_timeout,
            max_output_tokens=args.max_output_tokens) as relay:
        worker_args = [ROOT/"scripts/aspire_native_worker.py", "--config", Path(args.config).resolve(),
            "--out", directory, "--relay-url", relay.url, "--model", args.model,
            "--seed", str(args.seed), "--candidates", str(args.candidates), "--revisions", str(args.revisions),
            "--provider-timeout", str(args.provider_timeout), "--max-output-tokens", str(args.max_output_tokens),
            "--device", "cuda:0"]
        if not args.gui:
            worker_args.append("--headless")
        if args.initial_code:
            worker_args.extend(["--initial-code", str(Path(args.initial_code).resolve())])
        with (directory/"worker.log").open("w", encoding="utf-8") as log:
            environment = worker_environment()
            environment["PYTHONUTF8"] = "1"
            process = subprocess.Popen(launcher_command(args.python, worker_args), cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT, env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            write_json(directory/"process.json", dict(pid=process.pid, relay_url=relay.url))
            try:
                return process.wait(timeout=args.request_budget*args.provider_timeout+4*600+180)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=log, stderr=subprocess.STDOUT, timeout=20,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.kill()
                write_json(directory/"supervisor_error.json", dict(status="worker_wall_timeout"))
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
