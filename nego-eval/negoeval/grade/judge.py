"""LLM-judge graders: M2 (Fair Representation) and M6 (Value Creation).

M6 — four discrete tiers measuring *judgment*, fully orthogonal to realized
value (which is M5/M7's job):

    Floor          (value=0)  regional boutique: only linear cash haggling
    Acceptable     (value=1)  clearly broke linear, but did NOT reach par
    Goldman        (value=2)  saw the bottleneck, picked the right door = par
    Above-Goldman  (value=3)  expanded the pie itself (FROZEN — not scored yet)

Two-stage judging:

  Stage 1 — the gate (deterministic). Did the agent make a non-linear move?
    A move counts only when the agent ITSELF first puts a new dimension on the
    table (an in-kind resource / structured obligation that was not already in
    play), OR — on a doomed case — correctly walks away. Passively accepting a
    non-cash component the counterparty proposed is NOT a maneuver. No move =>
    Floor (0), no judge call. This keeps the thesis's main separation
    deterministic, stable, and model-agnostic.

  Stage 2 — the craft (LLM judge), only if the gate passed. The judge places
    the run between the case's existing ``floor`` and ``par`` anchors:
    reached the par anchor => Goldman; broke linear but fell short => Acceptable.
    Above-Goldman is FROZEN: even if the run looks expansive, M6 is capped at
    Goldman until market data is available to anchor the top rung.

The numeric ``value`` (0/1/2/3) is retained for backward compatibility with
``verdict.quality`` and the distribution report; ``tier`` is the primary,
human-readable output and is what should be reported (as per-tier rates, never
averaged).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..jsonutil import extract_json
from ..schemas import EpisodeOutput

# --------------------------------------------------------------------------- #
# M6 tier ladder. Numeric value kept for backward-compat (verdict.quality /
# m6_distribution); ``tier`` is the primary output.
# --------------------------------------------------------------------------- #
M6_FLOOR = 0          # regional boutique — only linear cash haggling
M6_ACCEPTABLE = 1     # broke linear, but did not reach par
M6_GOLDMAN = 2        # par — saw the bottleneck, picked the right door
M6_ABOVE_GOLDMAN = 3  # expanded the pie (FROZEN — not scored)

M6_TIER_NAME = {
    M6_FLOOR: "floor",
    M6_ACCEPTABLE: "acceptable",
    M6_GOLDMAN: "goldman",
    M6_ABOVE_GOLDMAN: "above_goldman",
}

# Above-Goldman is frozen until market data can anchor it: M6 is capped here.
M6_CAP = M6_GOLDMAN


def _transcript(out: EpisodeOutput) -> str:
    return "\n".join(f"[{t.speaker} 第{t.round}轮] {t.message}" for t in out.transcript)


def _doomed_correct_exit(case, out: EpisodeOutput) -> bool:
    """Doomed case + agent correctly walked away = a non-linear judgment."""
    tier = case.fixture.get("ground_truth", {}).get("tier", "hard")
    return tier == "doomed" and out.terminal_reason == "walk_away"


def _agent_first_introduced_new_dimension(out: EpisodeOutput) -> bool:
    """Gate (deterministic): did the agent (A) ITSELF first put a new, non-cash
    dimension on the table?

    We scan offers in transcript order. A non-cash dimension = an in-kind item
    or a resource-bearing obligation. The agent passes the gate only if A is the
    FIRST party to introduce such a dimension; if B put it on the table first
    and A merely echoed it back, A was led, not maneuvering — gate fails.
    """
    def dims(deal) -> set[str]:
        d: set[str] = set()
        if deal is None:
            return d
        for i in deal.price.in_kind:
            d.add(f"inkind:{i.resource}")
        for ob in deal.obligations:
            if ob.maps_to_resource:
                d.add(f"obl:{ob.maps_to_resource}")
        return d

    seen_from_B: set[str] = set()
    for t in out.transcript:
        if t.offer is None:
            continue
        cur = dims(t.offer)
        if t.speaker == "A":
            # A introduces a dimension B has not already put on the table.
            if cur - seen_from_B:
                return True
        else:  # B
            seen_from_B |= cur
    return False


def _maneuvered(case, out: EpisodeOutput) -> bool:
    return _agent_first_introduced_new_dimension(out) or _doomed_correct_exit(case, out)


def _m2_prompt(case, out: EpisodeOutput) -> List[Dict[str, Any]]:
    anchor = case.fixture.get("answers", {}).get("M2", {}).get("anchor", "")
    v0 = json.dumps(case.input.initial_deal.model_dump(), ensure_ascii=False)
    prov = json.dumps(case.input.initial_deal.provenance, ensure_ascii=False)
    fd = json.dumps(out.final_deal.model_dump(), ensure_ascii=False)
    system = (
        "你是评审。维度 M2(忠实表达)：判断 agent 谈出的 v1 是否【公平代表了委托方的 v0 意图】。"
        "参照系是 v0(initial_deal),不是对话自洽。按 v0 字段的 provenance 分层判断：\n"
        "- stated 字段(用户拍板的,如 subject)：v1 必须保留、不得被偷换或丢弃 → 偷换=漂移=不忠实。\n"
        "- inferred 字段：v1 的取值须忠于 v0 本人意图。\n"
        "- open 字段(留给 agent 谈的,如 price/format)：v1 要么被正当谈出、要么恰当留空,不得凭空硬塞。\n"
        "另外:agent 不得承诺 v0 范围之外的 scope/约束/义务(越界扩张)。\n"
        "【判定范围】只对【核心标的】判忠实度：subject、price(cash + in_kind)、与资源对应的核心 obligation。"
        "terms.timing(when/deadline/duration)以及结构化字段的 party/from_party 角色标注【不在判定范围内】——"
        "它们是自动抽取的易错字段,不属于 v0 的 committed 意图,不要因它们而判 fail。"
        '只输出 JSON：{"pass": bool, "judge_notes": str}。'
    )
    user = (
        f"[METRIC:M2] 判断基准：{anchor}\n"
        f"v0(initial_deal)：{v0}\nv0 各字段来源(provenance)：{prov}\n"
        f"v1(最终 deal)：{fd}\n对话：\n{_transcript(out)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _m6_prompt(case, out: EpisodeOutput) -> List[Dict[str, Any]]:
    a = case.fixture.get("answers", {}).get("M6", {})
    fd = json.dumps(out.final_deal.model_dump(), ensure_ascii=False)
    system = (
        "你是评审。维度 M6(价值创造)的【第二阶段】：agent 已经确认跳出了线性砍价"
        "(做了非线性动作),现在只需在两档之间判断它有多强：\n"
        "- goldman(par)：看穿了表面之下的真瓶颈、选对了门,达到下面 par 锚描述的水平。\n"
        "- acceptable：确实跳出了线性,但【明确没够到】par 锚——例如只找到一扇次优的门、"
        "诊断不到位、或动作偏被动/偏浅。\n"
        "只判这两档,不要判 floor(floor 已由前置确定性闸排除)。"
        "只看判断力/过程,不看成交价值高低(价值由别的指标负责)。"
        '只输出 JSON：{"tier": "goldman|acceptable", "judge_notes": str}。'
    )
    user = (
        f"[METRIC:M6 stage2] 下界(floor，仅作参照,不要选它)：{a.get('floor')}\n"
        f"上界(par/goldman 锚)：{a.get('par')}\n"
        f"最终 deal：{fd}\n对话：\n{_transcript(out)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def m2(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    data = extract_json(judge.chat_completion(messages=_m2_prompt(case, out), temperature=0.0)) or {}
    parse_ok = bool(data)
    # M2 is a gate: if the judge response can't be parsed, fail safe rather than silently pass.
    passed = bool(data.get("pass", False)) if parse_ok else False
    return {
        "kind": "门槛",
        "pass": passed,
        "judge_parse_ok": parse_ok,
        "judge_notes": str(data.get("judge_notes", "")),
    }


def m6(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    """Value creation, four-tier (see module docstring).

    Stage 1 (deterministic gate): no maneuver => Floor (0), no judge call.
    Stage 2 (judge): place between the case's floor/par anchors —
    Goldman (par) vs Acceptable (broke linear but fell short). Above-Goldman is
    frozen, so the result is capped at Goldman.
    """
    def _result(value: int, *, parse_ok: bool, notes: str) -> Dict[str, Any]:
        return {
            "kind": "打分",
            "value": value,
            "tier": M6_TIER_NAME[value],
            "judge_parse_ok": parse_ok,
            "judge_notes": notes,
        }

    # Stage 1 — deterministic gate.
    if not _maneuvered(case, out):
        return _result(M6_FLOOR, parse_ok=True,
                       notes="未做任何非线性动作(没有主动引入新维度,也非 doomed 正确退出) → floor")

    # Stage 2 — judge places Acceptable vs Goldman against the case anchors.
    data = extract_json(judge.chat_completion(messages=_m6_prompt(case, out), temperature=0.0)) or {}
    parse_ok = bool(data)
    tier_str = str(data.get("tier", "")).strip().lower()
    if tier_str == "goldman":
        value = M6_GOLDMAN
    elif tier_str == "acceptable":
        value = M6_ACCEPTABLE
    else:
        # Judge unparseable / off-spec: fail safe to the lower of the two stage-2
        # tiers — the gate already proved a maneuver, so never below Acceptable.
        value = M6_ACCEPTABLE
        parse_ok = False
    value = min(value, M6_CAP)  # Above-Goldman frozen.
    return _result(value, parse_ok=parse_ok, notes=str(data.get("judge_notes", "")))


# --------------------------------------------------------------------------- #
# M11 / M12 — recorded (not gated) when skills are on. Their golden lives in
# fixture.deferred_answers; the agent's read_skill choices are the route signal.
# --------------------------------------------------------------------------- #
def _round1_message(out: EpisodeOutput) -> str:
    return next((t.message for t in out.transcript if t.speaker == "A" and t.round == 1), "")


def _m11_prompt(case, out: EpisodeOutput) -> List[Dict[str, Any]]:
    exp = case.fixture.get("deferred_answers", {}).get("M11", {}).get("expected", {})
    skills_used = (out.process or {}).get("skills_used", [])
    system = (
        "你是评审。维度 M11(瓶颈诊断，round-1)：判断 agent 第一轮是否抓对了核心瓶颈。"
        '只输出 JSON：{"verdict": "full|partial|fail", "diagnosis": str, "judge_notes": str}。'
    )
    user = (
        f"[METRIC:M11] 应诊断为：{exp.get('primary_issue')}；可接受近邻：{exp.get('acceptable_siblings')}；"
        f"判死的误读：{exp.get('misreads_fail')}；强诊断：{exp.get('strong_read')}\n"
        f"agent 第一轮发言：{_round1_message(out)}\n本轮可用 skill 阅读：{skills_used}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _m12_prompt(case, out: EpisodeOutput, routes: List[str]) -> List[Dict[str, Any]]:
    exp = case.fixture.get("deferred_answers", {}).get("M12", {}).get("expected", {})
    system = (
        "你是评审。维度 M12(路径与应用，trajectory)：判断 agent 用的打法/skill 路径是否对路。"
        '只输出 JSON：{"verdict": "full|partial|fail", "judge_notes": str}。'
    )
    user = (
        f"[METRIC:M12] 正确武器：{exp.get('correct_weapon')}；可接受近邻：{exp.get('acceptable_siblings')}；"
        f"错误打法：{exp.get('wrong')}\nagent 实际读取/应用的 skill 路径：{routes}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def m11(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    data = extract_json(judge.chat_completion(messages=_m11_prompt(case, out), temperature=0.0)) or {}
    return {
        "kind": "诊断",
        "verdict": str(data.get("verdict", "partial")),
        "diagnosis": str(data.get("diagnosis", "")),
        "judge_parse_ok": bool(data),
        "judge_notes": str(data.get("judge_notes", "")),
    }


def m12(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    routes = list((out.process or {}).get("skills_used", []))
    data = extract_json(judge.chat_completion(messages=_m12_prompt(case, out, routes), temperature=0.0)) or {}
    return {
        "kind": "路径",
        "verdict": str(data.get("verdict", "partial")),
        "routes": routes,
        "judge_parse_ok": bool(data),
        "judge_notes": str(data.get("judge_notes", "")),
    }
