#!/usr/bin/env python3
"""Build the static, secret-free dataset consumed by the negotiation viewer."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negoeval.cases import DEFAULT_CASES_DIR, LEGACY_CASES_DIR, load_all  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_index() -> dict[str, dict[str, Any]]:
    cases = [*load_all(LEGACY_CASES_DIR), *load_all(DEFAULT_CASES_DIR)]
    return {
        case.case_id: {
            "case_id": case.case_id,
            "side": case.side,
            "tier": case.meta.get("tier"),
            "isolates": case.meta.get("isolates", ""),
            "probes": case.meta.get("probes", []),
            "meta": case.meta,
            "input": case.input.model_dump(),
            "fixture": case.fixture,
            "agent_label": (
                "买方谈判代理" if case.side == "buy" else "卖方谈判代理"
            ),
            "counterparty_label": (
                "卖方对手模型" if case.side == "buy" else "买方对手模型"
            ),
        }
        for case in cases
    }


def _result_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*.json")
        if not path.name.startswith(("_summary", "._"))
        and not path.name.endswith(".episode.json")
        and not path.name.endswith(".trace.json")
    )


def _source_label(directory: Path, archived: bool) -> str:
    if archived:
        return f"Historical pre-refactor sample · {directory.name}"
    return directory.name


def build_dataset(result_dirs: list[Path], endpoint_status: Path | None) -> dict[str, Any]:
    cases = _case_index()
    runs: list[dict[str, Any]] = []

    for directory in result_dirs:
        directory = directory.resolve()
        archived = "archive" in directory.parts
        for result_path in _result_files(directory):
            episode_path = result_path.with_name(
                result_path.name.removesuffix(".json") + ".episode.json"
            )
            if not episode_path.exists():
                continue
            result = _read_json(result_path)
            episode = _read_json(episode_path)
            case_id = str(result.get("case_id") or episode.get("episode_id") or "unknown")
            case_meta = cases.get(
                case_id,
                {
                    "case_id": case_id,
                    "side": "unknown",
                    "tier": None,
                    "isolates": "",
                    "probes": [],
                    "agent_label": "谈判代理（A）",
                    "counterparty_label": "对手模型（B）",
                    "meta": {},
                    "input": {},
                    "fixture": {},
                },
            )
            arm = str((result.get("config") or {}).get("skills") or "unknown")
            run_id = str(result.get("run_id") or result_path.stem)
            runs.append(
                {
                    "id": f"{directory.name}:{case_id}:{arm}:{run_id}",
                    "source": directory.name,
                    "source_label": _source_label(directory, archived),
                    "archived": archived,
                    "case": case_meta,
                    "case_id": case_id,
                    "arm": arm,
                    "run_id": run_id,
                    "config": result.get("config") or {},
                    "metrics": result.get("metrics") or {},
                    "verdict": result.get("verdict") or {},
                    "episode": {
                        "final_deal": episode.get("final_deal") or {},
                        "transcript": episode.get("transcript") or [],
                        "rounds": episode.get("rounds", 0),
                        "terminal_reason": episode.get("terminal_reason", "unknown"),
                        "process": {
                            key: value
                            for key, value in (episode.get("process") or {}).items()
                            if key
                            in {
                                "skills",
                                "skills_used",
                                "skills_forced",
                                "mode",
                                "agent_profile",
                                "agent_side",
                                "sim_side",
                                "extract_fallbacks",
                                "extract_warnings",
                            }
                        },
                    },
                }
            )

    passes = sum(bool(run["verdict"].get("case_pass")) for run in runs)
    settled = sum(
        run["episode"].get("terminal_reason") == "settled" for run in runs
    )
    qualities = [
        int(run["verdict"].get("quality", 0))
        for run in runs
        if run.get("verdict")
    ]
    by_case: dict[str, list[bool]] = {}
    judge_agreements: list[float] = []
    judge_parse_rates: list[float] = []
    for run in runs:
        by_case.setdefault(run["case_id"], []).append(
            bool(run["verdict"].get("case_pass"))
        )
        for metric in run["metrics"].values():
            agreement = metric.get("judge_agreement")
            parse_rate = metric.get("judge_parse_rate")
            if isinstance(agreement, (int, float)):
                judge_agreements.append(float(agreement))
            if isinstance(parse_rate, (int, float)):
                judge_parse_rates.append(float(parse_rate))
    rerun_cases = {
        case_id: outcomes for case_id, outcomes in by_case.items() if len(outcomes) >= 2
    }
    stable_cases = sum(len(set(outcomes)) == 1 for outcomes in rerun_cases.values())
    unstable_case_ids = sorted(
        case_id
        for case_id, outcomes in rerun_cases.items()
        if len(set(outcomes)) > 1
    )
    sources = sorted({run["source"] for run in runs})
    case_ids = sorted({run["case_id"] for run in runs})
    arms = sorted({run["arm"] for run in runs})

    status = _read_json(endpoint_status) if endpoint_status and endpoint_status.exists() else {}
    historical_only = bool(runs) and all(run["archived"] for run in runs)
    return {
        "meta": {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_label": (
                "历史归档样本" if historical_only else "Coolwei GLM / Qwen 本次实验"
            ),
            "disclaimer": (
                "当前页面只展示本次 Coolwei GLM / Qwen 结果，不混入任何历史样本。"
                if not historical_only
                else "当前页面展示历史归档样本。"
            ),
            "canonical_result_dir": (
                "nego-eval/results/clean-coolwei-glm52-qwen36"
            ),
        },
        "summary": {
            "runs": len(runs),
            "cases": len(case_ids),
            "pass_rate": passes / len(runs) if runs else 0,
            "settled": settled,
            "quality_mean": sum(qualities) / len(qualities) if qualities else 0,
            "rerun_cases": len(rerun_cases),
            "stable_cases": stable_cases,
            "stability_rate": stable_cases / len(rerun_cases) if rerun_cases else 0,
            "unstable_case_ids": unstable_case_ids,
            "judge_agreement_mean": (
                sum(judge_agreements) / len(judge_agreements)
                if judge_agreements
                else 0
            ),
            "judge_parse_rate_mean": (
                sum(judge_parse_rates) / len(judge_parse_rates)
                if judge_parse_rates
                else 0
            ),
        },
        "filters": {"sources": sources, "cases": case_ids, "arms": arms},
        "endpoint_status": status,
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results",
        action="append",
        required=True,
        help="result directory; repeat to merge multiple runs",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--endpoint-status")
    args = parser.parse_args()

    result_dirs = [
        (Path(path) if Path(path).is_absolute() else (ROOT / path)).resolve()
        for path in args.results
    ]
    missing = [str(path) for path in result_dirs if not path.is_dir()]
    if missing:
        raise SystemExit(f"result directories do not exist: {', '.join(missing)}")
    endpoint_status = (
        (Path(args.endpoint_status) if Path(args.endpoint_status).is_absolute()
         else ROOT / args.endpoint_status).resolve()
        if args.endpoint_status
        else None
    )
    output = (
        Path(args.output)
        if Path(args.output).is_absolute()
        else (ROOT / args.output)
    ).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset(result_dirs, endpoint_status)
    output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {dataset['summary']['runs']} runs / "
        f"{dataset['summary']['cases']} cases to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
