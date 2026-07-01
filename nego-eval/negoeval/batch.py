"""Run the benchmark over cases × skill configs × repeats; write + aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    workers: int = 16,
) -> BatchReport:
    cases = _select(load_all(cases_dir), case_filter)
    skill_modes = (["on", "off"] if skills == "both" else [x.strip() for x in skills.split(",")] if "," in skills else [skills])
    judge_cfg = live_config.aux if (mode == "live" and live_config) else None
    report = BatchReport()
    # === PARALLEL_PATCH ===
    _write_lock = threading.Lock()

    def _one(cf, sk, i):
        run_id = f"{sk}-r{i}"
        # === RESUME_PATCH ===
        from pathlib import Path as _P
        if (_P(out_dir) / f"{cf.case_id}__skills-{sk}__{run_id}.json").exists():
            return None
        # === RETRY_PATCH ===
        _max_attempts = 3
        _last_exc = None
        for _attempt in range(_max_attempts):
            try:
                out = run_episode(cf, mode=mode, skills=sk, agent_profile=agent_profile, live_config=live_config)
                judge = build_provider("judge", mode=mode, case=cf, agent_profile=agent_profile, llm_config=judge_cfg)
                res = evaluate(cf, out, run_id=run_id, judge_provider=judge)
                with _write_lock:
                    write_result(res, out_dir)
                    write_episode(out, cf.case_id, sk, run_id, out_dir, keep_trace=keep_trace)
                    report.results.append(res)
                return None
            except Exception as exc:
                _last_exc = exc
                if _attempt < _max_attempts - 1:
                    time.sleep(5 * (3 ** _attempt))  # 5s, 15s, 45s 退避
                    continue
        return f"{cf.case_id} skills={sk} run={i} (after {_max_attempts} attempts): {_last_exc!r}"

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
    }
    write_summary(report.results, report.errors, batch_config, out_dir)
    return report
