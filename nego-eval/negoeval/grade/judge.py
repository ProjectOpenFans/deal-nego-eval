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
import re
from typing import Any, Dict, List, Optional

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


def judge_json(judge, messages, *, retries: int = 2) -> tuple[Dict[str, Any], str]:
    """Call a judge and parse its JSON, retrying only when nothing came back.

    An empty completion is a transport hiccup, not a judgment — the endpoints
    run with ``max_retries: 0``, so without this a momentary blip is recorded as
    an unparseable answer and fail-safed to the floor tier. That is how a flaky
    minute turns into a dozen fabricated zeros.

    A non-empty but unparseable reply is NOT retried: at temperature 0 the model
    would just repeat itself, and the raw text is worth more as a diagnostic.
    Returns ``(parsed_or_empty, raw)`` so callers can keep the raw for triage.
    """
    raw = ""
    for attempt in range(retries + 1):
        try:
            raw = judge.chat_completion(messages=messages, temperature=0.0) or ""
        except Exception:
            raw = ""
        if raw.strip():
            break
    return (extract_json(raw) or {}), raw


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
        "- stated 字段(用户拍板的,如 subject)：v1 必须忠于该意图。\n"
        "  ✓ 允许【正当具体化】：把一个宽泛的 stated 意图(如'想参与进来达成某种合作')在谈判中\n"
        "    收敛成一个仍落在原意图范围内的具体形式(如'内容制作协作'/'本地合作搭档'/'线下试点')\n"
        "    —— 这是正常的谈判收敛, 算忠实, 不要因为字面措辞变了就判 fail。\n"
        "  ✗ 只有【偷换主题】才算不忠实：把标的换成原意图之外的另一件事(如用户要'参与合作'\n"
        "    却变成'纯财务投资'、或换成一个与原意图无关的交易)。判断看'是否还在原意图范围内', 不看措辞是否逐字保留。\n"
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
    data, raw = judge_json(judge, _m2_prompt(case, out))
    parse_ok = bool(data)
    # M2 is a gate: if the judge response can't be parsed, fail safe rather than silently pass.
    passed = bool(data.get("pass", False)) if parse_ok else False
    return {
        "kind": "门槛",
        "pass": passed,
        "judge_parse_ok": parse_ok,
        "judge_raw_head": "" if parse_ok else raw[:240],
        "judge_notes": str(data.get("judge_notes", "")),
    }



# === R4_SCORER_PATCH ===
# R4 五档 tier (锁定的 rubric)。floor 也由 judge 判，无确定性门。
R4_TIER_NUM = {"floor": 0, "crude": 1, "sound": 2, "sharp": 3, "brilliant": 4}

_R4_TIER_ALIASES = {
    **{name: value for name, value in R4_TIER_NUM.items()},
    **{str(value): value for value in R4_TIER_NUM.values()},
    # Chinese names appear whenever the rubric is quoted back in the reply.
    "地板": 0, "粗糙": 1, "合格": 2, "站得住": 2, "精到": 3, "高明": 3, "卓越": 4,
}
M6_R4_TIER_NAME = {v: k for k, v in R4_TIER_NUM.items()}
_R4_LEADING_INT = re.compile(r"^\s*([0-4])\b")
_R4_ANY_NAME = re.compile(r"(floor|crude|sound|sharp|brilliant)", re.I)


def coerce_r4_tier(raw: Any) -> Optional[int]:
    """Map whatever the judge put in ``tier`` onto 0-4, or None if unreadable.

    The strict lookup this replaces only accepted the five lowercase English
    names, so a judge answering ``{"tier": 3}`` — correct, just numeric — was
    recorded as a parse failure and fail-safed to floor. That silently rewrote
    real gradings as zeros; few-shot exemplars that render tiers as "3 sharp"
    are enough to trigger it across a whole run. Accept the answer in any of the
    forms a model actually emits, and reserve None for genuinely absent values.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = int(raw)
        return value if 0 <= value <= 4 else None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in _R4_TIER_ALIASES:
        return _R4_TIER_ALIASES[text]
    leading = _R4_LEADING_INT.match(text)      # "3 sharp", "3 - sharp"
    if leading:
        return int(leading.group(1))
    named = _R4_ANY_NAME.search(text)          # "tier: sharp", "Sharp (3)"
    if named:
        return R4_TIER_NUM[named.group(1).lower()]
    for zh, value in _R4_TIER_ALIASES.items():
        if not zh.isascii() and zh in text:
            return value
    return None

R4_RUBRIC = (
    "你是一位资深交易员，评判一笔【已结束的谈判】里 agent 的 deal making 水准，给一个 tier(0-4)。\n"
    "tier 衡量的是【解是否恰好匹配这个 case 的真实难度】——不是解有多复杂、多花哨。\n\n"
    "档位：\n"
    "0 Floor：没做成 deal，或只在单一维度(现金/常规框架)上死磕、撞死在对这个 case 行不通的常规打法上。没有真正的 deal making。\n"
    "1 Crude：跳出了最表层的常规打法，但极粗糙——方向对、条款空泛，没说清关键，像草稿。\n"
    "2 Sound(par/合格)：搭出一个站得住的 deal，核心交换对、该处理的关键点处理了、能落地。合格，但没有特别见功力的一手。\n"
    "3 Sharp：在 Sound 之上有一手 load-bearing 的精到操作，恰到好处地咬住了这个 case 的难度命门，明显更见功力。\n"
    "4 Brilliant：Sharp 之上还有一手别人想不到的——非显然的洞察或框架级重构，且整体依然干净。稀有。\n\n"
    "原则：\n"
    "1. 看 load-bearing，不看数量。一个解决关键的条款胜过五个无关痛痒的。\n"
    "2. 警惕过度堆砌。好 deal 恰好够(minimally sufficient)。把一堆东西堆进一个简单/一次性交易=负担，应判低不应判高。\n"
    "3. case-specific。是否高明要对照【本 case 的难度命门】判：难点要求的重构=高明；难点不要求却硬上的复杂=过度，降档。\n"
    "4. 识别灵活高明。简洁里一手情境化的精到，胜过套路化、面面俱到但平庸的 deal。\n"
    "5. 整体判断，非逐项加总。\n"
)

def _r4_tier_prompt(case, out: EpisodeOutput) -> List[Dict[str, Any]]:
    gt = case.fixture.get("ground_truth", {})
    tr = case.fixture.get("tier_reference", {})
    fd = json.dumps(out.final_deal.model_dump(), ensure_ascii=False)
    system = (
        R4_RUBRIC +
        '\n只输出 JSON：{"tier": "floor|crude|sound|sharp|brilliant", "judge_notes": str}。'
    )
    user = (
        f"[本 case 难度命门] {tr.get('difficulty_note','')}\n"
        f"[常规 deal 为何失效] {gt.get('conventional_deal_fails_why','')}\n\n"
        f"[各档在本 case 长什么样 (anchor)]\n"
        f"- Floor: {tr.get('T0_floor','')}\n"
        f"- Crude: {tr.get('T1_crude','')}\n"
        f"- Sound: {tr.get('T2_sound','')}\n"
        f"- Sharp: {tr.get('T3_sharp','')}\n"
        f"- Brilliant: {tr.get('T4_brilliant','')}\n\n"
        f"[最终 deal] {fd}\n[对话]\n{_transcript(out)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def _r4_no_deal_floor(case, out: EpisodeOutput) -> Optional[Dict[str, Any]]:
    """R4 tier 0 is defined as 没做成 deal — enforce it deterministically.

    Left to the judge this leaked badly: a ``round_cap`` episode still carries a
    draft ``final_deal``, so the judge graded the *package on the table* and
    handed out sound/sharp to negotiations that concluded nothing (A2 pilot: 25
    round-cap episodes, all scored 2–3, versus 0–1 for walk-aways). Arm-level M6
    then tracked which arm walked rather than which arm dealt.

    The one legitimate no-deal is a doomed case exited correctly, which is a
    judgment call worth grading, so it still reaches the judge.
    """
    if out.terminal_reason == "settled":
        return None
    if _doomed_correct_exit(case, out):
        return None
    return {
        "kind": "打分",
        "value": R4_TIER_NUM["floor"],
        "tier": "floor",
        "judge_parse_ok": True,
        "judge_notes": f"未达成 deal（terminal={out.terminal_reason}）→ 按 rubric 判 floor，不调用 judge。",
    }


def _m6_r4(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    gated = _r4_no_deal_floor(case, out)
    if gated is not None:
        return gated
    data, raw = judge_json(judge, _r4_tier_prompt(case, out))
    value = coerce_r4_tier(data.get("tier"))
    if value is None:
        # Genuinely unreadable: fail safe to floor, and keep the raw head so the
        # failure can be diagnosed instead of just counted.
        return {"kind": "打分", "value": 0, "tier": "floor", "judge_parse_ok": False,
                "judge_raw_head": (raw or "")[:240],
                "judge_notes": str(data.get("judge_notes", ""))}
    return {"kind": "打分", "value": value, "tier": M6_R4_TIER_NAME[value],
            "judge_parse_ok": True, "judge_notes": str(data.get("judge_notes", ""))}


def m6(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    if case.meta.get("r4"):
        return _m6_r4(case, out, judge)
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
    data, _raw = judge_json(judge, _m6_prompt(case, out))
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
        f"错误打法：{exp.get('wrong')}\n"
        f"agent 自愿读取/应用的 skill 路径（系统强制注入的 deal-diagnosis 不在此列，不作评判）：{routes}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def m11(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    # 门控：只有当 case 设计上有瓶颈要诊断（primary_issue 非空）才评 M11。
    # 无瓶颈（primary_issue=None / expected 为空）→ N/A，不为判断而判断，避免 judge 在 None 上自由心证翻转。
    exp = case.fixture.get("deferred_answers", {}).get("M11", {}).get("expected", {})
    if not exp or exp.get("primary_issue") in (None, "", "None"):
        return {
            "kind": "诊断",
            "verdict": "n/a",
            "diagnosis": "",
            "judge_parse_ok": True,
            "judge_notes": "该 case 无瓶颈需诊断（primary_issue=None），M11 不适用。",
            "applicable": False,
        }
    data, _raw = judge_json(judge, _m11_prompt(case, out))
    return {
        "kind": "诊断",
        "verdict": str(data.get("verdict", "partial")),
        "diagnosis": str(data.get("diagnosis", "")),
        "judge_parse_ok": bool(data),
        "judge_notes": str(data.get("judge_notes", "")),
        "applicable": True,
    }


def m12(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    # routes = the agent's VOLUNTARY read_skill choices. The harness force-injects
    # deal-diagnosis every episode (recorded in process.skills_forced) — a forced
    # route is not a trajectory choice and must not be judged as one. Legacy
    # results (no skills_forced field) get the same exemption by filtering.
    proc = out.process or {}
    routes = list(proc.get("skills_used", []))
    if "skills_forced" not in proc and "deal-diagnosis" in routes:
        routes.remove("deal-diagnosis")
    # Mirror M11's gating: if the case defines no expected path, N/A — do not ask
    # the judge to freestyle on None (it fails every on-arm run of such cases).
    exp = case.fixture.get("deferred_answers", {}).get("M12", {}).get("expected", {})
    if not exp or not any(exp.get(k) for k in ("correct_weapon", "acceptable_siblings", "wrong")):
        return {
            "kind": "路径",
            "verdict": "n/a",
            "routes": routes,
            "judge_parse_ok": True,
            "judge_notes": "该 case 未定义期望 skill 路径（expected 为空），M12 不适用。",
            "applicable": False,
        }
    data, _raw = judge_json(judge, _m12_prompt(case, out, routes))
    return {
        "kind": "路径",
        "verdict": str(data.get("verdict", "partial")),
        "routes": routes,
        "judge_parse_ok": bool(data),
        "judge_notes": str(data.get("judge_notes", "")),
    }
