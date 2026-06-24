"""Assemble an ``EvaluationResult`` from an episode + the case fixture.

verdict: gates = M1∧M2∧M3∧M4∧M7; outcome = M5; case_pass = gates∧outcome;
quality = M6.value (case_spec §5).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..schemas import EpisodeOutput, EvaluationResult, Verdict
from . import deterministic as det
from . import judge as jdg

_GATES = ("M1", "M2", "M3", "M4", "M7")


def evaluate(
    case,
    out: EpisodeOutput,
    *,
    run_id: str,
    judge_provider,
    config_extra: Optional[Dict[str, Any]] = None,
) -> EvaluationResult:
    metrics: Dict[str, Dict[str, Any]] = {
        "M1": det.m1(case, out),
        "M2": jdg.m2(case, out, judge_provider),
        "M3": det.m3(case, out),
        "M4": det.m4(case, out),
        "M5": det.m5(case, out),
        "M6": jdg.m6(case, out, judge_provider),
        "M7": det.m7(case, out),
        "M8": det.m8(case, out),
        "M9": det.m9(case, out),
        "M10": det.m10(case, out),
    }
    # M11/M12 are recorded (not gated) when skills are on — the agent's read_skill
    # choices are the diagnosis/route signal. They never affect the verdict.
    if (out.process or {}).get("skills") == "on":
        metrics["M11"] = jdg.m11(case, out, judge_provider)
        metrics["M12"] = jdg.m12(case, out, judge_provider)
    gates_pass = all(bool(metrics[m].get("pass")) for m in _GATES)
    outcome_pass = bool(metrics["M5"].get("pass"))
    verdict = Verdict(
        gates_pass=gates_pass,
        outcome_pass=outcome_pass,
        case_pass=gates_pass and outcome_pass,
        quality=int(metrics["M6"].get("value", 0)),
    )
    proc = out.process or {}
    config: Dict[str, Any] = {
        "skills": proc.get("skills"),
        "agent_profile": proc.get("agent_profile"),
        "mode": proc.get("mode"),
    }
    if config_extra:
        config.update(config_extra)
    return EvaluationResult(
        case_id=case.case_id,
        run_id=run_id,
        config=config,
        metrics=metrics,
        verdict=verdict,
    )
