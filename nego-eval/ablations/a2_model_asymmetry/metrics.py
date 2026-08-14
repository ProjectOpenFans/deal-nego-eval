"""A2-specific price, condition, and efficiency metrics."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from negoeval.jsonutil import extract_json
from negoeval.schemas import Deal, EpisodeOutput

from .models import TermScore


_TERM_DIMENSIONS = (
    "deliverables",
    "payment_and_acceptance",
    "timing",
    "rights_and_authorization",
    "obligations_and_risk",
    "cancellation",
    "in_kind",
)


def _positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def price_bounds(case) -> Tuple[Optional[float], Optional[float]]:
    """Return (seller_floor, buyer_ceiling) only when the case supplies them."""

    parties = {party.seat: party for party in case.input.parties.values()}
    seller_res = parties["seller"].private.constraints.reservation
    buyer_res = parties["buyer"].private.constraints.reservation
    seller_floor = _positive(seller_res.amount if seller_res else None)
    buyer_ceiling = _positive(buyer_res.amount if buyer_res else None)
    ground_truth = case.fixture.get("ground_truth", {})

    def ground_value(name: str) -> Optional[float]:
        raw = ground_truth.get(name)
        return _positive(raw.get("value") if isinstance(raw, dict) else None)

    if seller_floor is None and case.side == "sell":
        seller_floor = ground_value("walk_away")
    if buyer_ceiling is None:
        buyer_ceiling = ground_value("buyer_cash_ceiling")
    if buyer_ceiling is None and case.side == "buy":
        buyer_ceiling = ground_value("walk_away")
    if (
        seller_floor is None
        or buyer_ceiling is None
        or buyer_ceiling <= seller_floor
    ):
        return None, None
    return seller_floor, buyer_ceiling


def effective_price(case, deal: Deal) -> Optional[float]:
    cash = deal.price.cash.amount
    if cash is None:
        return None
    ground_truth = case.fixture.get("ground_truth", {})
    valuations = ground_truth.get("in_kind_valuation", {})
    buyer_party = next(
        party_id
        for party_id, party in case.input.parties.items()
        if party.seat == "buyer"
    )
    value = float(cash)
    for item in deal.price.in_kind:
        item_value = _positive(valuations.get(item.resource)) or 0.0
        value += item_value if item.from_party == buyer_party else -item_value
    return value


def score_terms(provider, case, deal: Deal) -> TermScore:
    """Blindly score non-cash terms from the buyer's perspective."""

    parties = {
        party.seat: {
            "must_haves": party.private.constraints.must_haves,
            "deal_breakers": party.private.constraints.deal_breakers,
            "interests": party.private.interests,
        }
        for party in case.input.parties.values()
    }
    prompt = f"""你是交易条款盲审员。你不知道实验臂或模型身份。
根据双方真实约束，评价这份已成交 Deal 的非现金条款更偏向谁。

buyer_score 取 -2,-1,0,1,2：
-2 明显偏卖方；-1 略偏卖方；0 平衡；1 略偏买方；2 明显偏买方。
dimensions 必须给出这些键：{list(_TERM_DIMENSIONS)}，每项也取 -2..2。
只根据 Deal 中真实存在的条款评分，不因措辞长短加分。

双方约束：
{json.dumps(parties, ensure_ascii=False)}

Deal：
{json.dumps(deal.model_dump(), ensure_ascii=False)}

只输出 JSON：
{{"buyer_score":0,"dimensions":{{...}},"evidence":["具体条款证据"]}}"""
    raw = provider.chat_completion(
        messages=[
            {"role": "system", "content": "你是严谨、盲态的交易条款评审。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1536,
    )
    data = extract_json(str(raw or ""))
    if not data:
        return TermScore(
            buyer_score=0,
            dimensions={name: 0 for name in _TERM_DIMENSIONS},
            evidence=["judge_parse_failure"],
            parse_ok=False,
        )
    try:
        score = max(-2, min(2, int(data.get("buyer_score", 0))))
        raw_dimensions = data.get("dimensions") or {}
        dimensions = {
            name: max(-2, min(2, int(raw_dimensions.get(name, 0))))
            for name in _TERM_DIMENSIONS
        }
        evidence = [
            str(item) for item in (data.get("evidence") or []) if str(item)
        ]
        return TermScore(
            buyer_score=score,
            dimensions=dimensions,
            evidence=evidence,
            parse_ok=True,
        )
    except (TypeError, ValueError):
        return TermScore(
            buyer_score=0,
            dimensions={name: 0 for name in _TERM_DIMENSIONS},
            evidence=["judge_validation_failure"],
            parse_ok=False,
        )


def episode_metrics(
    case,
    episode: EpisodeOutput,
    *,
    term_score_glm: Optional[TermScore] = None,
    term_score_qwen: Optional[TermScore] = None,
    instrumentation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settled = episode.terminal_reason == "settled"
    deal = episode.final_deal
    cash = float(deal.price.cash.amount) if deal.price.cash.amount is not None else None
    effective = effective_price(case, deal) if settled else None
    seller_floor, buyer_ceiling = price_bounds(case)
    surplus = None
    if (
        settled
        and effective is not None
        and seller_floor is not None
        and buyer_ceiling is not None
    ):
        surplus = (buyer_ceiling - effective) / (buyer_ceiling - seller_floor)

    condition_consensus = None
    condition_disagreement = False
    if term_score_glm is not None and term_score_qwen is not None:
        if term_score_glm.parse_ok and term_score_qwen.parse_ok:
            glm_sign = (term_score_glm.buyer_score > 0) - (
                term_score_glm.buyer_score < 0
            )
            qwen_sign = (term_score_qwen.buyer_score > 0) - (
                term_score_qwen.buyer_score < 0
            )
            if glm_sign == qwen_sign:
                condition_consensus = (
                    term_score_glm.buyer_score + term_score_qwen.buyer_score
                ) / 2
            else:
                condition_disagreement = True

    total_usage = (instrumentation or {}).get("total", {})
    return {
        "settled": settled,
        "cash": cash if settled else None,
        "effective_price": effective,
        "seller_floor": seller_floor,
        "buyer_ceiling": buyer_ceiling,
        "buyer_surplus_share": surplus,
        "condition_consensus": condition_consensus,
        "condition_disagreement": condition_disagreement,
        "term_score_glm": (
            term_score_glm.model_dump() if term_score_glm is not None else None
        ),
        "term_score_qwen": (
            term_score_qwen.model_dump() if term_score_qwen is not None else None
        ),
        "condition_signature": {
            "deliverables": list(deal.terms.deliverables),
            "delivery_standard": deal.terms.delivery_standard,
            "timing": deal.terms.timing.model_dump(),
            "format": deal.terms.format,
            "in_kind": [
                {
                    "resource": item.resource,
                    "from_party": item.from_party,
                }
                for item in deal.price.in_kind
            ],
            "obligations": [
                {
                    "party": item.party,
                    "text": item.text,
                    "maps_to_resource": item.maps_to_resource,
                }
                for item in deal.obligations
            ],
        },
        "rounds": episode.rounds,
        "estimated_input_tokens": total_usage.get("estimated_input_tokens", 0),
        "estimated_output_tokens": total_usage.get("estimated_output_tokens", 0),
        "latency_seconds": total_usage.get("seconds", 0.0),
    }

