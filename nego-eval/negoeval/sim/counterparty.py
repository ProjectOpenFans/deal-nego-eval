"""CounterpartySim — plays seat B against the agent, one turn at a time.

It is an LLM (provider) + the rendered system prompt + tolerant parsing of the
``{message, action, offer}`` contract. The provider may be the stub (offline) or
a live model; the parsing path is identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..dealnorm import coerce_deal
from ..jsonutil import extract_json
from ..schemas import Deal, Turn
from .prompt import render_system_prompt

_ACTIONS = {"CONTINUE", "COUNTER", "ACCEPT", "WALK"}


@dataclass
class SimTurn:
    message: str
    action: str
    offer: Optional[Deal]


class CounterpartySim:
    def __init__(self, case, provider):
        self.case = case
        self.provider = provider
        self.provider_party = "B" if case.side == "sell" else "A"
        self.system = render_system_prompt(case)

    def respond(self, transcript: List[Turn], round_no: int) -> SimTurn:
        messages = [{"role": "system", "content": self.system}]
        for t in transcript:
            if t.speaker == "B":
                messages.append({"role": "assistant", "content": t.message})
            else:
                messages.append({"role": "user", "content": f"[对方 · 第{t.round}轮]\n{t.message}"})
        messages.append(
            {"role": "user", "content": "现在轮到你回应。只输出一个 JSON 对象（message / action / offer）。"}
        )
        raw = self.provider.chat_completion(messages=messages, temperature=0.3)
        return self._parse(raw)

    def _parse(self, raw: str) -> SimTurn:
        data = extract_json(raw)
        if not data:
            return SimTurn(message=(raw or "").strip(), action="CONTINUE", offer=None)
        action = str(data.get("action", "CONTINUE")).upper()
        if action not in _ACTIONS:
            action = "CONTINUE"
        offer = None
        raw_offer = data.get("offer")
        if isinstance(raw_offer, dict):
            try:
                offer = Deal.model_validate(coerce_deal(raw_offer, provider_party=self.provider_party))
            except Exception:
                offer = None
        return SimTurn(message=str(data.get("message", "")), action=action, offer=offer)
