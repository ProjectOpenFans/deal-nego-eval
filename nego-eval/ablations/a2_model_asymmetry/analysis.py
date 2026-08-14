"""Aggregate A2 records and calculate case-clustered contrasts."""

from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .models import A2EpisodeRecord


ARMS = ("GG", "GQ", "QG", "QQ")
TERM_DIMENSIONS = (
    "deliverables",
    "payment_and_acceptance",
    "timing",
    "rights_and_authorization",
    "obligations_and_risk",
    "cancellation",
    "in_kind",
)


def load_records(stage_dir: str | Path) -> List[A2EpisodeRecord]:
    path = Path(stage_dir) / "episodes"
    records = []
    for item in sorted(path.glob("*.json")):
        if item.name.startswith("._"):
            continue
        records.append(
            A2EpisodeRecord.model_validate_json(item.read_text(encoding="utf-8"))
        )
    return records


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None]
    return statistics.median(clean) if clean else None


def _quantile(values: Iterable[Optional[float]], fraction: float) -> Optional[float]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def _benchmark_pass_rate(
    records: Iterable[A2EpisodeRecord], metric: str
) -> Optional[float]:
    values = []
    for record in records:
        if record.benchmark_result is None:
            continue
        payload = record.benchmark_result.metrics.get(metric)
        if payload is not None and "pass" in payload:
            values.append(bool(payload["pass"]))
    return sum(values) / len(values) if values else None


def _benchmark_value_mean(
    records: Iterable[A2EpisodeRecord], metric: str
) -> Optional[float]:
    values = []
    for record in records:
        if record.benchmark_result is None:
            continue
        payload = record.benchmark_result.metrics.get(metric)
        if payload is not None and payload.get("value") is not None:
            values.append(float(payload["value"]))
    return _mean(values)


def _concession_moves(record: A2EpisodeRecord) -> Dict[str, int]:
    """Count same-party cash moves toward the counterparty.

    Counts, rather than raw currency deltas, remain comparable across cases with
    very different monetary scales.
    """

    previous: Dict[str, float] = {}
    moves = {"buyer": 0, "seller": 0}
    for entry in record.offer_ledger:
        if entry.deal is None:
            continue
        amount = entry.deal.price.cash.amount
        if amount is None or float(amount) <= 0:
            continue
        current = float(amount)
        prior = previous.get(entry.role)
        if prior is not None:
            if entry.role == "buyer" and current > prior:
                moves["buyer"] += 1
            elif entry.role == "seller" and current < prior:
                moves["seller"] += 1
        previous[entry.role] = current
    return moves


def _condition_dimensions(
    records: Iterable[A2EpisodeRecord],
) -> Dict[str, Dict[str, Any]]:
    values: Dict[str, List[float]] = defaultdict(list)
    disagreements: Dict[str, int] = defaultdict(int)
    for record in records:
        glm = record.a2_metrics.get("term_score_glm")
        qwen = record.a2_metrics.get("term_score_qwen")
        if not isinstance(glm, dict) or not isinstance(qwen, dict):
            continue
        if not glm.get("parse_ok") or not qwen.get("parse_ok"):
            continue
        glm_dims = glm.get("dimensions") or {}
        qwen_dims = qwen.get("dimensions") or {}
        for dimension in TERM_DIMENSIONS:
            left = float(glm_dims.get(dimension, 0))
            right = float(qwen_dims.get(dimension, 0))
            left_sign = (left > 0) - (left < 0)
            right_sign = (right > 0) - (right < 0)
            if left_sign == right_sign:
                values[dimension].append((left + right) / 2)
            else:
                disagreements[dimension] += 1
    return {
        dimension: {
            "mean": _mean(values[dimension]),
            "n_consensus": len(values[dimension]),
            "disagreements": disagreements[dimension],
        }
        for dimension in TERM_DIMENSIONS
    }


def arm_summary(
    records: List[A2EpisodeRecord], *, expected_per_arm: int
) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for arm in ARMS:
        rows = [record for record in records if record.arm == arm]
        valid = [record for record in rows if record.valid]
        settled = [
            record for record in valid if record.a2_metrics.get("settled") is True
        ]
        cash_values = [record.a2_metrics.get("cash") for record in settled]
        concessions = [_concession_moves(record) for record in valid]
        invalid_count = max(0, expected_per_arm - len(valid))
        output[arm] = {
            "expected": expected_per_arm,
            "written": len(rows),
            "valid": len(valid),
            "invalid": invalid_count,
            "invalid_rate": (
                invalid_count / expected_per_arm if expected_per_arm else None
            ),
            "settled": len(settled),
            "settlement_rate": len(settled) / len(valid) if valid else None,
            "walk_away": sum(
                record.episode.terminal_reason == "walk_away" for record in valid
            ),
            "round_cap": sum(
                record.episode.terminal_reason == "round_cap" for record in valid
            ),
            "cash_n": sum(value is not None for value in cash_values),
            "cash_mean": _mean(cash_values),
            "cash_min": _quantile(cash_values, 0.0),
            "cash_q25": _quantile(cash_values, 0.25),
            "cash_median": _median(cash_values),
            "cash_q75": _quantile(cash_values, 0.75),
            "cash_max": _quantile(cash_values, 1.0),
            "buyer_surplus_mean": _mean(
                record.a2_metrics.get("buyer_surplus_share")
                for record in settled
            ),
            "condition_consensus_mean": _mean(
                record.a2_metrics.get("condition_consensus")
                for record in settled
            ),
            "condition_disagreements": sum(
                bool(record.a2_metrics.get("condition_disagreement"))
                for record in settled
            ),
            "quality_mean": _mean(
                (
                    record.benchmark_result.verdict.quality
                    if record.benchmark_result is not None
                    else None
                )
                for record in valid
            ),
            "M1_pass_rate": _benchmark_pass_rate(valid, "M1"),
            "M2_pass_rate": _benchmark_pass_rate(valid, "M2"),
            "M3_pass_rate": _benchmark_pass_rate(valid, "M3"),
            "M4_pass_rate": _benchmark_pass_rate(valid, "M4"),
            "M5_pass_rate": _benchmark_pass_rate(valid, "M5"),
            "M6_mean": _benchmark_value_mean(valid, "M6"),
            "condition_dimensions": _condition_dimensions(settled),
            "rounds_mean": _mean(
                record.a2_metrics.get("rounds") for record in valid
            ),
            "buyer_concession_moves_mean": _mean(
                item["buyer"] for item in concessions
            ),
            "seller_concession_moves_mean": _mean(
                item["seller"] for item in concessions
            ),
            "estimated_input_tokens_mean": _mean(
                record.a2_metrics.get("estimated_input_tokens")
                for record in valid
            ),
            "estimated_output_tokens_mean": _mean(
                record.a2_metrics.get("estimated_output_tokens")
                for record in valid
            ),
            "latency_seconds_mean": _mean(
                record.a2_metrics.get("latency_seconds") for record in valid
            ),
        }
    return output


def _case_arm_means(
    records: List[A2EpisodeRecord], metric: str
) -> Dict[str, Dict[str, float]]:
    values: Dict[tuple, List[float]] = defaultdict(list)
    for record in records:
        if not record.valid:
            continue
        value = record.a2_metrics.get(metric)
        if value is None:
            continue
        values[(record.case_id, record.arm)].append(float(value))
    output: Dict[str, Dict[str, float]] = defaultdict(dict)
    for (case_id, arm), items in values.items():
        output[case_id][arm] = sum(items) / len(items)
    return dict(output)


def _bootstrap(
    differences: List[float], *, samples: int, seed: int
) -> Dict[str, Any]:
    if not differences:
        return {
            "n_cases": 0,
            "effect": None,
            "ci95": [None, None],
        }
    effect = sum(differences) / len(differences)
    randomizer = random.Random(seed)
    draws = []
    for _ in range(samples):
        sample = [
            differences[randomizer.randrange(len(differences))]
            for _ in range(len(differences))
        ]
        draws.append(sum(sample) / len(sample))
    draws.sort()
    lower = draws[int(0.025 * (len(draws) - 1))]
    upper = draws[int(0.975 * (len(draws) - 1))]
    return {
        "n_cases": len(differences),
        "effect": effect,
        "ci95": [lower, upper],
    }


def contrasts(
    records: List[A2EpisodeRecord],
    *,
    samples: int,
    seed: int,
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for metric in (
        "settled",
        "cash",
        "buyer_surplus_share",
        "condition_consensus",
    ):
        case_values = _case_arm_means(records, metric)

        def direct(left: str, right: str) -> List[float]:
            return [
                arms[left] - arms[right]
                for arms in case_values.values()
                if left in arms and right in arms
            ]

        def versus_equal(arm: str) -> List[float]:
            return [
                arms[arm] - ((arms["GG"] + arms["QQ"]) / 2)
                for arms in case_values.values()
                if arm in arms and "GG" in arms and "QQ" in arms
            ]

        result[metric] = {
            "GQ_minus_QG": _bootstrap(
                direct("GQ", "QG"), samples=samples, seed=seed
            ),
            "GQ_minus_equal": _bootstrap(
                versus_equal("GQ"), samples=samples, seed=seed + 1
            ),
            "QG_minus_equal": _bootstrap(
                versus_equal("QG"), samples=samples, seed=seed + 2
            ),
        }
    return result


# --------------------------------------------------------------------------- #
# Seat/pairwise contrasts, terminal-conditioned quality, and metric health.
#
# The `contrasts()` block above answers the pre-registered questions (direction
# of asymmetry, heterogeneous vs homogeneous). The blocks below exist because
# the pilot showed those alone are easy to misread:
#
#   * arm-level M6 tracks WHO WALKED, not deal quality: walk_away scores 0-1
#     while round_cap scores 2-3, so an episode that produced nothing at all
#     outranks one that collapsed. `m6_by_terminal` exposes it; the
#     settled-only contrast is the one to read until the M6 grader is fixed.
#   * `buyer_surplus_share` — the normalized "who won" metric — needs a settled
#     deal AND both floor and ceiling in the fixture. `metric_coverage` reports
#     how few cases actually qualify, so a contrast built on 2 cases is not
#     mistaken for one built on 8.
#   * condition scores are a two-judge consensus. `condition_agreement` reports
#     how often the two judges even agree on the SIGN, which bounds how much
#     the per-dimension means can carry.
# --------------------------------------------------------------------------- #

SEAT_MODEL = {
    "buyer": {"GG": "G", "GQ": "G", "QG": "Q", "QQ": "Q"},
    "seller": {"GG": "G", "GQ": "Q", "QG": "G", "QQ": "Q"},
}

TERMINAL_REASONS = ("settled", "walk_away", "round_cap")


def _m6(record: A2EpisodeRecord) -> Optional[float]:
    if record.benchmark_result is None:
        return None
    payload = record.benchmark_result.metrics.get("M6")
    if payload is None or payload.get("value") is None:
        return None
    return float(payload["value"])


def _episode_metrics(record: A2EpisodeRecord) -> Dict[str, Optional[float]]:
    reason = record.episode.terminal_reason
    return {
        "settled": 1.0 if reason == "settled" else 0.0,
        "walk_away": 1.0 if reason == "walk_away" else 0.0,
        "round_cap": 1.0 if reason == "round_cap" else 0.0,
        "M6": _m6(record),
    }


def _case_arm_episode_means(
    records: List[A2EpisodeRecord], metric: str, *, settled_only: bool = False
) -> Dict[str, Dict[str, float]]:
    values: Dict[tuple, List[float]] = defaultdict(list)
    for record in records:
        if not record.valid:
            continue
        if settled_only and record.episode.terminal_reason != "settled":
            continue
        value = _episode_metrics(record).get(metric)
        if value is None:
            continue
        values[(record.case_id, record.arm)].append(value)
    output: Dict[str, Dict[str, float]] = defaultdict(dict)
    for (case_id, arm), items in values.items():
        output[case_id][arm] = sum(items) / len(items)
    return dict(output)


def pairwise_contrasts(
    records: List[A2EpisodeRecord], *, samples: int, seed: int
) -> Dict[str, Dict[str, Any]]:
    """Every arm pair, not just the three pre-registered ones.

    `GQ_minus_equal` averages two noisy baselines and can reach significance
    when neither underlying pairwise difference does; reporting both keeps that
    visible.
    """
    pairs = [
        ("GQ", "GG"), ("QG", "GG"), ("QQ", "GG"),
        ("GQ", "QQ"), ("QG", "QQ"), ("GQ", "QG"),
    ]
    result: Dict[str, Dict[str, Any]] = {}
    for offset, metric in enumerate(("settled", "walk_away", "round_cap", "M6")):
        case_values = _case_arm_episode_means(records, metric)
        result[metric] = {
            f"{left}_minus_{right}": _bootstrap(
                [
                    arms[left] - arms[right]
                    for arms in case_values.values()
                    if left in arms and right in arms
                ],
                samples=samples,
                seed=seed + offset * 10 + index,
            )
            for index, (left, right) in enumerate(pairs)
        }
    return result


def seat_contrasts(
    records: List[A2EpisodeRecord], *, samples: int, seed: int
) -> Dict[str, Dict[str, Any]]:
    """Q minus G within each seat, pooling the two arms that share that seat.

    This is the contrast the arm table cannot show: it separates "which model
    sits here" from "which pair is playing", and it is where the pilot's one
    clean effect lives (walk-away is a seller-seat model trait).
    """
    result: Dict[str, Dict[str, Any]] = {}
    for offset, metric in enumerate(("settled", "walk_away", "round_cap", "M6")):
        per_seat: Dict[str, Any] = {}
        for seat, mapping in SEAT_MODEL.items():
            grouped: Dict[tuple, List[float]] = defaultdict(list)
            for record in records:
                if not record.valid:
                    continue
                value = _episode_metrics(record).get(metric)
                if value is None:
                    continue
                grouped[(record.case_id, mapping[record.arm])].append(value)
            per_case: Dict[str, Dict[str, float]] = defaultdict(dict)
            for (case_id, model), items in grouped.items():
                per_case[case_id][model] = sum(items) / len(items)
            per_seat[f"{seat}_Q_minus_G"] = _bootstrap(
                [
                    arms["Q"] - arms["G"]
                    for arms in per_case.values()
                    if "Q" in arms and "G" in arms
                ],
                samples=samples,
                seed=seed + 100 + offset * 10,
            )
        result[metric] = per_seat
    return result


def m6_by_terminal(records: List[A2EpisodeRecord]) -> Dict[str, Any]:
    """M6 distribution split by terminal reason.

    Diagnostic, not a result: it shows whether the grader is scoring the deal
    or scoring the ending.
    """
    buckets: Dict[str, List[float]] = {reason: [] for reason in TERMINAL_REASONS}
    for record in records:
        if not record.valid:
            continue
        value = _m6(record)
        if value is None:
            continue
        buckets.setdefault(record.episode.terminal_reason, []).append(value)
    return {
        reason: {
            "n": len(values),
            "mean": _mean(values),
            "distribution": {
                str(tier): sum(1 for value in values if value == tier)
                for tier in range(5)
            },
        }
        for reason, values in buckets.items()
    }


def settled_only_m6_contrasts(
    records: List[A2EpisodeRecord], *, samples: int, seed: int
) -> Dict[str, Any]:
    """Same pairwise M6 contrasts, restricted to episodes that settled."""
    case_values = _case_arm_episode_means(records, "M6", settled_only=True)
    pairs = [
        ("GQ", "GG"), ("QG", "GG"), ("QQ", "GG"),
        ("GQ", "QQ"), ("QG", "QQ"), ("GQ", "QG"),
    ]
    return {
        f"{left}_minus_{right}": _bootstrap(
            [
                arms[left] - arms[right]
                for arms in case_values.values()
                if left in arms and right in arms
            ],
            samples=samples,
            seed=seed + 200 + index,
        )
        for index, (left, right) in enumerate(pairs)
    }


def metric_coverage(records: List[A2EpisodeRecord]) -> Dict[str, Any]:
    """How many episodes and cases each case-level metric can actually use."""
    valid = [record for record in records if record.valid]
    output: Dict[str, Any] = {}
    for metric in ("cash", "buyer_surplus_share", "condition_consensus"):
        usable = [
            record for record in valid if record.a2_metrics.get(metric) is not None
        ]
        cases = sorted({record.case_id for record in usable})
        output[metric] = {
            "episodes": len(usable),
            "episodes_total": len(valid),
            "coverage": len(usable) / len(valid) if valid else None,
            "cases": len(cases),
            "case_ids": cases,
        }
    return output


def cash_robustness(records: List[A2EpisodeRecord]) -> Dict[str, Any]:
    """Is a cash contrast a real price effect, or one case and a missing case?

    Raw cash spans three orders of magnitude across the bank, so a mean of
    per-case differences is dominated by whichever big-ticket case moved. Two
    checks travel with every cash contrast:

      * leave_one_out — recompute the contrast with each case dropped. If one
        case carries it, the contrast is that case, not the arms.
      * normalized — each arm's settled price divided by the mean across arms
        for the same case. Ratios near 1.00 mean the arms settled at the same
        price and any arm-level median gap is composition: an arm that walks
        away on the cheap cases loses those low observations from its pool.
    """
    per_case: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if not record.valid:
            continue
        value = record.a2_metrics.get("cash")
        if value is None:
            continue
        per_case[record.case_id][record.arm].append(float(value))
    means = {
        case_id: {arm: sum(items) / len(items) for arm, items in arms.items()}
        for case_id, arms in per_case.items()
    }

    def paired(left: str, right: str, *, drop: Optional[str] = None) -> List[tuple]:
        return [
            (case_id, arms[left] - arms[right])
            for case_id, arms in means.items()
            if left in arms and right in arms and case_id != drop
        ]

    output: Dict[str, Any] = {"normalized": {}, "leave_one_out": {}}
    for case_id, arms in sorted(means.items()):
        base = _mean(list(arms.values()))
        output["normalized"][case_id] = {
            "base": base,
            "ratios": (
                {arm: value / base for arm, value in arms.items()}
                if base
                else {arm: None for arm in arms}
            ),
        }
    for left, right in (("GQ", "QG"), ("GQ", "GG"), ("QG", "GG"), ("QQ", "GG")):
        full = paired(left, right)
        if not full:
            continue
        output["leave_one_out"][f"{left}_minus_{right}"] = {
            "effect": _mean([value for _, value in full]),
            "per_case": {case_id: value for case_id, value in full},
            "dropping": {
                case_id: _mean(
                    [value for _, value in paired(left, right, drop=case_id)]
                )
                for case_id, _ in full
            },
        }
    return output


def condition_agreement(records: List[A2EpisodeRecord]) -> Dict[str, Any]:
    """How often the two blind term judges agree on the SIGN of each dimension.

    The per-dimension means only average the items where they agreed, so this
    rate is what bounds their interpretability.
    """
    def sign(value: Any) -> Optional[int]:
        if value is None:
            return None
        number = float(value)
        return (number > 0) - (number < 0)

    per_dimension: Dict[str, List[bool]] = defaultdict(list)
    overall_buyer: List[bool] = []
    for record in records:
        if not record.valid:
            continue
        glm = record.a2_metrics.get("term_score_glm")
        qwen = record.a2_metrics.get("term_score_qwen")
        if not isinstance(glm, dict) or not isinstance(qwen, dict):
            continue
        left, right = sign(glm.get("buyer_score")), sign(qwen.get("buyer_score"))
        if left is not None and right is not None:
            overall_buyer.append(left == right)
        glm_dimensions = glm.get("dimensions") or {}
        qwen_dimensions = qwen.get("dimensions") or {}
        for dimension in TERM_DIMENSIONS:
            left = sign(glm_dimensions.get(dimension))
            right = sign(qwen_dimensions.get(dimension))
            if left is not None and right is not None:
                per_dimension[dimension].append(left == right)

    flat = [item for items in per_dimension.values() for item in items]
    return {
        "dimension_items": len(flat),
        "dimension_agreement": sum(flat) / len(flat) if flat else None,
        "buyer_score_items": len(overall_buyer),
        "buyer_score_agreement": (
            sum(overall_buyer) / len(overall_buyer) if overall_buyer else None
        ),
        "by_dimension": {
            dimension: {
                "n": len(items),
                "agreement": sum(items) / len(items) if items else None,
            }
            for dimension, items in per_dimension.items()
        },
    }


def build_analysis(
    records: List[A2EpisodeRecord],
    *,
    expected: int,
    samples: int,
    seed: int,
) -> Dict[str, Any]:
    expected_per_arm = expected // len(ARMS) if ARMS else 0
    arms = arm_summary(records, expected_per_arm=expected_per_arm)
    written = len(records)
    valid = sum(record.valid for record in records)
    invalid_rates = [
        summary["invalid_rate"]
        for summary in arms.values()
        if summary["invalid_rate"] is not None
    ]
    return {
        "expected_episodes": expected,
        "written_episodes": written,
        "valid_episodes": valid,
        "completion_rate": valid / expected if expected else 0.0,
        "arm_invalid_rate_gap": (
            max(invalid_rates) - min(invalid_rates) if invalid_rates else None
        ),
        "arms": arms,
        "contrasts": contrasts(records, samples=samples, seed=seed),
        "pairwise_contrasts": pairwise_contrasts(
            records, samples=samples, seed=seed
        ),
        "seat_contrasts": seat_contrasts(records, samples=samples, seed=seed),
        "m6_by_terminal": m6_by_terminal(records),
        "settled_only_m6_contrasts": settled_only_m6_contrasts(
            records, samples=samples, seed=seed
        ),
        "metric_coverage": metric_coverage(records),
        "cash_robustness": cash_robustness(records),
        "condition_agreement": condition_agreement(records),
        "cases": sorted({record.case_id for record in records}),
    }


def write_analysis(payload: Dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
