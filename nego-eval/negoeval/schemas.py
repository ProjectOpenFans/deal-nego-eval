"""Our negotiation schemas (Deal / EpisodeInput / Turn / EpisodeOutput / result).

Mirrors ``case_spec.md`` §2 and §5.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Side = Literal["A", "B"]


# --------------------------------------------------------------------------- #
# Deal (used for initial_deal, per-turn offer, and final_deal)
# --------------------------------------------------------------------------- #
class Cash(BaseModel):
    amount: Optional[float] = None
    currency: str = "CNY"


class InKindItem(BaseModel):
    resource: str
    description: str = ""
    from_party: Side = "B"


class Price(BaseModel):
    cash: Cash = Field(default_factory=Cash)
    in_kind: List[InKindItem] = Field(default_factory=list)


class Timing(BaseModel):
    when: Optional[str] = None
    deadline: Optional[str] = None
    duration: Optional[str] = None


class Terms(BaseModel):
    timing: Timing = Field(default_factory=Timing)
    format: Optional[str] = None
    deliverables: List[str] = Field(default_factory=list)
    delivery_standard: Optional[str] = None


class Obligation(BaseModel):
    party: Side
    text: str
    maps_to_resource: Optional[str] = None


class Deal(BaseModel):
    subject: str = ""
    price: Price = Field(default_factory=Price)
    terms: Terms = Field(default_factory=Terms)
    obligations: List[Obligation] = Field(default_factory=list)
    status: Literal["draft", "settled", "walked_away"] = "draft"
    provenance: Dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Parties / EpisodeInput
# --------------------------------------------------------------------------- #
class PublicProfile(BaseModel):
    id: str = ""
    display_name: str = ""
    education: List[str] = Field(default_factory=list)
    career: List[str] = Field(default_factory=list)
    current_focus: str = ""
    location: str = ""
    age_band: str = ""
    hobbies: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    credentials: List[str] = Field(default_factory=list)


class Reservation(BaseModel):
    type: Literal["cash", "value"] = "cash"
    amount: Optional[float] = None
    currency: str = "CNY"
    note: str = ""


class Constraints(BaseModel):
    reservation: Optional[Reservation] = None
    must_haves: List[str] = Field(default_factory=list)
    deal_breakers: List[str] = Field(default_factory=list)
    blocking_flags: List[str] = Field(default_factory=list)


class Private(BaseModel):
    intent: str = ""
    interests: List[str] = Field(default_factory=list)
    value_perception: str = ""
    constraints: Constraints = Field(default_factory=Constraints)


class Party(BaseModel):
    seat: Literal["seller", "buyer"]
    public_profile: PublicProfile = Field(default_factory=PublicProfile)
    private: Private = Field(default_factory=Private)


class RunConfig(BaseModel):
    agent_seat: Side = "A"
    round_cap: int = 8


class EpisodeInput(BaseModel):
    episode_id: str
    initial_deal: Deal = Field(default_factory=Deal)
    parties: Dict[str, Party]
    config: RunConfig = Field(default_factory=RunConfig)


# --------------------------------------------------------------------------- #
# Transcript / EpisodeOutput
# --------------------------------------------------------------------------- #
class Turn(BaseModel):
    round: int
    speaker: Side
    message: str = ""
    offer: Optional[Deal] = None


class EpisodeOutput(BaseModel):
    episode_id: str
    final_deal: Deal
    transcript: List[Turn] = Field(default_factory=list)
    rounds: int = 0
    terminal_reason: Literal["settled", "walk_away", "round_cap"] = "round_cap"
    process: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Evaluation result
# --------------------------------------------------------------------------- #
class Verdict(BaseModel):
    gates_pass: bool = False
    outcome_pass: bool = False
    case_pass: bool = False
    quality: int = 0


class EvaluationResult(BaseModel):
    case_id: str
    run_id: str
    config: Dict[str, Any] = Field(default_factory=dict)
    # Heterogeneous per-metric payloads (kept as plain dicts to match case_spec §5).
    metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    verdict: Verdict = Field(default_factory=Verdict)
