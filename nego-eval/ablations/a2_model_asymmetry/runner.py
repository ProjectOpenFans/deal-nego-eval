"""Isolated bilateral buyer-broker vs seller-broker runner."""

from __future__ import annotations

from typing import Dict, List, Optional

from negoeval.agent.runner import AgentUnderTest
from negoeval.extract.offer_extractor import OfferExtractor
from negoeval.schemas import Deal, EpisodeOutput, Turn

from .instrumentation import InstrumentedProvider
from .models import OfferLedgerEntry, TerminalDecision
from .requests import build_bilateral_requests, transcript_history
from .terminal import TerminalReferee


_STATUS = {
    "settled": "settled",
    "walk_away": "walked_away",
    "round_cap": "draft",
}


class BilateralEpisodeRunner:
    def __init__(
        self,
        case,
        *,
        buyer_provider,
        seller_provider,
        buyer_extractor_provider,
        seller_extractor_provider,
        referee_provider,
        round_cap: int = 12,
    ) -> None:
        self.case = case
        self.round_cap = min(round_cap, case.input.config.round_cap)
        self.requests, self.party_ids, self.initiator = build_bilateral_requests(
            case.input
        )

        self.providers = {
            "buyer": InstrumentedProvider(
                buyer_provider, label="buyer_negotiator"
            ),
            "seller": InstrumentedProvider(
                seller_provider, label="seller_negotiator"
            ),
            "buyer_extractor": InstrumentedProvider(
                buyer_extractor_provider, label="buyer_offer_extractor"
            ),
            "seller_extractor": InstrumentedProvider(
                seller_extractor_provider, label="seller_offer_extractor"
            ),
            "referee": InstrumentedProvider(
                referee_provider, label="terminal_referee"
            ),
        }
        self.agents = {
            role: AgentUnderTest(
                self.requests[role],
                self.providers[role],
                allowlist=set(),
                prompt_variant="clean",
            )
            for role in ("buyer", "seller")
        }
        self.extractors = {
            role: OfferExtractor(
                case, self.providers[f"{role}_extractor"]
            )
            for role in ("buyer", "seller")
        }
        for role, extractor in self.extractors.items():
            extractor.provider_party = self.party_ids[role]
        self.referee = TerminalReferee(self.providers["referee"])
        self.final_warnings: List[str] = []

    @staticmethod
    def _nonempty(deal: Optional[Deal]) -> bool:
        return deal is not None and (
            deal.price.cash.amount is not None
            or bool(deal.price.in_kind)
            or bool(deal.obligations)
            or bool(deal.terms.deliverables)
        )

    def _final_deal(
        self,
        *,
        terminal_reason: str,
        ledger: List[OfferLedgerEntry],
        decision: TerminalDecision,
    ) -> Deal:
        selected: Optional[Deal] = None
        if terminal_reason == "settled" and decision.accepted_offer_turn is not None:
            selected = next(
                (
                    entry.deal
                    for entry in ledger
                    if entry.turn_index == decision.accepted_offer_turn
                    and self._nonempty(entry.deal)
                ),
                None,
            )
        if selected is None:
            selected = next(
                (
                    entry.deal
                    for entry in reversed(ledger)
                    if self._nonempty(entry.deal)
                ),
                None,
            )
        deal = (
            selected.model_copy(deep=True)
            if selected is not None
            else self.case.input.initial_deal.model_copy(deep=True)
        )
        deal.status = _STATUS[terminal_reason]
        if (
            deal.price.cash.amount is not None
            and float(deal.price.cash.amount) == -1
        ):
            deal.price.cash.amount = None
            self.final_warnings.append("undefined_cash_commitment")
        for field in (
            self.case.fixture.get("answers", {})
            .get("M1", {})
            .get("required_fields", [])
        ):
            deal.provenance.setdefault(field, "inferred")
        return deal

    def run(
        self,
    ) -> tuple[
        EpisodeOutput,
        List[OfferLedgerEntry],
        TerminalDecision,
        List[TerminalDecision],
        Dict,
    ]:
        turns: List[Turn] = []
        ledger: List[OfferLedgerEntry] = []
        previous: Dict[str, Optional[Deal]] = {"buyer": None, "seller": None}
        terminal_reason = "round_cap"
        decision = TerminalDecision()
        terminal_history: List[TerminalDecision] = []
        order = [self.initiator, "seller" if self.initiator == "buyer" else "buyer"]

        for round_number in range(1, self.round_cap + 1):
            for role in order:
                party_id = self.party_ids[role]
                history = transcript_history(turns, self.case.input)
                text = self.agents[role].play_turn(
                    side=f"{role}_broker",
                    round_number=round_number,
                    transcript_history=history,
                )
                extractor = self.extractors[role]
                before_fallbacks = len(extractor.fallback_turns)
                offer = extractor.extract_turn(
                    text,
                    prev_offer=previous[role],
                    speaker=party_id,
                    round_no=round_number,
                )
                if offer is not None:
                    previous[role] = offer
                turn = Turn(
                    round=round_number,
                    speaker=party_id,
                    message=text,
                    offer=offer,
                )
                turns.append(turn)
                ledger.append(
                    OfferLedgerEntry(
                        turn_index=len(turns),
                        round=round_number,
                        party=party_id,
                        role=role,
                        message=text,
                        deal=offer,
                        extraction_fallbacks=extractor.fallback_turns[
                            before_fallbacks:
                        ],
                    )
                )
                decision = self.referee.decide(turns, ledger)
                terminal_history.append(decision)
                if decision.status == "settled":
                    terminal_reason = "settled"
                    break
                if decision.status == "walk_away":
                    terminal_reason = "walk_away"
                    break
            if terminal_reason != "round_cap":
                break

        rounds = turns[-1].round if turns else 0
        final_deal = self._final_deal(
            terminal_reason=terminal_reason,
            ledger=ledger,
            decision=decision,
        )
        instrumentation = {
            key: provider.summary() for key, provider in self.providers.items()
        }
        instrumentation["total"] = {
            "calls": sum(item["calls"] for item in instrumentation.values()),
            "seconds": sum(item["seconds"] for item in instrumentation.values()),
            "estimated_input_tokens": sum(
                item["estimated_input_tokens"]
                for item in instrumentation.values()
            ),
            "estimated_output_tokens": sum(
                item["estimated_output_tokens"]
                for item in instrumentation.values()
            ),
        }
        fallbacks_by_role = {
            role: list(extractor.fallback_turns)
            for role, extractor in self.extractors.items()
        }
        warnings_by_role = {
            role: list(extractor.warnings)
            for role, extractor in self.extractors.items()
        }
        if self.final_warnings:
            warnings_by_role["final"] = list(self.final_warnings)
        process = {
            "mode": "live",
            "skills": "clean",
            "agent_profile": "bilateral",
            "agent_side": f"{self.case.input.parties['A'].seat}_broker",
            "sim_side": f"{self.case.input.parties['B'].seat}_broker",
            "buyer_model": self.providers["buyer"].model,
            "seller_model": self.providers["seller"].model,
            "initiator": self.initiator,
            "extract_fallbacks": [
                f"{role}:{value}"
                for role, values in fallbacks_by_role.items()
                for value in values
            ],
            "extract_fallbacks_by_role": fallbacks_by_role,
            "extract_warnings": [
                value
                for _role, values in warnings_by_role.items()
                for value in values
            ],
            "extract_warnings_by_role": warnings_by_role,
            "terminal_history": [
                item.model_dump() for item in terminal_history
            ],
        }
        episode = EpisodeOutput(
            episode_id=self.case.input.episode_id,
            final_deal=final_deal,
            transcript=turns,
            rounds=rounds,
            terminal_reason=terminal_reason,
            process=process,
        )
        return episode, ledger, decision, terminal_history, instrumentation
