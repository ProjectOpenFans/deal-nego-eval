"""Run the benchmark over cases × skill configs × repeats; write + aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .cases import CaseFile, load_all
from .grade.evaluator import evaluate
from .llm.registry import build_provider
from .orchestrator import run_episode
from .results.writer import aggregate, write_episode, write_result, write_summary
from .schemas import EvaluationResult


@dataclass
class BatchReport:
    results: List[EvaluationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def reports(self) -> List[Dict[str, Any]]:
        return aggregate(self.results)


def _select(cases: List[CaseFile], case_filter: str) -> List[CaseFile]:
    if case_filter in ("all", "", None):
        return cases
    wanted = {c.strip() for c in case_filter.split(",")}
    return [c for c in cases if c.case_id in wanted]


def run_batch(
    *,
    out_dir: str,
    cases_dir: Optional[str] = None,
    case_filter: str = "all",
    skills: str = "both",
    mode: str = "stub",
    runs: int = 1,
    agent_profile: str = "par",
    live_config: Any = None,
    keep_trace: bool = False,
) -> BatchReport:
    cases = _select(load_all(cases_dir), case_filter)
    skill_modes = ["on", "off"] if skills == "both" else [skills]
    judge_cfg = live_config.aux if (mode == "live" and live_config) else None
    report = BatchReport()
    for cf in cases:
        for sk in skill_modes:
            for i in range(runs):
                run_id = f"{sk}-r{i}"
                try:
                    out = run_episode(cf, mode=mode, skills=sk, agent_profile=agent_profile, live_config=live_config)
                    judge = build_provider(
                        "judge", mode=mode, case=cf, agent_profile=agent_profile, llm_config=judge_cfg
                    )
                    res = evaluate(cf, out, run_id=run_id, judge_provider=judge)
                    write_result(res, out_dir)
                    write_episode(out, cf.case_id, sk, run_id, out_dir, keep_trace=keep_trace)
                    report.results.append(res)
                except Exception as exc:  # keep going; surface at the end
                    report.errors.append(f"{cf.case_id} skills={sk} run={i}: {exc!r}")

    # Always write a batch-level summary, even when some runs errored.
    batch_config: Dict[str, Any] = {
        "case_filter": case_filter,
        "skills": skills,
        "mode": mode,
        "runs": runs,
        "agent_profile": agent_profile,
        "keep_trace": keep_trace,
    }
    write_summary(report.results, report.errors, batch_config, out_dir)
    return report
