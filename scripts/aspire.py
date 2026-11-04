"""ASPIRE surgical task: preflight, single trial, evaluation and refinement."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import ROOT, setup_paths, upstream_revision
setup_paths()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run", "evaluate", "refine", "search"))
    parser.add_argument("--python", default=r"C:\isaac-sim-450\python.bat", help="Isaac Sim Python launcher")
    parser.add_argument("--config", default=str(ROOT/"configs/aspire/surgical.json"))
    parser.add_argument("--code", default=str(ROOT/"examples/aspire/motor_smoke.py"))
    parser.add_argument("--out")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--split", choices=("dev", "validation", "eval"), default="eval",
                        help="Seed partition for evaluate; dev avoids touching held-out seeds")
    parser.add_argument("--wall-timeout", type=float, default=600.)
    parser.add_argument("--gui", action="store_true", help="Show this trial's simulator window")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--candidates", type=int, default=8, help="K proposed programs per search round")
    parser.add_argument("--iterations", type=int, default=3, help="T search rounds after the starting program")
    parser.add_argument("--plan", action="store_true", help="Print search budget without launching or contacting a provider")
    parser.add_argument("--provider-timeout", type=float, default=1800., help="Search provider response timeout in seconds")
    parser.add_argument("--resume-baseline", help="Search directory stopped on its first proposal; reuse its completed baseline")
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reasoning-effort", choices=("none", "minimal", "low", "medium", "high"))
    parser.add_argument("--max-output-tokens", type=int, default=128000)
    parser.add_argument("--env-file", default=str(ROOT/".env"),
                        help="Load only the selected provider credential for refine")
    parser.add_argument("--development-only", action="store_true",
                        help="Refine and freeze without running held-out evaluation")
    args = parser.parse_args()
    from src.aspire.config import load_protocol
    protocol, _ = load_protocol(args.config)
    if args.plan:
        if args.command != "search":
            parser.error("--plan is only supported for search")
        from src.aspire.search import search_plan
        print(json.dumps(search_plan(args.config, candidates=args.candidates, iterations=args.iterations,
            development_only=args.development_only, wall_timeout=args.wall_timeout), indent=2))
        return 0
    if args.command == "preflight":
        from src.aspire.assets import compatible_assets
        assets = compatible_assets()
        dependencies = {n: importlib.util.find_spec(n) is not None for n in
                        ("numpy", "torch", "gymnasium", "omegaconf", "cloudpickle", "PIL", "isaaclab", "flatdict", "hydra", "h5py")}
        result = dict(python=sys.version, launcher_exists=Path(args.python).is_file(),
                      aspire_commit=upstream_revision(), dependencies=dependencies,
                      isaaclab_version="v2.1.1", target_runtime="Isaac Sim 4.5",
                      compatible_wrappers=[p.name for p in assets.values()],
                      dev_seeds=protocol["development_seeds"], eval_seeds=protocol["evaluation_seeds"])
        print(json.dumps(result, indent=2))
        return 0 if result["launcher_exists"] and all(dependencies.values()) else 1
    if not args.out:
        parser.error("--out is required; use a new directory under logs")
    from src.aspire.campaign import run_trial, evaluate, refine
    common = dict(wall_timeout=args.wall_timeout, headless=not args.gui)
    if args.command == "run":
        result = run_trial(args.python, args.code, args.config, args.seed, args.out, **common)
        print(json.dumps(result, indent=2))
        return 0 if result["execution_ok"] else 1
    if args.command == "evaluate":
        result = evaluate(args.python, args.code, args.config, args.out, split=args.split, **common)
    else:
        if not args.model:
            parser.error("refine/search requires --model (and its provider credential in the parent process)")
        from src.aspire.provider import load_credential
        load_credential(args.env_file, args.api_key_env)
        provider = dict(model=args.model, base_url=args.base_url, api_key_env=args.api_key_env,
                        development_only=args.development_only, reasoning_effort=args.reasoning_effort,
                        max_output_tokens=args.max_output_tokens)
        if args.command == "search":
            from src.aspire.search import search
            result = search(args.python, args.code, args.config, args.out, candidates=args.candidates,
                            iterations=args.iterations, provider_timeout=args.provider_timeout,
                            resume_baseline=args.resume_baseline, **provider, **common)
            if result["status"] != "search_completed":
                print(json.dumps(result, indent=2))
                return 1
        else:
            result = refine(args.python, args.code, args.config, args.out, rounds=args.rounds,
                            **provider, **common)
    print(json.dumps(dict(success_count=result["success_count"], trial_count=result["trial_count"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
