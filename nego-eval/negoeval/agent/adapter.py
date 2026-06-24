"""Adapt our ``EpisodeInput`` to the local ``BrokerChatRequest`` + map turns.

Visibility rules (case_spec §2): both public profiles are shared; seat A (the
agent) also sees its OWN private (intent / must-haves / its declared reservation
via ``budget_reserve_private``); seat B's private is never exposed. The harness-only
``walk_away`` is never placed here — only A's *declared* reservation (which some
cases, e.g. P1, deliberately leave empty so the agent must construct its floor).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..broker.schemas import (
    BrokerChatMessage,
    BrokerChatRequest,
    ComposeFinalCard,
    NegotiationValueToolPolicy,
    UserInfo,
    ValueToolCapabilityPolicy,
)

from ..schemas import EpisodeInput, Party, Private, PublicProfile, Turn


def _join(items: List[str]) -> Optional[str]:
    text = "；".join(i for i in items if i)
    return text or None


def _user_info(profile: PublicProfile, private: Optional[Private], *, include_private: bool) -> UserInfo:
    desc: List[str] = []
    if profile.current_focus:
        desc.append(profile.current_focus)
    if include_private and private is not None:
        if private.intent:
            desc.append(f"我的目标：{private.intent}")
        if private.value_perception:
            desc.append(f"我的判断：{private.value_perception}")
        if private.constraints.must_haves:
            desc.append("必须满足：" + "；".join(private.constraints.must_haves))
        if private.constraints.deal_breakers:
            desc.append("不可接受：" + "；".join(private.constraints.deal_breakers))
    return UserInfo(
        id=profile.id or "?",
        nickname=profile.display_name or profile.id or "?",
        description=" | ".join(desc) or None,
        schools=_join(profile.education),
        employments=_join(profile.career),
        skills=list(profile.interests) + list(profile.credentials),
    )


def _disabled_policy() -> NegotiationValueToolPolicy:
    off = ValueToolCapabilityPolicy(enabled=False)
    return NegotiationValueToolPolicy(deposit=off, tip=off, blank_check=off)


def build_broker_request(
    inp: EpisodeInput, side: str, *, value_tools_enabled: bool
) -> Tuple[BrokerChatRequest, str, str]:
    """Return (request, agent_broker_side, sim_broker_side). ``side`` is meta.side."""
    a: Party = inp.parties["A"]
    b: Party = inp.parties["B"]
    agent_is_seller = side == "sell"
    agent_side = "seller_broker" if agent_is_seller else "buyer_broker"
    sim_side = "buyer_broker" if agent_is_seller else "seller_broker"

    a_info = _user_info(a.public_profile, a.private, include_private=True)
    b_info = _user_info(b.public_profile, None, include_private=False)
    if agent_is_seller:
        seller_profile, buyer_profile, direction = a_info, b_info, "seller"
    else:
        buyer_profile, seller_profile, direction = a_info, b_info, "buyer"

    cash = inp.initial_deal.price.cash.amount
    budget_target = f"{cash:g} CNY" if cash is not None else ""
    reserve = None
    res = a.private.constraints.reservation
    if res is not None and res.amount is not None:
        reserve = f"{res.amount:g} {res.currency} — {res.note}".strip()

    card = ComposeFinalCard(
        direction=direction,  # owner opens -> seat A opens
        headline=inp.initial_deal.subject,
        scenario=inp.initial_deal.subject,
        budget_target=budget_target,
        budget_reserve_private=reserve,
        non_negotiables=list(a.private.constraints.must_haves),
        notes=[],
    )
    policy = NegotiationValueToolPolicy() if value_tools_enabled else _disabled_policy()
    request = BrokerChatRequest(
        deal_id=inp.episode_id,
        mode="initial",
        messages=[],
        compose_card=card,
        buyer_profile=buyer_profile,
        seller_profile=seller_profile,
        debug=True,
        value_tool_policy=policy,
    )
    return request, agent_side, sim_side


def to_transcript_history(turns: List[Turn], agent_side: str, sim_side: str) -> List[BrokerChatMessage]:
    """Map our transcript to local broker messages (A->agent side, B->sim side)."""
    out: List[BrokerChatMessage] = []
    for t in turns:
        role = agent_side if t.speaker == "A" else sim_side
        out.append(BrokerChatMessage(role=role, content=t.message, round=t.round))
    return out
