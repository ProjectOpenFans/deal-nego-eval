"""A2 artifact schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from negoeval.schemas import Deal, EpisodeOutput, EvaluationResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OfferLedgerEntry(BaseModel):
    turn_index: int
    round: int
    party: Literal["A", "B"]
    role: Literal["buyer", "seller"]
    message: str
    deal: Optional[Deal] = None
    extraction_fallbacks: List[str] = Field(default_factory=list)


class TerminalVote(BaseModel):
    status: Literal["continue", "settled", "walk_away"] = "continue"
    accepted_offer_turn: Optional[int] = None
    evidence: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    parse_ok: bool = True


class TerminalDecision(BaseModel):
    status: Literal["continue", "settled", "walk_away"] = "continue"
    accepted_offer_turn: Optional[int] = None
    evidence: str = ""
    votes: List[TerminalVote] = Field(default_factory=list)


class TermScore(BaseModel):
    buyer_score: int = Field(ge=-2, le=2)
    dimensions: Dict[str, int] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    parse_ok: bool = True


class A2EpisodeRecord(BaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    stage: Literal["smoke", "pilot", "full"]
    case_id: str
    arm: Literal["GG", "GQ", "QG", "QQ"]
    replicate: int
    attempt: int = 1
    buyer_model: str
    seller_model: str
    initiator: Literal["buyer", "seller"]
    valid: bool = True
    errors: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    episode: EpisodeOutput
    offer_ledger: List[OfferLedgerEntry] = Field(default_factory=list)
    terminal_decision: TerminalDecision
    terminal_history: List[TerminalDecision] = Field(default_factory=list)
    benchmark_result: Optional[EvaluationResult] = None
    a2_metrics: Dict[str, Any] = Field(default_factory=dict)
    instrumentation: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
