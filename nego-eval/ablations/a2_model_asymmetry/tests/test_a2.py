from __future__ import annotations

import json
from pathlib import Path

from negoeval.cases import DEFAULT_CASES_DIR, load_case
from negoeval.schemas import Deal, Turn

from ablations.a2_model_asymmetry.analysis import build_analysis
from ablations.a2_model_asymmetry.models import (
    A2EpisodeRecord,
    OfferLedgerEntry,
    TerminalDecision,
)
from ablations.a2_model_asymmetry.requests import build_bilateral_requests
from ablations.a2_model_asymmetry.runner import BilateralEpisodeRunner
from ablations.a2_model_asymmetry.spec import load_spec
from ablations.a2_model_asymmetry.terminal import TerminalReferee


PACKAGE = Path(__file__).resolve().parents[1]


class SequenceProvider:
    def __init__(self, outputs, model="test-model"):
        self.outputs = list(outputs)
        self.model = model

    def chat_completion(self, messages, **kwargs):
        if not self.outputs:
            raise AssertionError("provider output sequence exhausted")
        return self.outputs.pop(0)


def deal_payload(amount=4000):
    return {
        "subject": "测试交易",
        "price": {
            "cash": {"amount": amount, "currency": "CNY"},
            "in_kind": [],
        },
        "terms": {
            "timing": {"when": None, "deadline": None, "duration": None},
            "format": "线上",
            "deliverables": ["测试交付"],
            "delivery_standard": "双方确认",
        },
        "obligations": [],
        "status": "draft",
        "provenance": {
            "subject": "stated",
            "price.cash": "stated",
            "price.in_kind": "stated",
            "terms.format": "stated",
            "obligations": "stated",
            "status": "inferred",
        },
    }


def vote(status, accepted=None):
    return json.dumps(
        {
            "status": status,
            "accepted_offer_turn": accepted,
            "evidence": "明确接受" if status == "settled" else "继续",
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


def test_spec_freezes_four_arms_and_balanced_pilot():
    spec = load_spec(PACKAGE / "prd.yaml")
    assert set(spec.arms) == {"GG", "GQ", "QG", "QQ"}
    assert spec.arms["GQ"].buyer == "glm52"
    assert spec.arms["GQ"].seller == "qwen36"
    assert len(spec.stages["pilot"].cases) == 8
    assert spec.stages["pilot"].repeats == 3


def test_bilateral_requests_do_not_cross_leak_private_context():
    case = load_case(DEFAULT_CASES_DIR / "R4N4_entangled_hybrid.jsonc")
    requests, _party_ids, _initiator = build_bilateral_requests(case.input)
    buyer_blob = requests["buyer"].model_dump_json()
    seller_blob = requests["seller"].model_dump_json()
    buyer_private = next(
        party.private.intent
        for party in case.input.parties.values()
        if party.seat == "buyer"
    )
    seller_private = next(
        party.private.intent
        for party in case.input.parties.values()
        if party.seat == "seller"
    )
    assert buyer_private in buyer_blob
    assert seller_private not in buyer_blob
    assert seller_private in seller_blob
    assert buyer_private not in seller_blob


def test_terminal_requires_majority_and_prior_counterparty_offer():
    offer = Deal.model_validate(deal_payload())
    turns = [
        Turn(round=1, speaker="A", message="报价四千。", offer=offer),
        Turn(round=1, speaker="B", message="我明确接受这个方案。", offer=None),
    ]
    ledger = [
        OfferLedgerEntry(
            turn_index=1,
            round=1,
            party="A",
            role="buyer",
            message=turns[0].message,
            deal=offer,
        ),
        OfferLedgerEntry(
            turn_index=2,
            round=1,
            party="B",
            role="seller",
            message=turns[1].message,
            deal=None,
        ),
    ]
    referee = TerminalReferee(
        SequenceProvider([vote("settled", 1), vote("settled", 1), vote("continue")])
    )
    decision = referee.decide(turns, ledger)
    assert decision.status == "settled"
    assert decision.accepted_offer_turn == 1
    assert len(decision.votes) == 3


def test_terminal_rejects_self_offer_as_settlement():
    offer = Deal.model_validate(deal_payload())
    turns = [
        Turn(round=1, speaker="A", message="先聊聊。", offer=None),
        Turn(round=1, speaker="B", message="我提出四千。", offer=offer),
    ]
    ledger = [
        OfferLedgerEntry(
            turn_index=1,
            round=1,
            party="A",
            role="buyer",
            message=turns[0].message,
            deal=None,
        ),
        OfferLedgerEntry(
            turn_index=2,
            round=1,
            party="B",
            role="seller",
            message=turns[1].message,
            deal=offer,
        ),
    ]
    referee = TerminalReferee(SequenceProvider([vote("settled", 2)]))
    decision = referee.decide(turns, ledger)
    assert decision.status == "continue"
    assert decision.accepted_offer_turn is None


def test_bilateral_runner_binds_the_accepted_prior_offer():
    case = load_case(DEFAULT_CASES_DIR / "R4P2_fan_hard.jsonc")
    payload = deal_payload(amount=5000)
    runner = BilateralEpisodeRunner(
        case,
        buyer_provider=SequenceProvider(["我们报价五千，交付按约定执行。"], "buyer"),
        seller_provider=SequenceProvider(["我明确接受你刚才的五千方案。"], "seller"),
        buyer_extractor_provider=SequenceProvider(
            [json.dumps(payload, ensure_ascii=False)], "extractor"
        ),
        seller_extractor_provider=SequenceProvider(
            [json.dumps(payload, ensure_ascii=False)], "extractor"
        ),
        referee_provider=SequenceProvider(
            [
                vote("continue"),
                vote("settled", 1),
                vote("settled", 1),
                vote("settled", 1),
            ],
            "referee",
        ),
        round_cap=2,
    )
    episode, ledger, decision, terminal_history, instrumentation = runner.run()
    assert episode.terminal_reason == "settled"
    assert episode.final_deal.status == "settled"
    assert episode.final_deal.price.cash.amount == 5000
    assert decision.accepted_offer_turn == 1
    assert len(terminal_history) == 2
    assert [entry.role for entry in ledger] == ["buyer", "seller"]
    assert instrumentation["total"]["calls"] == 8


def test_bilateral_runner_honors_round_cap():
    case = load_case(DEFAULT_CASES_DIR / "R4P2_fan_hard.jsonc")
    payload = json.dumps(deal_payload(amount=5000), ensure_ascii=False)
    runner = BilateralEpisodeRunner(
        case,
        buyer_provider=SequenceProvider(["买方第一轮。", "买方第二轮。"], "buyer"),
        seller_provider=SequenceProvider(["卖方第一轮。", "卖方第二轮。"], "seller"),
        buyer_extractor_provider=SequenceProvider([payload, payload], "extractor"),
        seller_extractor_provider=SequenceProvider([payload, payload], "extractor"),
        referee_provider=SequenceProvider(
            [vote("continue"), vote("continue"), vote("continue"), vote("continue")],
            "referee",
        ),
        round_cap=2,
    )
    episode, ledger, decision, terminal_history, _instrumentation = runner.run()
    assert episode.terminal_reason == "round_cap"
    assert episode.rounds == 2
    assert len(episode.transcript) == 4
    assert len(ledger) == 4
    assert len(terminal_history) == 4
    assert decision.status == "continue"


def test_analysis_counts_missing_records_as_invalid():
    case = load_case(DEFAULT_CASES_DIR / "R4P2_fan_hard.jsonc")
    offer = Deal.model_validate(deal_payload())
    from negoeval.schemas import EpisodeOutput

    episode = EpisodeOutput(
        episode_id=case.case_id,
        final_deal=offer.model_copy(update={"status": "settled"}),
        transcript=[],
        rounds=1,
        terminal_reason="settled",
        process={"skills": "clean"},
    )
    records = []
    for arm in ("GG", "GQ", "QG"):
        records.append(
            A2EpisodeRecord(
                run_id="t",
                stage="smoke",
                case_id=case.case_id,
                arm=arm,
                replicate=0,
                buyer_model="x",
                seller_model="y",
                initiator="buyer",
                episode=episode,
                terminal_decision=TerminalDecision(status="settled"),
                a2_metrics={"settled": True, "cash": 5000},
            )
        )
    analysis = build_analysis(records, expected=4, samples=100, seed=1)
    assert analysis["completion_rate"] == 0.75
    assert analysis["arms"]["QQ"]["invalid_rate"] == 1.0


def test_analysis_reports_m1_to_m6_and_concession_counts():
    case = load_case(DEFAULT_CASES_DIR / "R4P2_fan_hard.jsonc")
    offer_low = Deal.model_validate(deal_payload(amount=4000))
    offer_high = Deal.model_validate(deal_payload(amount=5000))
    from negoeval.schemas import EpisodeOutput, EvaluationResult

    episode = EpisodeOutput(
        episode_id=case.case_id,
        final_deal=offer_high.model_copy(update={"status": "settled"}),
        transcript=[],
        rounds=2,
        terminal_reason="settled",
        process={"skills": "clean"},
    )
    benchmark = EvaluationResult(
        case_id=case.case_id,
        run_id="t",
        metrics={
            **{f"M{index}": {"pass": True} for index in range(1, 6)},
            "M6": {"value": 3},
        },
    )
    record = A2EpisodeRecord(
        run_id="t",
        stage="smoke",
        case_id=case.case_id,
        arm="GG",
        replicate=0,
        buyer_model="x",
        seller_model="y",
        initiator="buyer",
        episode=episode,
        offer_ledger=[
            OfferLedgerEntry(
                turn_index=1,
                round=1,
                party="A",
                role="buyer",
                message="四千",
                deal=offer_low,
            ),
            OfferLedgerEntry(
                turn_index=2,
                round=2,
                party="A",
                role="buyer",
                message="五千",
                deal=offer_high,
            ),
        ],
        terminal_decision=TerminalDecision(status="settled"),
        benchmark_result=benchmark,
        a2_metrics={"settled": True, "cash": 5000},
    )
    analysis = build_analysis([record], expected=4, samples=100, seed=1)
    summary = analysis["arms"]["GG"]
    assert summary["M1_pass_rate"] == 1.0
    assert summary["M5_pass_rate"] == 1.0
    assert summary["M6_mean"] == 3.0
    assert summary["buyer_concession_moves_mean"] == 1.0
    assert summary["seller_concession_moves_mean"] == 0.0
