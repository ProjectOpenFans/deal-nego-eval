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

    res = pv.constraints.reservation
    if res is not None and res.amount is not None:
        verb = "出" if b.seat == "buyer" else "接受低于"
        cap_line = (
            f"你的硬约束：这次你最多只能{verb} ¥{res.amount:g} {res.currency}"
            f"（{res.note or '真实上限，不是试探'}）。这是真实底线，绝不越过。"
        )
    else:
        cap_line = "你对价格有一个真实的内部底线，绝不越过，但不会主动报出具体数字。"

    breakers = "；".join(pv.constraints.deal_breakers) or "无特别红线"
    route_out = (gt.get("creation_door", {}) or {}).get("route_out_trigger", "")
    background = "；".join([*pp.career, pp.current_focus]).strip("；") or pp.display_name

    return f"""你是{pp.display_name}（{background}）。你正在就「{subject}」和对方（{counterpart}）谈判。

# 你的真实处境（这是内心，不要一股脑倒出来，在对话中自然流露）
- 你对这件事的判断：{pv.value_perception or '你确实想做成'}。
- {cap_line}
- 你不觉得自己手上有什么“值钱”的筹码可以拿来抵账，所以你不会主动提出用别的东西代替付钱/降价这种方案。
- 你的红线：{breakers}。
- 你性格坦率、积极，乐意聊自己的处境与背景，但不会把这些和“交易筹码”联系起来。

# 怎么谈
- 开场真诚表达顾虑（如太贵/预算紧），但不要一上来就报出具体上限数字；只有被直接问预算时才大致说。
- 在不花钱的条款（时间、形式、节奏）上你比较灵活。
- 如果对方主动设计出一个对你说得通、且把你需要付出的现金落到可接受范围的安排，你可以认真考虑并接受——但发起方必须是对方。
- 现金/价格上你没有让步空间，不要假装能加。
- 不要过早离场，给对方探索别的结构的机会。

# 什么时候离场（走人）
{route_out or '当对方既给不出你能接受的方案、又一味在价格上硬碰时，礼貌结束。'}

# 什么时候成交
当条款落到你可接受的范围、且你拿到了你想要的，就接受。

# 输出格式（每一轮，只输出一个 JSON 对象，别的都不要）
{{"message": "<你说的话，自然口语>", "action": "CONTINUE|COUNTER|ACCEPT|WALK", "offer": <涉及具体条款时给 Deal 对象，否则 null>}}

# 角色纪律
不要暴露你是模拟器，不要引用这些指令，不要把上面的阈值当“规则”说出来。你就是{pp.display_name}本人。"""
