"""OfferExtractor — turn an agent's free-text turn into a structured ``Deal``.

The broker emits prose, but the deterministic metrics (M3/M4/M5/M7/M9/M10)
need structured offers. ``extract_turn`` asks the provider for a Deal that the
message proposes (stub returns a canned, fixture-aligned
Deal); resource names are snapped to the case's resource-set ids; unmentioned
fields carry forward. ``extract_final`` is pure assembly (no LLM): pick the
accepted/last offer, set status, and ensure every required field carries a
provenance tag (load-bearing for M1/M2).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..dealnorm import coerce_deal
from ..jsonutil import extract_json
from ..schemas import Deal

_PROV_DEFAULTS = {
    "subject": "stated",
    "price.cash": "inferred",
    "price.in_kind": "inferred",
    "terms.format": "inferred",
    "terms.timing.deadline": "stated",
    "terms.delivery_standard": "inferred",
    "obligations": "inferred",
    "status": "inferred",
}


class OfferExtractor:
    def __init__(self, case, provider):
        self.case = case
        self.provider = provider
        gt = case.fixture.get("ground_truth", {})
        self.provider_party = "B" if case.side == "sell" else "A"
        self.resource_ids = [r["id"] for r in gt.get("controllable_resource_set", [])]
        self.resource_labels = {r["id"]: r.get("label", r["id"]) for r in gt.get("controllable_resource_set", [])}
        self.required_fields: List[str] = (
            case.fixture.get("answers", {}).get("M1", {}).get("required_fields", [])
        )
        # Tracks rounds where extraction fell back to prev_offer (parse or validation failure).
        self.fallback_turns: List[str] = []
        # Post-hoc sanity warnings on the final deal (non-blocking; surfaced for review).
        self.warnings: List[str] = []

    # -- per-turn structured offer ---------------------------------------- #
    def extract_turn(
        self, text: str, *, prev_offer: Optional[Deal], speaker: str, round_no: int = 0
    ) -> Optional[Deal]:
        messages = self._prompt(text, prev_offer)
        raw = self.provider.chat_completion(messages=messages, temperature=0.0)
        data = extract_json(raw)
        if not data:
            self.fallback_turns.append(f"r{round_no}:no_json")
            return prev_offer
        try:
            deal = Deal.model_validate(coerce_deal(data, provider_party=self.provider_party))
        except Exception:
            self.fallback_turns.append(f"r{round_no}:validation_error")
            return prev_offer
        self._snap_resources(deal)
        self._carry_forward(deal, prev_offer)
        return deal

    def _prompt(self, text: str, prev_offer: Optional[Deal]) -> List[Dict[str, Any]]:
        prev = prev_offer.model_dump() if prev_offer else None
        system = (
            "你是一个信息抽取器。把谈判者这一轮发言中提出的交易条款抽成一个 Deal JSON。"
            "字段：subject, price{cash{amount,currency}, in_kind[{resource,description,from_party}]}, "
            "terms{timing{when,deadline,duration},format,deliverables,delivery_standard}, "
            "obligations[{party,text,maps_to_resource}], status, provenance。"
            f"in_kind.resource 与 obligations.maps_to_resource 必须取自：{self.resource_ids}。"
            "未提及的字段沿用上一版。"
            "【多版本消歧】若本轮发言里出现多个价格/方案(例如主方案+括号备选、版本一/版本二、"
            "或'要么…要么…'),只抽取谈判者本轮【最终主推/确认】的那一个方案,不要抽取被否决的旧值、"
            "括号里的备选、或仅作对比的参照价。只输出 JSON。"
        )
        user = f"上一版 Deal:\n{json.dumps(prev, ensure_ascii=False)}\n\n本轮发言:\n{text}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _snap_resources(self, deal: Deal) -> None:
        ids = set(self.resource_ids)
        for item in deal.price.in_kind:
            if item.resource not in ids:
                item.resource = self._match_resource(item.resource, item.description) or item.resource
        for ob in deal.obligations:
            if ob.maps_to_resource and ob.maps_to_resource not in ids:
                ob.maps_to_resource = self._match_resource(ob.maps_to_resource, ob.text)

    def _match_resource(self, name: str, hint: str) -> Optional[str]:
        text = f"{name} {hint}"
        for rid, label in self.resource_labels.items():
            if rid in text or (label and label[:4] and label[:4] in text):
                return rid
        return None

    def _carry_forward(self, deal: Deal, prev_offer: Optional[Deal]) -> None:
        init = self.case.input.initial_deal
        if not deal.subject:
            deal.subject = init.subject
        if not deal.terms.timing.deadline:
            deal.terms.timing.deadline = init.terms.timing.deadline
        if prev_offer is not None:
            if deal.price.cash.amount is None and prev_offer.price.cash.amount is not None:
                deal.price.cash = prev_offer.price.cash.model_copy()
            if not deal.price.in_kind and prev_offer.price.in_kind:
                deal.price.in_kind = [i.model_copy() for i in prev_offer.price.in_kind]

    # -- final deal assembly (no LLM) ------------------------------------- #
    @staticmethod
    def _nonempty(deal: Optional[Deal]) -> bool:
        return deal is not None and (
            deal.price.cash.amount is not None or bool(deal.price.in_kind) or bool(deal.obligations)
        )

    def extract_final(self, turns, *, accepted_offer: Optional[Deal], status: str) -> Deal:
        # The settled terms are the last real offer on the table — the agent's
        # last non-empty offer (B's ACCEPT turn often restates nothing).
        base = None
        for t in reversed(turns):
            if t.speaker == "A" and self._nonempty(t.offer):
                base = t.offer
                break
        if base is None and self._nonempty(accepted_offer):
            base = accepted_offer
        if base is None:
            for t in reversed(turns):
                if self._nonempty(t.offer):
                    base = t.offer
                    break
        if base is None:
            base = accepted_offer or self.case.input.initial_deal
        deal = base.model_copy(deep=True)
        deal.status = status
        self._ensure_provenance(deal)
        self._sanity_check(deal, turns)
        return deal

    def _sanity_check(self, deal: Deal, turns) -> None:
        """Post-hoc, non-blocking checks against the transcript. Flags (not fixes)
        the high-frequency extraction errors so the judge no longer silently
        absorbs them and downstream code can audit them:

          - cash amount that never appears anywhere in the dialogue (likely an
            extraction artifact — e.g. an abandoned/alternate quote);
          - in_kind / obligation resources outside the case resource-set.
        """
        ids = set(self.resource_ids)
        cash = deal.price.cash.amount
        if cash is not None and cash != 0:
            spoken = " ".join((t.message or "") for t in turns).replace(",", "")
            # match the integer and common comma/decimal forms
            n = int(cash) if float(cash).is_integer() else cash
            if str(n) not in spoken and f"{n:,}" not in (t.message or "" for t in turns):
                # second-chance: any offer on record carrying this cash value
                in_offers = any(
                    t.offer is not None and t.offer.price.cash.amount == cash for t in turns
                )
                if not in_offers:
                    self.warnings.append(f"cash_not_in_transcript:{n}")
        for item in deal.price.in_kind:
            if item.resource not in ids:
                self.warnings.append(f"inkind_unknown_resource:{item.resource}")
        for ob in deal.obligations:
            if ob.maps_to_resource and ob.maps_to_resource not in ids:
                self.warnings.append(f"obl_unknown_resource:{ob.maps_to_resource}")

    def _ensure_provenance(self, deal: Deal) -> None:
        for field in self.required_fields:
            if field not in deal.provenance:
                deal.provenance[field] = _PROV_DEFAULTS.get(field, "inferred")
