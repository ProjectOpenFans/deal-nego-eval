"""Run the benchmark over cases × skill configs × repeats; write + aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _select(
    cases: List[CaseFile],
    case_filter: str,
    case_include: Optional[List[str]] = None,
    case_exclude: Optional[List[str]] = None,
) -> List[CaseFile]:
    selected = cases
    if case_filter not in ("all", "", None):
        wanted = {c.strip() for c in case_filter.split(",")}
        selected = [case for case in selected if case.case_id in wanted]
    if case_include is not None:
        selected = [
            case
            for case in selected
            if any(fnmatchcase(case.case_id, pattern) for pattern in case_include)
        ]
    if case_exclude:
        selected = [
            case
            for case in selected
            if not any(fnmatchcase(case.case_id, pattern) for pattern in case_exclude)
        ]
    return selected


def _skill_modes(skills: str) -> List[str]:
    if skills == "both":
        return ["on", "off"]
    if "," in skills:
        return [item.strip() for item in skills.split(",")]
    return [skills]


def _build_judges(case, *, mode: str, live_config, agent_profile: str):
    if mode == "live" and hasattr(live_config, "judge_spec"):
        return {
            metric: build_provider(
                "judge",
                mode=mode,
                case=case,
                agent_profile=agent_profile,
                llm_config=live_config.judge_spec(metric),
            )
            for metric in ("M2", "M6", "M11", "M12")
        }
    judge_config = live_config.aux if (mode == "live" and live_config) else None
    return build_provider(
        "judge",
        mode=mode,
        case=case,
        agent_profile=agent_profile,
        llm_config=judge_config,
    )


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
    workers: int = 16,
    case_include: Optional[List[str]] = None,
    case_exclude: Optional[List[str]] = None,
    resume: bool = True,
    experiment_name: Optional[str] = None,
) -> BatchReport:
    cases = _select(load_all(cases_dir), case_filter, case_include, case_exclude)
    skill_modes = _skill_modes(skills)
    report = BatchReport()
    _write_lock = threading.Lock()

    def _one(cf, sk, i):
        run_id = f"{sk}-r{i}"
        if resume and (Path(out_dir) / f"{cf.case_id}__skills-{sk}__{run_id}.json").exists():
            return None
        max_attempts = 3
        last_exception = None
        for attempt in range(max_attempts):
            try:
                out = run_episode(cf, mode=mode, skills=sk, agent_profile=agent_profile, live_config=live_config)
                judge = _build_judges(
                    cf,
                    mode=mode,
                    live_config=live_config,
                    agent_profile=agent_profile,
                )
                res = evaluate(cf, out, run_id=run_id, judge_provider=judge)
                with _write_lock:
                    write_result(res, out_dir)
                    write_episode(out, cf.case_id, sk, run_id, out_dir, keep_trace=keep_trace)
                    report.results.append(res)
                return None
            except Exception as exc:
                last_exception = exc
                if attempt < max_attempts - 1:
                    time.sleep(5 * (3 ** attempt))
                    continue
        return (
            f"{cf.case_id} skills={sk} run={i} "
            f"(after {max_attempts} attempts): {last_exception!r}"
        )

    tasks = [(cf, sk, i) for cf in cases for sk in skill_modes for i in range(runs)]
    if workers <= 1 or len(tasks) <= 1:
        for cf, sk, i in tasks:
            err = _one(cf, sk, i)
            if err:
                report.errors.append(err)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_one, cf, sk, i): (cf, sk, i) for cf, sk, i in tasks}
            for fut in as_completed(futs):
                err = fut.result()
                if err:
                    report.errors.append(err)

    # Always write a batch-level summary, even when some runs errored.
    batch_config: Dict[str, Any] = {
        "case_filter": case_filter,
        "skills": skills,
        "mode": mode,
        "runs": runs,
        "agent_profile": agent_profile,
        "keep_trace": keep_trace,
        "case_include": case_include,
        "case_exclude": case_exclude,
        "resume": resume,
        "experiment_name": experiment_name,
    }
    write_summary(report.results, report.errors, batch_config, out_dir)
    return report
