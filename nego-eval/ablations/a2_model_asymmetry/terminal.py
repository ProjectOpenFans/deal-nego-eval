"""Blind public-transcript terminal adjudication for bilateral episodes."""

from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List

from negoeval.jsonutil import extract_json
from negoeval.schemas import Turn

from .models import OfferLedgerEntry, TerminalDecision, TerminalVote


_SYSTEM = """你是双边谈判的盲态终止裁判。你只看公开对话和公开报价，不知道模型身份。

输出一个 JSON：
{"status":"continue|settled|walk_away","accepted_offer_turn":整数或null,
 "evidence":"公开话术证据","confidence":0到1}

严格规则：
1. settled 只在最新发言者明确、无条件接受了对方先前一个可定位的具体方案时成立。
2. “可以考虑、方向可以、如果你同意、基本没问题、回去确认”都不是成交。
3. accepted_offer_turn 必须指向对方更早的、含具体条款的报价 turn_index。
4. walk_away 只在最新发言明确结束/退出本次谈判时成立。
5. 其他情况一律 continue。不要依据常识补全接受或退出。"""


class TerminalReferee:
    def __init__(self, provider):
        self.provider = provider

    @staticmethod
    def _public_payload(
        turns: List[Turn], ledger: List[OfferLedgerEntry]
    ) -> str:
        offers: Dict[int, dict] = {
            entry.turn_index: entry.deal.model_dump()
            for entry in ledger
            if entry.deal is not None
        }
        rows = []
        for index, turn in enumerate(turns, start=1):
            role = next(
                (
                    entry.role
                    for entry in ledger
                    if entry.turn_index == index
                ),
                "?",
            )
            offer = offers.get(index)
            rows.append(
                f"turn_index={index} round={turn.round} party={turn.speaker} "
                f"role={role}\n消息：{turn.message}\n"
                f"报价：{json.dumps(offer, ensure_ascii=False) if offer else 'null'}"
            )
        return "\n\n".join(rows)

    def _vote(
        self, turns: List[Turn], ledger: List[OfferLedgerEntry]
    ) -> TerminalVote:
        raw = self.provider.chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": self._public_payload(turns, ledger),
                },
            ],
            temperature=0.0,
            max_tokens=512,
        )
        data = extract_json(str(raw or ""))
        if not data:
            return TerminalVote(
                status="continue",
                evidence="referee_parse_failure",
                confidence=0.0,
                parse_ok=False,
            )
        status = str(data.get("status") or "continue").lower()
        if status not in {"continue", "settled", "walk_away"}:
            status = "continue"
        accepted = data.get("accepted_offer_turn")
        try:
            accepted = int(accepted) if accepted is not None else None
        except (TypeError, ValueError):
            accepted = None
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return TerminalVote(
            status=status,
            accepted_offer_turn=accepted,
            evidence=str(data.get("evidence") or ""),
            confidence=max(0.0, min(1.0, confidence)),
            parse_ok=True,
        )

    @staticmethod
    def _valid_settlement(
        vote: TerminalVote,
        *,
        turns: List[Turn],
        ledger: List[OfferLedgerEntry],
    ) -> bool:
        if vote.status != "settled" or vote.accepted_offer_turn is None:
            return vote.status != "settled"
        current_index = len(turns)
        if vote.accepted_offer_turn >= current_index:
            return False
        accepted = next(
            (
                entry
                for entry in ledger
                if entry.turn_index == vote.accepted_offer_turn
                and entry.deal is not None
            ),
            None,
        )
        if accepted is None:
            return False
        return accepted.party != turns[-1].speaker

    def decide(
        self, turns: List[Turn], ledger: List[OfferLedgerEntry]
    ) -> TerminalDecision:
        first = self._vote(turns, ledger)
        if not self._valid_settlement(first, turns=turns, ledger=ledger):
            first = TerminalVote(
                status="continue",
                evidence="invalid accepted_offer_turn: " + first.evidence,
                confidence=0.0,
                parse_ok=first.parse_ok,
            )
        votes = [first]
        if first.status != "continue":
            for _ in range(2):
                vote = self._vote(turns, ledger)
                if not self._valid_settlement(vote, turns=turns, ledger=ledger):
                    vote = TerminalVote(
                        status="continue",
                        evidence="invalid accepted_offer_turn: " + vote.evidence,
                        confidence=0.0,
                        parse_ok=vote.parse_ok,
                    )
                votes.append(vote)

        counts = Counter(vote.status for vote in votes)
        if counts.get("settled", 0) >= 2:
            status = "settled"
        elif counts.get("walk_away", 0) >= 2:
            status = "walk_away"
        else:
            status = "continue"

        accepted_offer_turn = None
        if status == "settled":
            accepted_candidates = [
                vote.accepted_offer_turn
                for vote in votes
                if vote.status == "settled" and vote.accepted_offer_turn is not None
            ]
            if accepted_candidates:
                accepted_offer_turn = Counter(accepted_candidates).most_common(1)[0][0]
        evidence = next(
            (vote.evidence for vote in votes if vote.status == status),
            votes[0].evidence,
        )
        return TerminalDecision(
            status=status,
            accepted_offer_turn=accepted_offer_turn,
            evidence=evidence,
            votes=votes,
        )

