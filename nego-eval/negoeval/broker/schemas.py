"""Minimal broker schemas owned by the benchmark runtime."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


BrokerSide = Literal["seller_broker", "buyer_broker"]


class UserInfo(BaseModel):
    id: str = ""
    nickname: str = ""
    description: Optional[str] = None
    schools: Optional[str] = None
    employments: Optional[str] = None
    skills: List[str] = Field(default_factory=list)


class ComposeFinalCard(BaseModel):
    direction: Literal["seller", "buyer"] = "seller"
    headline: str = ""
    scenario: str = ""
    budget_target: str = ""
    budget_reserve_private: Optional[str] = None
    non_negotiables: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ValueToolCapabilityPolicy(BaseModel):
    enabled: bool = True


class NegotiationValueToolPolicy(BaseModel):
    deposit: ValueToolCapabilityPolicy = Field(default_factory=ValueToolCapabilityPolicy)
    tip: ValueToolCapabilityPolicy = Field(default_factory=ValueToolCapabilityPolicy)
    blank_check: ValueToolCapabilityPolicy = Field(default_factory=ValueToolCapabilityPolicy)


class ValueToolState(BaseModel):
    tool_calls: List[dict] = Field(default_factory=list)


class BrokerChatMessage(BaseModel):
    role: BrokerSide
    content: str
    round: int


class BrokerChatRequest(BaseModel):
    deal_id: str
    mode: Literal["initial", "update"] = "initial"
    messages: List[BrokerChatMessage] = Field(default_factory=list)
    compose_card: ComposeFinalCard
    buyer_profile: UserInfo
    seller_profile: UserInfo
    debug: bool = False
    value_tool_policy: NegotiationValueToolPolicy = Field(default_factory=NegotiationValueToolPolicy)
    value_tool_state: ValueToolState = Field(default_factory=ValueToolState)
