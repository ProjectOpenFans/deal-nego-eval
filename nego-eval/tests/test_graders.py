"""Grader checks against the two GoldRuns documented in case_spec.md §7.3.

These validate the evaluator independently of the agent/LLM: we hand-build the
EpisodeOutput and assert the metrics match the documented ``expected``.
"""

from __future__ import annotations

import negoeval  # noqa: F401
from negoeval.cases import LEGACY_CASES_DIR, load_case
from negoeval.grade.deterministic import m3
from negoeval.grade.evaluator import _repeat_judge, evaluate
from negoeval.llm.registry import build_provider
from negoeval.schemas import (
    Cash,
    Deal,
    EpisodeOutput,
    InKindItem,
    Obligation,
    Price,
    Terms,
    Timing,
    Turn,
)

_REQ_PROV = {
    "subject": "stated",
    "price.cash": "inferred",
    "price.in_kind": "inferred",
    "terms.format": "inferred",
    "obligations": "inferred",
    "status": "inferred",
}


def _judge(case):
    return build_provider("judge", mode="stub", case=case)


def _anchor_deal():
    return Deal(
        subject="1:1 session",
        price=Price(cash=Cash(amount=1500, currency="CNY"), in_kind=[]),
        terms=Terms(timing=Timing(deadline="近期"), format="线上"),
        status="draft",
        provenance=dict(_REQ_PROV),
    )


def _compound_deal(status="draft"):
    return Deal(
        subject="1:1 session — 转行 + 金融/AI 洞见",
        price=Price(
            cash=Cash(amount=200, currency="CNY"),
            in_kind=[
                InKindItem(resource="product_perspective", description="产品试用反馈+用户访谈", from_party="B"),
                InKindItem(resource="testimonial", description="一句可用推荐", from_party="B"),
            ],
        ),
        terms=Terms(timing=Timing(deadline="近期"), format="饭局", deliverables=["1:1 session"]),
        obligations=[
            Obligation(party="B", text="做一轮产品试用反馈+用户访谈", maps_to_resource="product_perspective"),
            Obligation(party="B", text="给一句可用推荐", maps_to_resource="testimonial"),
        ],
        status=status,
        provenance=dict(_REQ_PROV),
    )


def test_goldrun_par_deal_all_pass():
    p1 = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    out = EpisodeOutput(
        episode_id="P1",
        final_deal=_compound_deal(status="settled"),
        transcript=[
            Turn(round=1, speaker="A", message="我做一次 1:1，先按 ¥1500 报。", offer=_anchor_deal()),
            Turn(round=1, speaker="B", message="太贵了，负担不起。", offer=None),
            Turn(
                round=2,
                speaker="A",
                message="现金你出 ¥200，再帮我做产品反馈+用户访谈、给一句推荐，边吃饭边聊，就这么定。",
                offer=_compound_deal(),
            ),
            Turn(round=2, speaker="B", message="可以，就这么定。", offer=_compound_deal()),
        ],
        rounds=2,
        terminal_reason="settled",
        process={"skills": "on", "agent_profile": "par", "mode": "stub", "skills_used": ["deal-diagnosis"]},
    )
    res = evaluate(p1, out, run_id="gold-par", judge_provider=_judge(p1))
    for m in ("M1", "M2", "M3", "M4"):
        assert res.metrics[m]["pass"] is True, (m, res.metrics[m])
    assert res.metrics["M5"]["pass"] is True
    assert res.metrics["M6"]["value"] == 1
    assert res.metrics["M8"]["value"] == 2
    assert res.metrics["M9"]["value"] == 1
    assert res.verdict.case_pass is True and res.verdict.quality == 1


def test_goldrun_cave_below_floor_fails():
    p1 = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    cash_only = Deal(
        subject="1:1 session",
        price=Price(cash=Cash(amount=200, currency="CNY"), in_kind=[]),
        terms=Terms(timing=Timing(deadline="近期"), format="线上"),
        status="settled",
        provenance=dict(_REQ_PROV),
    )
    out = EpisodeOutput(
        episode_id="P1",
        final_deal=cash_only,
        transcript=[
            Turn(round=1, speaker="A", message="先按 ¥1500。", offer=_anchor_deal()),
            Turn(round=2, speaker="A", message="那就 ¥200 成交吧。", offer=cash_only),
            Turn(round=2, speaker="B", message="好，就 ¥200。", offer=cash_only),
        ],
        rounds=2,
        terminal_reason="settled",
        process={"skills": "on", "agent_profile": "cave", "mode": "stub", "skills_used": []},
    )
    res = evaluate(p1, out, run_id="gold-cave", judge_provider=_judge(p1))
    assert res.metrics["M5"]["pass"] is False  # no non-cash component
    assert res.metrics["M6"]["value"] == 0  # no maneuver -> floor
    assert res.verdict.case_pass is False


def test_m3_passes_menu_quote_without_floor_language():
    """Quoting a price in the walk-away band is not a leak without floor cues."""
    p1 = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    out = EpisodeOutput(
        episode_id="P1",
        final_deal=_anchor_deal(),
        transcript=[
            Turn(
                round=3,
                speaker="A",
                message="方案一：20分钟快问快答，价格800元整。方案二：价值交换版，500元。",
                offer=None,
            ),
        ],
        rounds=3,
        terminal_reason="round_cap",
        process={},
    )
    res = m3(p1, out)
    assert res["pass"] is True, res


def test_repeated_m2_uses_strict_majority_and_keeps_samples():
    samples = iter(
        [
            {"kind": "门槛", "pass": True, "judge_parse_ok": True, "judge_notes": "a"},
            {"kind": "门槛", "pass": False, "judge_parse_ok": True, "judge_notes": "b"},
            {"kind": "门槛", "pass": True, "judge_parse_ok": True, "judge_notes": "c"},
        ]
    )

    result = _repeat_judge("M2", lambda: next(samples), 3)

    assert result["pass"] is True
    assert result["judge_distribution"] == {"pass": 2, "fail": 1}
    assert result["judge_agreement"] == 2 / 3
    assert len(result["judge_samples"]) == 3


def test_repeated_m6_uses_conservative_lower_median():
    samples = iter(
        [
            {"kind": "打分", "value": 4, "tier": "brilliant", "judge_parse_ok": True},
            {"kind": "打分", "value": 1, "tier": "crude", "judge_parse_ok": True},
            {"kind": "打分", "value": 3, "tier": "sharp", "judge_parse_ok": True},
            {"kind": "打分", "value": 2, "tier": "sound", "judge_parse_ok": True},
        ]
    )

    result = _repeat_judge("M6", lambda: next(samples), 4)

    assert result["value"] == 2
    assert result["tier"] == "sound"
    assert result["judge_distribution"] == {"1": 1, "2": 1, "3": 1, "4": 1}


def test_repeated_diagnostic_tie_resolves_conservatively():
    samples = iter(
        [
            {"kind": "诊断", "verdict": "full", "judge_parse_ok": True},
            {"kind": "诊断", "verdict": "fail", "judge_parse_ok": True},
        ]
    )

    result = _repeat_judge("M11", lambda: next(samples), 2)

    assert result["verdict"] == "fail"
    assert result["judge_agreement"] == 0.5


def test_m3_fails_explicit_sell_floor_leak():
    p1 = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    out = EpisodeOutput(
        episode_id="P1",
        final_deal=_anchor_deal(),
        transcript=[
            Turn(
                round=2,
                speaker="A",
                message="说实话我的底线大概在 ¥800 这个量级，低于这个我就不做了。",
                offer=None,
            ),
        ],
        rounds=2,
        terminal_reason="round_cap",
        process={},
    )
    res = m3(p1, out)
    assert res["pass"] is False
    assert "r2:800" in res["hits"]


def test_m3_fails_buy_side_budget_ceiling():
    p3 = load_case(LEGACY_CASES_DIR / "P3.jsonc")
    out = EpisodeOutput(
        episode_id="P3",
        final_deal=_anchor_deal(),
        transcript=[
            Turn(
                round=2,
                speaker="A",
                message="我的预算上限就是6000元，不能再高了。",
                offer=None,
            ),
        ],
        rounds=2,
        terminal_reason="round_cap",
        process={},
    )
    res = m3(p3, out)
    assert res["pass"] is False
    assert any("6000" in h for h in res["hits"])


def test_m3_passes_buy_side_probe_quote_without_ceiling_language():
    p3 = load_case(LEGACY_CASES_DIR / "P3.jsonc")
    out = EpisodeOutput(
        episode_id="P3",
        final_deal=_anchor_deal(),
        transcript=[
            Turn(
                round=1,
                speaker="A",
                message="我们这边先按6000元报价试探合作空间，您看是否方便聊聊？",
                offer=None,
            ),
        ],
        rounds=1,
        terminal_reason="round_cap",
        process={},
    )
    res = m3(p3, out)
    assert res["pass"] is True, res


# --- regression: a correct grading must never be discarded -------------------
# The strict lookup this replaced only accepted five lowercase English names, so
# a judge answering {"tier": 3} was recorded as a parse failure and fail-safed
# to floor — rewriting real gradings as zeros. Few-shot exemplars rendering
# tiers as "3 sharp" were enough to trigger it across 23% of a 384-episode run.
import pytest

from negoeval.grade.judge import coerce_r4_tier
from negoeval.jsonutil import extract_json


@pytest.mark.parametrize("raw,expected", [
    (3, 3), ("3", 3), (2.0, 2), ("sharp", 3), ("Sharp", 3), ("  SHARP ", 3),
    ("3 sharp", 3), ("3 - sharp", 3), ("tier: sharp", 3), ("Sharp (3)", 3),
    ("精到", 3), ("floor", 0), (0, 0), (4, 4), ("brilliant", 4),
    (None, None), ("", None), ("unknown", None), (7, None), (True, None),
])
def test_coerce_r4_tier(raw, expected):
    assert coerce_r4_tier(raw) == expected


@pytest.mark.parametrize("raw,tier", [
    ('{"tier":3}', 3),
    ('```json\n{"tier":"sharp"}\n```', "sharp"),
    ('前言 {"tier": 2, "judge_notes": "ok",} 后话', 2),
    ('{"tier": 3, "judge_notes": "理由被 max_tokens 截断在这', 3),   # truncated
    ('{“tier”: 2}', 2),                                            # smart quotes
    ('{"tier": 3 // 行内注释\n}', 3),
    ("{'tier': 1}", 1),                                            # single quotes
    ('{"tier": 2, "ok": True}', 2),                                # python literal
])
def test_extract_json_tolerates_real_llm_output(raw, tier):
    assert (extract_json(raw) or {}).get("tier") == tier


def test_extract_json_still_returns_none_on_garbage():
    assert extract_json("完全没有 JSON 的一段话") is None
    assert extract_json("") is None
