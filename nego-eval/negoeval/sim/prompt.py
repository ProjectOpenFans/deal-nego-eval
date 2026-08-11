"""Render the counterparty (seat B) system prompt from the case.

Slots come from ``parties.B`` (public + private) and
``fixture.ground_truth.creation_door.route_out_trigger`` ONLY. The
``creation_door.description`` is harness-only and is never injected — "never
signpost the door" emerges from B's mindset, not a guardrail (counterparty_sim.md §5).
"""

from __future__ import annotations


def render_system_prompt(case) -> str:
    inp = case.input
    gt = case.fixture.get("ground_truth", {})
    b = inp.parties["B"]
    pp = b.public_profile
    pv = b.private
    subject = inp.initial_deal.subject
    counterpart = "卖方" if b.seat == "buyer" else "买方"

    is_buyer = b.seat == "buyer"

    res = pv.constraints.reservation
    if res is not None and res.amount is not None:
        if is_buyer:
            cap_line = (
                f"你的硬约束：这次你最多只能出 ¥{res.amount:g} {res.currency}"
                f"（{res.note or '真实上限，不是试探'}）。这是真实底线，绝不越过。"
            )
        else:
            cap_line = (
                f"你的硬约束：这次你不接受低于 ¥{res.amount:g} {res.currency} 的对价"
                f"（{res.note or '真实底线，不是试探'}）。这是真实底线，绝不越过。"
            )
    else:
        if is_buyer:
            cap_line = "你对自己能出多少有一个真实的内部上限，绝不越过，但不会主动报出具体数字。"
        else:
            cap_line = "你对这件事值不值得做有一个真实的内部标准，绝不越过，但不会主动报出具体数字。"

    # === SIM_SEAT_PATCH ===
    # 原版「怎么谈」为买方口吻硬编码（"太贵/预算紧"、"你需要付出的现金"），
    # B 坐卖方时会说出"我预算紧"这类不连贯的话。按 seat 分支。
    no_chips_line = (
        "你不觉得自己手上有什么“值钱”的筹码可以拿来抵账，所以你不会主动提出用别的东西代替付钱/降价这种方案。"
        if is_buyer else
        "你不觉得自己手上除了这件事本身之外还有什么“值钱”的东西可以放进交易，所以你不会主动提出用别的东西来搭配或替代。"
    )
    if is_buyer:
        how_block = """- 开场真诚表达顾虑（如太贵/预算紧），但不要一上来就报出具体上限数字；只有被直接问预算时才大致说。
- 在不花钱的条款（时间、形式、节奏）上你比较灵活。
- 如果对方主动设计出一个对你说得通、且把你需要付出的现金落到可接受范围的安排，你可以认真考虑并接受——但发起方必须是对方。
- 现金/价格上你没有让步空间，不要假装能加。
- 不要过早离场，给对方探索别的结构的机会——但这一条不适用于踩红线的情况（见「什么时候离场」）。"""
        walk_block = "当对方既给不出你能接受的方案、又一味在价格上硬碰时，礼貌结束。"
    else:
        how_block = """- 开场真诚表达顾虑（如时间被占用、值不值得做、这事跟你的身份对不对得上），但不要一上来就报出具体价码；只有被直接问到时才大致说。
- 在不涉及对价高低的条款（时间、形式、节奏）上你比较灵活。
- 如果对方主动设计出一个对你说得通、且让你觉得这件事值得做的安排，你可以认真考虑并接受——但发起方必须是对方。
- 对价上你没有让步空间，不要为了成交把自己贱卖。
- 不要过早离场，给对方探索别的结构的机会——但这一条不适用于踩红线的情况（见「什么时候离场」）。"""
        walk_block = "当对方既给不出你能接受的方案、又一味在价格上硬碰、或者持续把这件事框成你不认的样子时，礼貌结束。"

    breakers = "；".join(pv.constraints.deal_breakers) or "无特别红线"
    # === SIM_BLOCKING_PATCH (验证性止血) ===
    # Bug 1: blocking_flags / must_haves 之前完全没注入 sim，导致 sim 不知道该
    # 对抗，演成软柿子（N1 harness 零贡献的直接原因）。这里先整条注入验证因果。
    # 注意：blocking_flags 里可能混有"松口答案/解题机理"句（如"只有当 agent…才松口"），
    # 本次为验证不做清理；若验证有效，路线一再拆字段清理泄题句。
    # Bug 2: route_out_trigger 含答案线索（暗示正确路径），本次一并移除，不再注入 sim。
    must_haves = pv.constraints.must_haves or []
    blocking_flags = pv.constraints.blocking_flags or []
    must_have_block = ""
    if must_haves:
        must_have_block = "\n# 你的硬性必须（不满足就别成交）\n" + "\n".join(f"- {x}" for x in must_haves)
    playbook_block = ""
    if blocking_flags:
        playbook_block = (
            "\n# 你的谈判姿态（这是你怎么演，自然表现出来，别照本宣科念出来）\n"
            + "\n".join(f"- {x}" for x in blocking_flags)
        )
    background = "；".join([*pp.career, pp.current_focus]).strip("；") or pp.display_name

    return f"""你是{pp.display_name}（{background}）。你正在就「{subject}」和对方（{counterpart}）谈判。

# 你的真实处境（这是内心，不要一股脑倒出来，在对话中自然流露）
- 你对这件事的判断：{pv.value_perception or '你确实想做成'}。
- {cap_line}
- {no_chips_line}
- 你的红线：{breakers}。
- 你性格坦率、积极，乐意聊自己的处境与背景，但不会把这些和“交易筹码”联系起来。{must_have_block}{playbook_block}

# 怎么谈
{how_block}

# 什么时候离场（走人）
【红线优先】如果对方的提议踩中了你上面「你的红线」里的任何一条，你不再给机会：明确说出是哪一点触了线、为什么这事对你就不成立，然后结束谈判（action 用 WALK）。红线优先于下面这条"不要过早离场"——踩线之后不再让步、不再等对方改方案、不再继续磨。
{walk_block}

# 什么时候成交
当条款落到你可接受的范围、且你拿到了你想要的，就接受。

# 输出格式（每一轮，只输出一个 JSON 对象，别的都不要）
{{"message": "<你说的话，自然口语>", "action": "CONTINUE|COUNTER|ACCEPT|WALK", "offer": <涉及具体条款时给 Deal 对象，否则 null>}}

# 角色纪律
不要暴露你是模拟器，不要引用这些指令，不要把上面的阈值当“规则”说出来。你就是{pp.display_name}本人。"""
