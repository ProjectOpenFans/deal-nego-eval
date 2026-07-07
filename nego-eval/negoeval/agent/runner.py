"""AgentUnderTest — one local broker side, driven turn-by-turn."""

from __future__ import annotations

from typing import List, Optional, Set

from ..broker.runner import BrokerEventEmitter, BrokerToolExecutor, LocalBrokerRunner
from ..broker.schemas import BrokerChatMessage, BrokerChatRequest, BrokerSide


class AgentUnderTest:
    """One local broker side, driven turn-by-turn against an external opponent."""

    def __init__(self, request: BrokerChatRequest, provider, *, allowlist: Optional[Set[str]], prompt_variant: str = "full"):
        self.request = request
        self.provider = provider
        self.allowlist = allowlist
        self.executor = BrokerToolExecutor(allowlist=allowlist)
        self.emitter = BrokerEventEmitter()
        self.skills_used: List[str] = []
        self.skills_forced: List[str] = []
        self.turns = LocalBrokerRunner(
            request=self.request,
            provider=self.provider,
            allowlist=self.allowlist,
            executor=self.executor,
            emitter=self.emitter,
            skills_used=self.skills_used,
            skills_forced=self.skills_forced,
            prompt_variant=prompt_variant,
        )

    def play_turn(self, *, side: BrokerSide, round_number: int, transcript_history: List[BrokerChatMessage]) -> str:
        return self.turns.run(
            side=side,
            round_number=round_number,
            transcript_history=transcript_history,
        )

    def round_order_first(self) -> str:
        """Which side opens (compose-card owner)."""
        return "seller_broker" if self.request.compose_card.direction == "seller" else "buyer_broker"
