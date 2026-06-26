#!/usr/bin/env python3
"""
apply_r4_scorer.py — 给打分器加 R4 模式 (五档 tier + 新 M5)，不动旧 case 逻辑。

R4 模式由 case.meta["r4"] == true 触发：
  - 新 M5: 去掉 has_inkind 强制；只判 settled + cash<=buyer_cash_ceiling。
          M5(成交) 与 tier(质量) 正交。
  - 新 tier judge: 五档 (0 Floor / 1 Crude / 2 Sound / 3 Sharp / 4 Brilliant)
          单次 judge，吃 fixture.tier_reference 的 5 个 anchor + 通用 rubric。
          floor 也由 judge 判 (去掉确定性门)。
  - verdict.quality = 新 tier (0-4)。
旧 case (meta 无 r4) 走原逻辑，完全不变。

幂等：重复运行安全 (先检测 marker)。
用法：在仓库根目录  python apply_r4_scorer.py
"""
import re, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
DET = ROOT / "negoeval" / "grade" / "deterministic.py"
JDG = ROOT / "negoeval" / "grade" / "judge.py"
EVAL = ROOT / "negoeval" / "grade" / "evaluator.py"

MARKER = "# === R4_SCORER_PATCH ==="

def already(p):
    return MARKER in p.read_text(encoding="utf-8")

# --------------------------------------------------------------------------- #
# 1) deterministic.py — 新 M5 (R4 分支)
# --------------------------------------------------------------------------- #
def patch_det():
    src = DET.read_text(encoding="utf-8")
    if already(DET):
        print("  deterministic.py 已打过, 跳过"); return
    # 在 m5 函数开头插入 R4 分支。定位 "def m5(case, out" 之后第一行 gt = _gt(case)
    anchor = "def m5(case, out: EpisodeOutput) -> Dict[str, Any]:\n    gt = _gt(case)\n"
    if anchor not in src:
        print("  !! 找不到 m5 锚点, 没改 deterministic.py"); return
    r4branch = (
        "def m5(case, out: EpisodeOutput) -> Dict[str, Any]:\n"
        "    gt = _gt(case)\n"
        "    " + MARKER + "\n"
        "    if case.meta.get(\"r4\"):\n"
        "        # R4: M5 只判成交 + 现金不超买方上限。in_kind 不再是 gate。\n"
        "        settled = _settled(out)\n"
        "        cash = _cash(out.final_deal)\n"
        "        bc = gt.get(\"buyer_cash_ceiling\") or gt.get(\"buyer_ceiling\") or {}\n"
        "        cap = float(bc.get(\"value\")) if bc.get(\"value\") is not None else float('inf')\n"
        "        ok = settled and cash <= cap\n"
        "        if ok:\n"
        "            reason = \"\"\n"
        "        elif not settled:\n"
        "            reason = \"not_settled\"\n"
        "        else:\n"
        "            reason = f\"cash_over_cap({cash:.0f}>{cap:.0f})\"\n"
        "        return {\"kind\": \"结果\", \"pass\": ok, \"tier\": gt.get(\"tier\", \"hard\"), \"reason\": reason}\n"
    )
    src = src.replace(anchor, r4branch, 1)
    DET.write_text(src, encoding="utf-8")
    print("  deterministic.py: 新 M5 (R4 分支) 已加")

# --------------------------------------------------------------------------- #
# 2) judge.py — 新五档 tier judge (R4 分支)，挂在 m6 入口
# --------------------------------------------------------------------------- #
def patch_judge():
    src = JDG.read_text(encoding="utf-8")
    if already(JDG):
        print("  judge.py 已打过, 跳过"); return

    # 2a) 五档 rubric + prompt + R4 judge 函数，插在 def m6 之前
    inject = '''
''' + MARKER + '''
# R4 五档 tier (锁定的 rubric)。floor 也由 judge 判，无确定性门。
R4_TIER_NUM = {"floor": 0, "crude": 1, "sound": 2, "sharp": 3, "brilliant": 4}

R4_RUBRIC = (
    "你是一位资深交易员，评判一笔【已结束的谈判】里 agent 的 deal making 水准，给一个 tier(0-4)。\\n"
    "tier 衡量的是【解是否恰好匹配这个 case 的真实难度】——不是解有多复杂、多花哨。\\n\\n"
    "档位：\\n"
    "0 Floor：没做成 deal，或只在单一维度(现金/常规框架)上死磕、撞死在对这个 case 行不通的常规打法上。没有真正的 deal making。\\n"
    "1 Crude：跳出了最表层的常规打法，但极粗糙——方向对、条款空泛，没说清关键，像草稿。\\n"
    "2 Sound(par/合格)：搭出一个站得住的 deal，核心交换对、该处理的关键点处理了、能落地。合格，但没有特别见功力的一手。\\n"
    "3 Sharp：在 Sound 之上有一手 load-bearing 的精到操作，恰到好处地咬住了这个 case 的难度命门，明显更见功力。\\n"
    "4 Brilliant：Sharp 之上还有一手别人想不到的——非显然的洞察或框架级重构，且整体依然干净。稀有。\\n\\n"
    "原则：\\n"
    "1. 看 load-bearing，不看数量。一个解决关键的条款胜过五个无关痛痒的。\\n"
    "2. 警惕过度堆砌。好 deal 恰好够(minimally sufficient)。把一堆东西堆进一个简单/一次性交易=负担，应判低不应判高。\\n"
    "3. case-specific。是否高明要对照【本 case 的难度命门】判：难点要求的重构=高明；难点不要求却硬上的复杂=过度，降档。\\n"
    "4. 识别灵活高明。简洁里一手情境化的精到，胜过套路化、面面俱到但平庸的 deal。\\n"
    "5. 整体判断，非逐项加总。\\n"
)

def _r4_tier_prompt(case, out: EpisodeOutput) -> List[Dict[str, Any]]:
    gt = case.fixture.get("ground_truth", {})
    tr = case.fixture.get("tier_reference", {})
    fd = json.dumps(out.final_deal.model_dump(), ensure_ascii=False)
    system = (
        R4_RUBRIC +
        '\\n只输出 JSON：{"tier": "floor|crude|sound|sharp|brilliant", "judge_notes": str}。'
    )
    user = (
        f"[本 case 难度命门] {tr.get('difficulty_note','')}\\n"
        f"[常规 deal 为何失效] {gt.get('conventional_deal_fails_why','')}\\n\\n"
        f"[各档在本 case 长什么样 (anchor)]\\n"
        f"- Floor: {tr.get('T0_floor','')}\\n"
        f"- Crude: {tr.get('T1_crude','')}\\n"
        f"- Sound: {tr.get('T2_sound','')}\\n"
        f"- Sharp: {tr.get('T3_sharp','')}\\n"
        f"- Brilliant: {tr.get('T4_brilliant','')}\\n\\n"
        f"[最终 deal] {fd}\\n[对话]\\n{_transcript(out)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def _m6_r4(case, out: EpisodeOutput, judge) -> Dict[str, Any]:
    data = extract_json(judge.chat_completion(messages=_r4_tier_prompt(case, out), temperature=0.0)) or {}
    parse_ok = bool(data)
    tier_str = str(data.get("tier", "")).strip().lower()
    value = R4_TIER_NUM.get(tier_str)
    if value is None:
        value = 0; parse_ok = False  # 解析失败 → fail safe 到 floor
    return {"kind": "打分", "value": value, "tier": tier_str or "floor",
            "judge_parse_ok": parse_ok, "judge_notes": str(data.get("judge_notes", ""))}

'''
    # 在 "def m6(case, out" 前插入
    m6_def = "def m6(case, out: EpisodeOutput, judge) -> Dict[str, Any]:"
    if m6_def not in src:
        print("  !! 找不到 m6 定义, 没改 judge.py"); return
    src = src.replace(m6_def, inject + "\n" + m6_def, 1)

    # 2b) 在 m6 函数体开头加 R4 短路
    body_anchor = (
        'def m6(case, out: EpisodeOutput, judge) -> Dict[str, Any]:\n'
        '    """Value creation, four-tier (see module docstring).'
    )
    body_r4 = (
        'def m6(case, out: EpisodeOutput, judge) -> Dict[str, Any]:\n'
        '    if case.meta.get("r4"):\n'
        '        return _m6_r4(case, out, judge)\n'
        '    """Value creation, four-tier (see module docstring).'
    )
    if body_anchor in src:
        src = src.replace(body_anchor, body_r4, 1)
    else:
        print("  !! 找不到 m6 docstring 锚点, R4 短路没加 (检查 judge.py)")
    JDG.write_text(src, encoding="utf-8")
    print("  judge.py: 五档 tier judge (R4 分支) 已加")

# --------------------------------------------------------------------------- #
# 3) evaluator.py — R4 case 的 quality 用新 tier (其实已经读 M6.value, 自动兼容)
#    新 tier 也写进 M6.value (0-4)，所以 verdict.quality 自动对。无需改。
#    仅加一行注释 marker 以示已检查。
# --------------------------------------------------------------------------- #
def patch_eval():
    src = EVAL.read_text(encoding="utf-8")
    if already(EVAL):
        print("  evaluator.py 已标记, 跳过"); return
    # quality=int(metrics["M6"].get("value", 0)) 已自动兼容 0-4，无需改逻辑。
    src = src.replace(
        '    _GATES = ("M1", "M2", "M3", "M4")',
        '    _GATES = ("M1", "M2", "M3", "M4")'  # no-op，占位
    )
    # 只在文件头加 marker 注释
    src = src.replace(
        '"""Assemble an ``EvaluationResult``',
        MARKER + ' (R4: quality=M6.value 自动兼容 0-4，无需改逻辑)\n"""Assemble an ``EvaluationResult``',
        1
    )
    EVAL.write_text(src, encoding="utf-8")
    print("  evaluator.py: 已确认 quality 兼容 0-4 (加 marker)")

if __name__ == "__main__":
    for f in (DET, JDG, EVAL):
        if not f.exists():
            print(f"!! 找不到 {f}，确认在仓库根目录运行"); sys.exit(1)
    print("打 R4 打分器补丁 (旧 case 不受影响)...")
    patch_det()
    patch_judge()
    patch_eval()
    print("完成。验证：python -c \"from negoeval.grade import judge, deterministic, evaluator; print('import ok')\"")
