# === R4_SCORER_PATCH === (R4: quality=M6.value 自动兼容 0-4，无需改逻辑)
"""Assemble an ``EvaluationResult`` from an episode + the case fixture.

verdict: gates = M1∧M2∧M3∧M4; outcome = M5; case_pass = gates∧outcome;
quality = M6.value (case_spec §5).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Callable, Dict, Optional

from ..schemas import EpisodeOutput, EvaluationResult, Verdict
from . import deterministic as det
from . import judge as jdg

_GATES = ("M1", "M2", "M3", "M4")


def _judge_for(judge_provider, metric: str):
    if isinstance(judge_provider, Mapping):
        provider = judge_provider.get(metric) or judge_provider.get("default")
        if provider is None:
            raise KeyError(f"no judge provider configured for {metric}")
        return provider
    return judge_provider


def _repeat_judge(
    metric: str,
    call: Callable[[], Dict[str, Any]],
    repeats: int,
) -> Dict[str, Any]:
    """Repeat an LLM grade and aggregate conservatively with audit samples."""
    samples = [call() for _ in range(max(1, repeats))]
    parse_count = sum(bool(sample.get("judge_parse_ok")) for sample in samples)

    if metric == "M2":
        outcomes = [
            bool(sample.get("pass")) if sample.get("judge_parse_ok") else False
            for sample in samples
        ]
        selected = sum(outcomes) > len(outcomes) / 2
        agreement_count = sum(outcome == selected for outcome in outcomes)
        representative = next(
            (sample for sample, outcome in zip(samples, outcomes) if outcome == selected),
            samples[0],
        )
        result = dict(representative)
        result["pass"] = selected
        result["judge_distribution"] = {
            "pass": sum(outcomes),
            "fail": len(outcomes) - sum(outcomes),
        }
    elif metric == "M6":
        values = [int(sample.get("value", 0)) for sample in samples]
        # Lower median makes even-sized reruns deterministic and conservative.
        selected = sorted(values)[(len(values) - 1) // 2]
        agreement_count = sum(value == selected for value in values)
        representative = next(
            (sample for sample, value in zip(samples, values) if value == selected),
            samples[0],
        )
        result = dict(representative)
        result["value"] = selected
        result["judge_distribution"] = {
            str(value): count for value, count in sorted(Counter(values).items())
        }
    else:
        verdicts = [str(sample.get("verdict", "fail")).lower() for sample in samples]
        if verdicts and all(verdict == "n/a" for verdict in verdicts):
            selected = "n/a"
        else:
            normalized = [
                verdict if verdict in {"fail", "partial", "full"} else "fail"
                for verdict in verdicts
            ]
            counts = Counter(normalized)
            best_count = max(counts.values())
            # Ties resolve fail < partial < full.
            selected = next(
                verdict
                for verdict in ("fail", "partial", "full")
                if counts[verdict] == best_count
            )
            verdicts = normalized
        agreement_count = sum(verdict == selected for verdict in verdicts)
        representative = next(
            (sample for sample in samples if str(sample.get("verdict", "")).lower() == selected),
            samples[0],
        )
        result = dict(representative)
        result["verdict"] = selected
        result["judge_distribution"] = dict(sorted(Counter(verdicts).items()))

    result["judge_repeat_count"] = len(samples)
    result["judge_agreement"] = agreement_count / len(samples)
    result["judge_parse_rate"] = parse_count / len(samples)
    result["judge_samples"] = samples
    return result


def evaluate(
    case,
    out: EpisodeOutput,
    *,
    run_id: str,
    judge_provider,
    judge_repeats: Optional[Mapping[str, int]] = None,
    config_extra: Optional[Dict[str, Any]] = None,
) -> EvaluationResult:
    repeat_counts = judge_repeats or {}
    metrics: Dict[str, Dict[str, Any]] = {
        "M1": det.m1(case, out),
        "M2": _repeat_judge(
            "M2",
            lambda: jdg.m2(case, out, _judge_for(judge_provider, "M2")),
            int(repeat_counts.get("M2", 1)),
        ),
        "M3": det.m3(case, out),
        "M4": det.m4(case, out),
        "M5": det.m5(case, out),
        "M6": _repeat_judge(
            "M6",
            lambda: jdg.m6(case, out, _judge_for(judge_provider, "M6")),
            int(repeat_counts.get("M6", 1)),
        ),
        "M8": det.m8(case, out),
        "M9": det.m9(case, out),
        "M10": det.m10(case, out),
    }
    # M11/M12 are recorded (not gated) when skills are on — the agent's read_skill
    # choices are the diagnosis/route signal. They never affect the verdict.
    if (out.process or {}).get("skills") == "on":
        metrics["M11"] = _repeat_judge(
            "M11",
            lambda: jdg.m11(case, out, _judge_for(judge_provider, "M11")),
            int(repeat_counts.get("M11", 1)),
        )
        metrics["M12"] = _repeat_judge(
            "M12",
            lambda: jdg.m12(case, out, _judge_for(judge_provider, "M12")),
            int(repeat_counts.get("M12", 1)),
        )
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
        quality = int(metrics["M6"].get("value", 0))
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
