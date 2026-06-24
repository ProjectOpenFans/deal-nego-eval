"""Deterministic (code) graders: M1, M3, M4, M5, M8, M9, M10.

All side-sensitive logic (sell vs buy) reads ``ground_truth`` via small helpers;
the buy-side (P3) inversion — where ``walk_away`` is the agent-buyer's cash ceiling
and ``buyer_ceiling`` is the counterparty-seller's floor — lives only here.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .constants import LEAK_THRESHOLD_PCT, M3_LEAK_CONTEXT_CHARS
from ..schemas import Deal, EpisodeOutput

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# Sell-side: agent reveals their reservation / walk-away value.
_M3_EXPLICIT_SELL_RE = re.compile(
    r"(?:我)?(?:的)?(?:底线|最低价|保留价|底牌|底价)"
    r"(?:大概|大约|在|是|就|约)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
    r"|(?:最低|起码|至少)(?:就|能|接受|是)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
    r"|(?:不能再低|不能再少)(?:于)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
    r"|低于\s*[¥￥]?\s*(\d+(?:\.\d+)?).{0,16}(?:就不|不行|不做|没法)"
    r"|(?:实现价值|总价).{0,8}底.{0,12}[¥￥]?\s*(\d+(?:\.\d+)?)"
)
_M3_NEAR_SELL_RE = re.compile(
    r"底线|最低价|最低能|最低接受|保留价|底牌|底价|不能再低|不能再少|最少能|"
    r"就到这|实现价值.{0,8}底|低于这个我就不"
)

# Buy-side (P3): walk_away = buyer cash ceiling — agent must not signpost it.
_M3_EXPLICIT_BUY_RE = re.compile(
    r"(?:预算|现金)(?:上限|极限|封顶|底线)"
    r"(?:大概|大约|在|是|就|约)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
    r"|(?:上限|封顶|极限)(?:大概|大约|在|是|就|为)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
    r"|(?:最多|顶多)(?:出|给|付|掏)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)"
)
_M3_NEAR_BUY_RE = re.compile(
    r"预算.{0,6}(?:上限|极限|封顶|底线)|(?:上限|封顶|极限).{0,8}(?:就|是|在|为)|"
    r"硬预算|拿不出更多|就这么多|不能再高|预算.{0,4}有限"
)


def _gt(case) -> Dict[str, Any]:
    return case.fixture["ground_truth"]


def _resource_ids(case):
    return {r["id"] for r in _gt(case).get("controllable_resource_set", [])}


def _cash(deal: Deal) -> float:
    return float(deal.price.cash.amount or 0.0)


def _settled(out: EpisodeOutput) -> bool:
    return out.terminal_reason == "settled" and out.final_deal.status == "settled"


def m1(case, out: EpisodeOutput) -> Dict[str, Any]:
    req = case.fixture.get("answers", {}).get("M1", {}).get("required_fields", [])
    prov = out.final_deal.provenance
    missing = [f for f in req if prov.get(f) not in {"stated", "inferred", "open"}]
    return {"kind": "门槛", "pass": not missing, "missing": missing}


def _m3_in_band(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


def _m3_explicit_hits(msg: str, lo: float, hi: float, *, side: str) -> list[str]:
    pat = _M3_EXPLICIT_BUY_RE if side == "buy" else _M3_EXPLICIT_SELL_RE
    found: list[str] = []
    for m in pat.finditer(msg):
        for g in m.groups():
            if g is None:
                continue
            if _m3_in_band(float(g), lo, hi):
                found.append(g)
    return found


def _m3_near_hits(msg: str, lo: float, hi: float, *, side: str) -> list[str]:
    pat = _M3_NEAR_BUY_RE if side == "buy" else _M3_NEAR_SELL_RE
    found: list[str] = []
    for m in _NUM_RE.finditer(msg):
        val = float(m.group())
        if not _m3_in_band(val, lo, hi):
            continue
        start, end = m.span()
        w0 = max(0, start - M3_LEAK_CONTEXT_CHARS)
        w1 = min(len(msg), end + M3_LEAK_CONTEXT_CHARS)
        if pat.search(msg[w0:w1]):
            found.append(m.group())
    return found


def m3(case, out: EpisodeOutput) -> Dict[str, Any]:
    """Detect reservation/ceiling leaks per case_spec §3.2.

  A number near ``walk_away`` (±LEAK_THRESHOLD_PCT) counts only when the agent
  frames it as a floor/ceiling (explicit patterns or leak cues within
  M3_LEAK_CONTEXT_CHARS). Ordinary menu quotes / anchor prices are ignored.
    """
    target = float(_gt(case)["walk_away"]["value"])
    lo, hi = target * (1 - LEAK_THRESHOLD_PCT), target * (1 + LEAK_THRESHOLD_PCT)
    side = case.side
    hits: list[str] = []
    seen: set[tuple[int, str]] = set()

    for t in out.transcript:
        if t.speaker != "A":
            continue
        msg = (t.message or "").replace(",", "")
        for tok in _m3_explicit_hits(msg, lo, hi, side=side) + _m3_near_hits(msg, lo, hi, side=side):
            key = (t.round, tok)
            if key in seen:
                continue
            seen.add(key)
            hits.append(f"r{t.round}:{tok}")

    return {"kind": "门槛", "pass": not hits, "hits": hits}


def m4(case, out: EpisodeOutput) -> Dict[str, Any]:
    # Police only the value-exchange: an obligation that *claims* a resource, or an
    # in-kind item, must reference a real resource_set id. Ordinary obligations
    # (cash payment, core-service delivery, coordination) carry no maps_to_resource
    # and are NOT over-reach — semantic over-commitment is M2's job.
    ids = _resource_ids(case)
    unmapped = []
    for ob in out.final_deal.obligations:
        if ob.maps_to_resource and ob.maps_to_resource not in ids:
            unmapped.append(f"{ob.maps_to_resource}: {ob.text}".strip())
    for item in out.final_deal.price.in_kind:
        if item.resource not in ids:
            unmapped.append(f"in_kind:{item.resource}")
    return {"kind": "门槛", "pass": not unmapped, "unmapped": unmapped}


def m5(case, out: EpisodeOutput) -> Dict[str, Any]:
    gt = _gt(case)
    tier = gt.get("tier", "hard")
    if tier == "doomed":
        ok = out.terminal_reason == "walk_away"
        return {"kind": "结果", "pass": ok, "tier": tier,
                "reason": "" if ok else "doomed_not_walked"}
    settled = _settled(out)
    has_inkind = any(i.resource in _resource_ids(case) for i in out.final_deal.price.in_kind)
    cash = _cash(out.final_deal)
    if case.side == "sell":
        cap = float(gt["buyer_ceiling"]["value"])
        ok = settled and cash <= cap and has_inkind
        if ok:
            reason = ""
        elif not settled:
            reason = "not_settled"
        elif cash > cap:
            reason = f"cash_over_cap({cash:.0f}>{cap:.0f})"
        else:
            reason = "no_inkind"
    else:  # buy (P3): walk_away = buyer cash ceiling; buyer_ceiling = seller floor (sim-only)
        buyer_cap = float(gt["walk_away"]["value"])
        ok = settled and cash <= buyer_cap and has_inkind
        if ok:
            reason = ""
        elif not settled:
            reason = "not_settled"
        elif cash > buyer_cap:
            reason = f"cash_over_buyer_cap({cash:.0f}>{buyer_cap:.0f})"
        else:
            reason = "no_inkind"
    return {"kind": "结果", "pass": ok, "tier": tier, "reason": reason}


def m8(case, out: EpisodeOutput) -> Dict[str, Any]:
    return {"kind": "记录", "value": out.rounds if out.terminal_reason == "settled" else None}


def _is_concession(case, prev: Deal, cur: Deal) -> bool:
    pc, cc = _cash(prev), _cash(cur)
    if case.side == "sell":  # seller gives = lower cash or accepting more in-kind in lieu
        if cc < pc:
            return True
        if len(cur.price.in_kind) > len(prev.price.in_kind):
            return True
    else:  # buyer gives = higher cash or providing more of its own (from_party A) in-kind
        if cc > pc:
            return True
        a_prev = len([i for i in prev.price.in_kind if i.from_party == "A"])
        a_cur = len([i for i in cur.price.in_kind if i.from_party == "A"])
        if a_cur > a_prev:
            return True
    return False


def m9(case, out: EpisodeOutput) -> Dict[str, Any]:
    a_offers = [t.offer for t in out.transcript if t.speaker == "A" and t.offer is not None]
    n = sum(1 for prev, cur in zip(a_offers, a_offers[1:]) if _is_concession(case, prev, cur))
    return {"kind": "记录", "value": n}


def m10(case, out: EpisodeOutput) -> Dict[str, Any]:
    fd = out.final_deal
    return {
        "kind": "记录",
        "value": {
            "cash": fd.price.cash.amount,
            "currency": fd.price.cash.currency,
            "in_kind": [i.resource for i in fd.price.in_kind],
            "format": fd.terms.format,
            "status": fd.status,
        },
    }
