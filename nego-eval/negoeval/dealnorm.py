"""Coerce a loosely-shaped LLM Deal dict into our strict schema.

Real models drift from the schema (``from_party: "counterparty"`` instead of
``"A"/"B"``, ``deliverables`` as a string, ``currency: "元"``, etc.). We normalize
before ``Deal.model_validate`` so a structurally-correct extraction isn't dropped.
"""

from __future__ import annotations

from typing import Any, Dict

_VALID_STATUS = {"draft", "settled", "walked_away"}
_CURRENCY_ALIASES = {"", "元", "rmb", "cny", "人民币", "￥", "¥"}


def coerce_deal(data: Dict[str, Any], *, provider_party: str = "B") -> Dict[str, Any]:
    """``provider_party`` = which seat provides non-cash resources (B for sell, A for buy)."""
    agent_party = "A" if provider_party == "B" else "B"
    d: Dict[str, Any] = dict(data or {})

    price = d.get("price") if isinstance(d.get("price"), dict) else {}
    cash = price.get("cash")
    if isinstance(cash, (int, float)):
        cash = {"amount": float(cash)}
    if not isinstance(cash, dict):
        cash = {}
    if str(cash.get("currency") or "").strip().lower() in _CURRENCY_ALIASES:
        cash["currency"] = "CNY"
    in_kind = []
    for item in price.get("in_kind") or []:
        if not isinstance(item, dict):
            continue
        in_kind.append(
            {
                "resource": str(item.get("resource", "")),
                "description": str(item.get("description", "")),
                # The controllable resources always flow from one side (B for sell,
                # A for buy); set it structurally so an extractor role-swap can't
                # corrupt M2/M4. (Forced, not trusted from the LLM.)
                "from_party": provider_party,
            }
        )
    d["price"] = {"cash": cash, "in_kind": in_kind}

    terms = d.get("terms") if isinstance(d.get("terms"), dict) else {}
    deliv = terms.get("deliverables")
    if isinstance(deliv, str):
        terms["deliverables"] = [deliv] if deliv.strip() else []
    elif not isinstance(deliv, list):
        terms["deliverables"] = []
    if not isinstance(terms.get("timing"), dict):
        terms["timing"] = {}
    d["terms"] = terms

    obligations = []
    for ob in d.get("obligations") or []:
        if not isinstance(ob, dict):
            continue
        mtr = ob.get("maps_to_resource") or None
        # Party is set structurally, not trusted from the LLM (which routinely
        # swaps A/B). An obligation that draws on a controllable resource
        # (maps_to_resource) must belong to the side that owns those resources
        # (provider_party); every other obligation — core-service delivery, cash
        # payment, coordination — belongs to the agent's own side. This kills the
        # "义务方张冠李戴" noise the judge kept having to excuse.
        party = provider_party if mtr else agent_party
        obligations.append(
            {
                "party": party,
                "text": str(ob.get("text", "")),
                "maps_to_resource": mtr,
            }
        )
    d["obligations"] = obligations

    if d.get("status") not in _VALID_STATUS:
        d["status"] = "draft"
    if not isinstance(d.get("provenance"), dict):
        d["provenance"] = {}
    if "subject" in d and not isinstance(d["subject"], str):
        d["subject"] = str(d["subject"])
    return d
