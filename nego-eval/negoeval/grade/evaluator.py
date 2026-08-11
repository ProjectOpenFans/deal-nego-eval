# === R4_SCORER_PATCH === (R4: quality=M6.value 自动兼容 0-4，无需改逻辑)
"""Assemble an ``EvaluationResult`` from an episode + the case fixture.

verdict (v0811): gates = M2 only; outcome = M5 (compound, kept for compat);
case_pass = gates∧outcome; quality = M6.value, hard-zeroed only by M2-fail or
deterministic cash_over_cap. Analysis layer should use: M0.settled (headline),
M6.tier on settled runs (guardrail 1), M2 (guardrail 2), M1/M3/M4 flags (records).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..schemas import EpisodeOutput, EvaluationResult, Verdict
from . import deterministic as det
from . import judge as jdg

# v0811: M1/M3/M4 demoted to records (pipeline health / leak flag / id alignment).
# M2 (faithfulness to the client's v0) is the only remaining behavioral gate.
_GATES = ("M2",)


def evaluate(
    case,
    out: EpisodeOutput,
    *,
    run_id: str,
    judge_provider,
    config_extra: Optional[Dict[str, Any]] = None,
) -> EvaluationResult:
    metrics: Dict[str, Dict[str, Any]] = {
        # v0811 ①: pure settlement — THE headline metric. No compound conditions.
        "M0": {"kind": "记录", "settled": det._settled(out),
               "terminal_reason": out.terminal_reason},
        "M1": det.m1(case, out),
        "M2": jdg.m2(case, out, judge_provider),
        "M3": det.m3(case, out),
        "M4": det.m4(case, out),
        "M5": det.m5(case, out),
        "M6": jdg.m6(case, out, judge_provider),
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
    case_pass = gates_pass and outcome_pass
    # === M6_GATE_PATCH_V3 ===
    # quality (M6) zeroing rules — distinguish the TWO kinds of M5 failure:
    #   (a) cash_over_cap (踩 cash-trap: agent 掏钱/收钱成交) -> HARD zero.
    #       This is a bad settled deal; do NOT trust the judge to catch it
    #       (judge can be fooled by pretty maneuvering — observed on R5C2 on,
    #       where judge gave sharp=3 to a 2000-cash cash-trap breach). The
    #       ceiling breach is deterministic, so we zero it deterministically.
    #   (b) not_settled (deadlock OR constructive-progress-unsettled) -> DO NOT
    #       zero on M5. Let the judge's M6 tier stand: real deadlock/no-maneuver
    #       gets floor from the judge anyway, while a long-path correct solution
    #       (diagnose -> build trust -> lock next step, unsigned within round_cap)
    #       keeps its earned high tier. This is the fix for harness inversion.
    # Gates (M1-M4) still hard-zero regardless (leak/over-commit/ill-formed).
    m5_reason = metrics["M5"].get("reason", "")
    cash_breach = (not outcome_pass) and ("cash_over_cap" in m5_reason)
    if not gates_pass or cash_breach:
        quality = 0
    else:
        # v0811: M6 returns value=None on unsettled runs (n/a). quality keeps its
        # legacy 0 there for backward compat; analysis uses M6.tier on settled runs.
        _m6v = metrics["M6"].get("value")
        quality = int(_m6v) if _m6v is not None else 0
    # === TOKEN_USAGE_PATCH (v0811) ===
    # Judge runs here (not in the orchestrator), so its tally is written now.
    # Note: if a judge provider instance is reused across episodes, the caller
    # must reset judge_provider.usage_tally per episode, or this accumulates.
    _snap = getattr(judge_provider, "usage_snapshot", None)
    if callable(_snap) and out.process is not None:
        out.process.setdefault("token_usage", {})["judge"] = _snap()
    # === SIM_CFG_PATCH (v0811) ===
    # Record the judge's model id too, so a result file states its own full
    # arm configuration. The judge must stay pinned for the life of a study —
    # this makes an accidental swap visible in the data instead of silent.
    if out.process is not None:
        _jm = str(getattr(judge_provider, "model", "") or "")
        if _jm:
            out.process.setdefault("model_by_role", {})["judge"] = _jm

    verdict = Verdict(
        gates_pass=gates_pass,
        outcome_pass=outcome_pass,
        case_pass=case_pass,
        quality=quality,
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
