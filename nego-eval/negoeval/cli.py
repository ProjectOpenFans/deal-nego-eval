"""CLI: run the negotiation benchmark.

    python -m negoeval.cli --provider stub --skills both --case all --out /tmp/bench
"""

from __future__ import annotations

import argparse
import sys

from .batch import run_batch
from .results.writer import format_table


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="negoeval", description="Negotiation-agent benchmark")
    p.add_argument(
        "--config",
        default=None,
        help="run directly from a v2 YAML experiment configuration",
    )
    p.add_argument("--case", default="all", help="case id(s), comma-separated, or 'all'")
    p.add_argument("--skills", default=None, help="on|off|both|clean, or comma list e.g. clean,on")
    p.add_argument("--provider", default="stub", choices=["stub", "live"])
    p.add_argument("--profile", default="par", choices=["par", "cave", "leak"], help="stub agent behavior")
    p.add_argument("--runs", type=int, default=None, help="override YAML runs_per_case")
    # === PARALLEL_PATCH ===
    p.add_argument("--workers", type=int, default=None, help="override YAML parallel workers")
    p.add_argument("--out", default="results", help="output directory for EvaluationResult json")
    p.add_argument("--cases-dir", default=None, help="override cases directory")
    p.add_argument(
        "--eval-config",
        default=None,
        help="override eval.config.yaml for live-mode agent/aux wiring",
    )
    p.add_argument(
        "--keep-trace",
        action="store_true",
        default=False,
        help="also write *.trace.json with full broker trace and skill instructions",
    )
    args = p.parse_args(argv)

    if args.config:
        from .config import load_eval_config

        eval_config = load_eval_config(args.config)
        experiment = eval_config.experiment
        if experiment.mode == "live":
            missing = eval_config.missing_model_names()
            if missing:
                print(
                    f"live mode is missing API key(s) for model connection(s): "
                    f"{', '.join(missing)}. Set each connection's api_key_env in "
                    "nego-eval/.env or the environment.",
                    file=sys.stderr,
                )
                return 2
        print(f"config: {eval_config.source_path}")
        print(
            "routes: "
            + ", ".join(
                f"{role}={model}"
                for role, model in eval_config.route_summary().items()
            )
        )
        out_dir = str(eval_config.output_dir)
        report = run_batch(
            out_dir=out_dir,
            cases_dir=str(eval_config.cases_dir),
            case_filter=args.case,
            case_include=experiment.cases.include,
            case_exclude=experiment.cases.exclude,
            skills=args.skills or ",".join(experiment.arms),
            mode=experiment.mode,
            runs=args.runs or experiment.runs_per_case,
            # Stub mode ignores live providers but still uses the YAML's repeat
            # counts and writes the same provenance contract as live runs.
            live_config=eval_config,
            keep_trace=experiment.keep_trace,
            workers=args.workers or experiment.workers,
            resume=experiment.resume,
            experiment_name=experiment.name,
        )
        print(format_table(report.reports))
        print(f"\nwrote {len(report.results)} result(s) to {out_dir}")
        if report.errors:
            print("\nERRORS:", file=sys.stderr)
            for error in report.errors:
                print("  " + error, file=sys.stderr)
            return 1
        return 0

    live_config = None
    if args.provider == "live":
        from .llm.liveconfig import load_live_config

        live_config = load_live_config(args.eval_config)
        missing = [r for r, s in (("agent", live_config.agent), ("aux", live_config.aux)) if not s.api_key]
        if missing:
            print(
                f"live mode is missing API key(s) for: {', '.join(missing)}. "
                "Set them in nego-eval/.env or the environment (e.g. STEP_API_KEY / "
                "QWEN_API_KEY / ZHIPU_API_KEY), and pick providers in nego-eval/eval.config.yaml "
                "(see configs/legacy/eval.config.example.yaml).",
                file=sys.stderr,
            )
            return 2
        print(
            f"live: agent={live_config.agent.name}:{live_config.agent.model} "
            f"aux={live_config.aux.name}:{live_config.aux.model}"
        )

    report = run_batch(
        out_dir=args.out,
        cases_dir=args.cases_dir,
        case_filter=args.case,
        skills=args.skills or "both",
        mode=args.provider,
        runs=args.runs or 1,
        agent_profile=args.profile,
        live_config=live_config,
        keep_trace=args.keep_trace,
        workers=args.workers or 16,
    )

    print(format_table(report.reports))
    print(f"\nwrote {len(report.results)} result(s) to {args.out}")
    if report.errors:
        print("\nERRORS:", file=sys.stderr)
        for e in report.errors:
            print("  " + e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
