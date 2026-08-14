"""Build isolated buyer and seller requests without cross-leaking private data."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from negoeval.broker.schemas import (
    BrokerChatMessage,
    BrokerChatRequest,
    ComposeFinalCard,
    NegotiationValueToolPolicy,
    UserInfo,
    ValueToolCapabilityPolicy,
)
from negoeval.schemas import EpisodeInput, Party, Private, PublicProfile, Turn


def _join(items: List[str]) -> Optional[str]:
    value = "；".join(item for item in items if item)
    return value or None


def _user_info(profile: PublicProfile, private: Optional[Private]) -> UserInfo:
    description: List[str] = []
    if profile.current_focus:
        description.append(profile.current_focus)
    if private is not None:
        if private.intent:
            description.append(f"我的目标：{private.intent}")
        if private.value_perception:
            description.append(f"我的判断：{private.value_perception}")
        if private.interests:
            description.append("我的真实关切：" + "；".join(private.interests))
        if private.constraints.must_haves:
            description.append("必须满足：" + "；".join(private.constraints.must_haves))
        if private.constraints.deal_breakers:
            description.append("不可接受：" + "；".join(private.constraints.deal_breakers))
    return UserInfo(
        id=profile.id or "?",
        nickname=profile.display_name or profile.id or "?",
        description=" | ".join(description) or None,
        schools=_join(profile.education),
        employments=_join(profile.career),
        skills=list(profile.interests) + list(profile.credentials),
    )


def _disabled_policy() -> NegotiationValueToolPolicy:
    disabled = ValueToolCapabilityPolicy(enabled=False)
    return NegotiationValueToolPolicy(
        deposit=disabled,
        tip=disabled,
        blank_check=disabled,
    )


def _party_by_role(inp: EpisodeInput) -> Dict[str, Tuple[str, Party]]:
    by_role = {party.seat: (party_id, party) for party_id, party in inp.parties.items()}
    if set(by_role) != {"buyer", "seller"}:
        raise ValueError("bilateral A2 cases require exactly one buyer and one seller")
    return by_role


def _card(inp: EpisodeInput, *, party: Party, initiator: str) -> ComposeFinalCard:
    cash = inp.initial_deal.price.cash.amount
    budget_target = f"{cash:g} CNY" if cash is not None else ""
    reserve = None
    reservation = party.private.constraints.reservation
    if reservation is not None and reservation.amount is not None:
        reserve = (
            f"{reservation.amount:g} {reservation.currency} — {reservation.note}"
        ).strip()
    return ComposeFinalCard(
        direction=initiator,
        headline=inp.initial_deal.subject,
        scenario=inp.initial_deal.subject,
        budget_target=budget_target,
        budget_reserve_private=reserve,
        non_negotiables=list(party.private.constraints.must_haves),
        notes=[],
    )


def build_bilateral_requests(
    inp: EpisodeInput,
) -> Tuple[Dict[str, BrokerChatRequest], Dict[str, str], str]:
    """Return role-keyed requests, party-id mapping, and initiator role.

    Each request includes private fields for its own client only. The opposing
    profile is public-only even though both requests are built in one process.
    """

    by_role = _party_by_role(inp)
    initiator = inp.parties["A"].seat
    requests: Dict[str, BrokerChatRequest] = {}
    party_ids = {role: party_id for role, (party_id, _party) in by_role.items()}

    for role, (_party_id, own) in by_role.items():
        other_role = "seller" if role == "buyer" else "buyer"
        other = by_role[other_role][1]
        own_info = _user_info(own.public_profile, own.private)
        other_info = _user_info(other.public_profile, None)
        buyer_profile = own_info if role == "buyer" else other_info
        seller_profile = own_info if role == "seller" else other_info
        requests[role] = BrokerChatRequest(
            deal_id=inp.episode_id,
            mode="initial",
            messages=[],
            compose_card=_card(inp, party=own, initiator=initiator),
            buyer_profile=buyer_profile,
            seller_profile=seller_profile,
            debug=True,
            value_tool_policy=_disabled_policy(),
        )
    return requests, party_ids, initiator


def transcript_history(
    turns: List[Turn], inp: EpisodeInput
) -> List[BrokerChatMessage]:
    history: List[BrokerChatMessage] = []
    for turn in turns:
        role = inp.parties[turn.speaker].seat
        history.append(
            BrokerChatMessage(
                role=f"{role}_broker",
                content=turn.message,
                round=turn.round,
            )
        )
    return history

