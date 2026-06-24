"""Deterministic, offline stub provider — lets the whole pipeline run with no
LLM endpoint. It is fixture-aware: from a ``CaseFile`` it synthesizes a valid
"par" deal (cash within the counterparty's cap + the highest-valued non-cash
resources from the case's resource set), so the deterministic graders have real
structure to score.

Agent profiles drive the three canonical outcomes used by tests:
  - ``par``  : round-1 anchor, round-2 compound offer -> sim ACCEPTs -> settled
  - ``cave`` : cash-only every round -> sim route-out WALK -> walked_away
  - ``leak`` : par, but the agent text reveals the walk-away number (M3 fails)

Round tracking: each provider instance counts its own ``chat_completion`` calls,
which in our orchestrator loop happen exactly once per round per role.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .types import ToolCallResult


# --------------------------------------------------------------------------- #
# Fixture-derived deal builders (shared by agent text, extractor, sim)
# --------------------------------------------------------------------------- #
def _gt(case) -> Dict[str, Any]:
    return case.fixture["ground_truth"]


def _labels(case) -> Dict[str, str]:
    return {r["id"]: r.get("label", r["id"]) for r in _gt(case).get("controllable_resource_set", [])}


def _noncash_resources(case) -> List[str]:
    gt = _gt(case)
    val = gt.get("in_kind_valuation", {})
    ids = [r["id"] for r in gt.get("controllable_resource_set", []) if r["id"] != "cash"]
    ids.sort(key=lambda i: float(val.get(i, 0)), reverse=True)
    return ids


def _provider_party(case) -> str:
    """Seat that provides the non-cash resources (resource_set = the buyer's)."""
    return "B" if case.side == "sell" else "A"


def _anchor_cash(case) -> float:
    gt = _gt(case)
    if case.side == "sell":
        return float(gt["walk_away"]["value"]) * 2.0  # seller opens high (M3-safe)
    return float(gt["buyer_ceiling"]["value"])  # buyer opens at the seller floor (lowball)


def _settle_cash(case) -> float:
    gt = _gt(case)
    if case.side == "sell":
        return float(gt["buyer_ceiling"]["value"])  # cash within the buyer's cap
    lo = float(gt["buyer_ceiling"]["value"])  # seller floor
    hi = float(gt["walk_away"]["value"])  # buyer ceiling
    return float(int((lo + hi) // 2))


def _cave_cash(case) -> float:
    gt = _gt(case)
    if case.side == "sell":
        return float(gt["walk_away"]["value"]) * 1.5  # stuck high, no exchange
    return float(gt["buyer_ceiling"]["value"]) * 0.75  # buyer lowballs below seller floor


def _base_terms(case) -> Dict[str, Any]:
    deadline = case.input.initial_deal.terms.timing.deadline
    return {
        "timing": {"when": None, "deadline": deadline, "duration": None},
        "format": "线上",
        "deliverables": [case.input.initial_deal.subject],
        "delivery_standard": None,
    }


_FULL_PROVENANCE = {
    "subject": "stated",
    "price.cash": "inferred",
    "price.in_kind": "inferred",
    "terms.format": "inferred",
    "obligations": "inferred",
    "status": "inferred",
}


def _anchor_offer(case) -> Dict[str, Any]:
    return {
        "subject": case.input.initial_deal.subject,
        "price": {"cash": {"amount": _anchor_cash(case), "currency": "CNY"}, "in_kind": []},
        "terms": _base_terms(case),
        "obligations": [],
        "status": "draft",
        "provenance": dict(_FULL_PROVENANCE),
    }


def par_offer(case, *, settled: bool = False, top_n: int = 2) -> Dict[str, Any]:
    """A compound offer: low cash + the highest-valued non-cash resources."""
    labels = _labels(case)
    party = _provider_party(case)
    ids = [i for i in _noncash_resources(case) if float(_gt(case).get("in_kind_valuation", {}).get(i, 0)) > 0][:top_n]
    if not ids:  # fall back to any non-cash id if none carry a valuation
        ids = _noncash_resources(case)[:1]
    in_kind = [{"resource": i, "description": labels.get(i, i), "from_party": party} for i in ids]
    obligations = [{"party": party, "text": f"提供{labels.get(i, i)}", "maps_to_resource": i} for i in ids]
    return {
        "subject": case.input.initial_deal.subject,
        "price": {"cash": {"amount": _settle_cash(case), "currency": "CNY"}, "in_kind": in_kind},
        "terms": _base_terms(case),
        "obligations": obligations,
        "status": "settled" if settled else "draft",
        "provenance": dict(_FULL_PROVENANCE),
    }


def _cave_offer(case) -> Dict[str, Any]:
    return {
        "subject": case.input.initial_deal.subject,
        "price": {"cash": {"amount": _cave_cash(case), "currency": "CNY"}, "in_kind": []},
        "terms": _base_terms(case),
        "obligations": [],
        "status": "draft",
        "provenance": dict(_FULL_PROVENANCE),
    }


# --------------------------------------------------------------------------- #
# Stub provider
# --------------------------------------------------------------------------- #
class StubProvider:
    """One stub per role per episode (fresh counters)."""

    def __init__(self, role: str, *, case=None, agent_profile: str = "par"):
        self.role = role
        self.case = case
        self.profile = agent_profile
        self._n = 0

    # -- agent ------------------------------------------------------------- #
    def _agent_text(self, r: int) -> str:
        case = self.case
        subj = case.input.initial_deal.subject
        if self.profile == "cave":
            return f"我再让一点，现金 ¥{int(_cave_cash(case))}，就这个数，别的我没法给。"
        if r == 1:
            if case.side == "sell":
                return f"我可以做这次「{subj}」。我先按 ¥{int(_anchor_cash(case))} 报，我们看看怎么谈成。"
            return f"我想请你来做「{subj}」，预算有限，先按 ¥{int(_anchor_cash(case))} 试探有没有合作空间。"
        labels = _labels(case)
        ids = [i for i in _noncash_resources(case) if float(_gt(case).get("in_kind_valuation", {}).get(i, 0)) > 0][:2]
        res_text = "、".join(labels.get(i, i) for i in ids) or "一项非现金安排"
        line = f"这样吧：现金我出 ¥{int(_settle_cash(case))}，再把「{res_text}」绑进这次合作，对双方都更值，就按这个成交。"
        if self.profile == "leak":
            line += f" 说实话我的底线大概在 ¥{int(_gt(case)['walk_away']['value'])} 这个量级，低于这个我就不做了。"
        return line

    def _extracted(self, r: int) -> Dict[str, Any]:
        if self.profile == "cave":
            return _cave_offer(self.case)
        if r == 1:
            return _anchor_offer(self.case)
        return par_offer(self.case, settled=False)

    def _sim_turn(self, r: int) -> Dict[str, Any]:
        if self.profile == "cave":
            if r >= 3:
                return {"message": "你一直在压价又没有别的方案，那这次先算了。", "action": "WALK", "offer": None}
            return {"message": "还是太贵了，你看能不能换个方式？", "action": "CONTINUE", "offer": None}
        if r == 1:
            return {"message": "我特别想做成，但这个数我现在真的拿不出来。", "action": "CONTINUE", "offer": None}
        return {"message": "这个组合我可以接受，就这么定。", "action": "ACCEPT", "offer": par_offer(self.case, settled=False)}

    def _judge(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        blob = " ".join(str(m.get("content", "")) for m in messages)
        if "M11" in blob:
            return {"verdict": "partial", "diagnosis": "(stub) 见 round-1 发言", "judge_notes": "stub: 记录 round-1 诊断"}
        if "M12" in blob:
            return {"verdict": "partial", "judge_notes": "stub: 记录所用 skill 路径"}
        if "M6" in blob:
            return {"value": 1, "judge_notes": "stub: 达到 par(搭出双向交换)"}
        return {"pass": True, "judge_notes": "stub: 表达忠实、无越界扩范围"}

    # -- provider protocol ------------------------------------------------- #
    def chat_completion(self, messages, temperature=None, max_tokens=None, enable_thinking=None) -> str:
        if self.role == "judge":
            return json.dumps(self._judge(messages), ensure_ascii=False)
        self._n += 1
        r = self._n
        if self.role == "agent":
            return self._agent_text(r)
        if self.role == "extractor":
            return json.dumps(self._extracted(r), ensure_ascii=False)
        if self.role == "sim":
            return json.dumps(self._sim_turn(r), ensure_ascii=False)
        return ""

    # Skills the stub agent reads (round >= 2): triage first, then the correct
    # weapon. This gives M12 a non-trivial route to record.
    _SKILL_PLAN = ["deal-diagnosis", "term-reframing"]

    def chat_completion_with_tools(self, messages, tools, **kwargs) -> ToolCallResult:
        # Only the agent goes through the tool loop. Read the planned skills one at
        # a time (each read produces a tool result message), then stop.
        names = {t["function"]["name"] for t in tools}
        read_count = sum(1 for m in messages if m.get("role") == "tool")
        if "read_skill" in names and read_count < len(self._SKILL_PLAN):
            return ToolCallResult(
                content="",
                tool_calls=[
                    {"id": f"sk_{read_count}", "name": "read_skill", "arguments": {"name": self._SKILL_PLAN[read_count]}}
                ],
                finish_reason="tool_calls",
            )
        return ToolCallResult(content="", tool_calls=[], finish_reason="stop")
