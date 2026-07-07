"""Local single-side broker runner used as the agent-under-test."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from .prompts import broker_system_prompt
from .schemas import BrokerChatMessage, BrokerChatRequest, BrokerSide
from .skills import run_skill_tool, skill_catalog_block, skill_tools


_ROUND_LABEL_RE = None


def _strip_round_labels(text: str) -> str:
    """Strip leaked transcript labels ("[我方 · 第3轮]") from the head of a message."""
    global _ROUND_LABEL_RE
    import re as _re
    if _ROUND_LABEL_RE is None:
        _ROUND_LABEL_RE = _re.compile(r"^\s*\[(?:我方|对方)\s*·?\s*第\s*\d+\s*轮\]\s*")
    prev = None
    while prev != text:
        prev = text
        text = _ROUND_LABEL_RE.sub("", text, count=1)
    return text


def _strip_html_comments(text: str) -> str:
    import re as _re
    return _re.sub(r"<!--.*?-->\s*", "", text, flags=_re.DOTALL)


class BrokerEventEmitter:
    def __init__(self) -> None:
        self.trace: List[Dict[str, Any]] = []

    def emit(self, event_type: str, **payload: Any) -> None:
        self.trace.append({"type": event_type, **payload})


class BrokerToolExecutor:
    def __init__(self, *, allowlist: Optional[Set[str]]) -> None:
        self.allowlist = allowlist
        self.tool_calls: List[Dict[str, Any]] = []

    def run(self, name: str, arguments: dict) -> Dict[str, Any]:
        payload, ok = run_skill_tool(name, arguments or {}, self.allowlist)
        record = {"name": name, "arguments": arguments or {}, "ok": ok, "result": payload}
        self.tool_calls.append(record)
        return payload


class LocalBrokerRunner:
    def __init__(
        self,
        request: BrokerChatRequest,
        provider,
        *,
        allowlist: Optional[Set[str]],
        executor: BrokerToolExecutor,
        emitter: BrokerEventEmitter,
        skills_used: List[str],
        skills_forced: Optional[List[str]] = None,
        max_tool_rounds: int = 4,
        prompt_variant: str = "full",
    ) -> None:
        self.request = request
        self.provider = provider
        self.allowlist = allowlist
        self.executor = executor
        self.emitter = emitter
        self.skills_used = skills_used
        self.skills_forced = skills_forced if skills_forced is not None else []
        self.max_tool_rounds = max_tool_rounds
        self.prompt_variant = prompt_variant

    def run(self, *, side: BrokerSide, round_number: int, transcript_history: List[BrokerChatMessage]) -> str:
        messages = self._messages(side=side, round_number=round_number, transcript_history=transcript_history)
        if self.allowlist:
            messages = self._run_tools(messages, round_number=round_number)
        final_messages = messages + [
            {
                "role": "user",
                "content": (
                    "现在请输出你这一轮要发给对手方的自然语言消息。"
                    "只输出消息本身，不要输出 JSON，不要解释内部推理。"
                ),
            }
        ]
        text = self.provider.chat_completion(messages=final_messages, temperature=0.3)
        text = _strip_round_labels(str(text or ""))
        self.emitter.emit("round_message", side=side, round=round_number, message=text)
        return text.strip()

    def _run_tools(self, messages: List[Dict[str, Any]], *, round_number: int = 1) -> List[Dict[str, Any]]:
        tools = skill_tools()
        working = list(messages)
        # === FORCE_DIAGNOSIS_PATCH ===
        # full on: 强制先读 deal-diagnosis (中央路由), 保证 skill harness 真正介入,
        # 不依赖模型 auto 是否主动调。模型读后仍可在下面的循环里继续 route 其它 skill。
        # Round 1: force-inject the deal-diagnosis brief (INJECT.md). Forced reads are
        # tracked in skills_forced, NOT skills_used — skills_used carries only the
        # agent's voluntary route signal (consumed by M12).
        # Round 2+: inject the per-round compass (COMPASS.md) every round.
        # Injection uses a user message (local thinking endpoints hang on fabricated
        # assistant tool_call history).
        import pathlib as _pl
        _skills_dir = _pl.Path(__file__).resolve().parents[2] / "skills" / "deal-diagnosis"
        if round_number <= 1 and "deal-diagnosis" not in self.skills_forced:
            from .skills import read_skill as _read_skill
            _payload, _ok = _read_skill("deal-diagnosis", self.allowlist)
            if _ok:
                self.skills_forced.append("deal-diagnosis")
                _inject_path = _skills_dir / "INJECT.md"
                if _inject_path.exists():
                    _diag_text = _strip_html_comments(_inject_path.read_text(encoding="utf-8"))
                else:
                    _diag_text = _payload if isinstance(_payload, str) else str(_payload.get("instructions") or json.dumps(_payload, ensure_ascii=False))
                working.append({
                    "role": "user",
                    "content": "[系统已为你加载 deal-diagnosis 中央路由技能，作为每一轮的思考底座。何时跑哪一层，按框架内 When to run what 执行]\n\n" + _diag_text,
                })
                self.emitter.emit("forced_inject", name="deal-diagnosis", round=round_number)
        elif round_number >= 2:
            _compass_path = _skills_dir / "COMPASS.md"
            if _compass_path.exists():
                _compass_text = _strip_html_comments(_compass_path.read_text(encoding="utf-8"))
                working.append({
                    "role": "user",
                    "content": "[本轮罗盘——先按其分类对方上一条消息，再组织本轮谈判动作]\n\n" + _compass_text,
                })
                self.emitter.emit("compass_inject", round=round_number)
        for tool_round in range(self.max_tool_rounds):
            result = self.provider.chat_completion_with_tools(
                messages=working,
                tools=tools,
                temperature=0.2,
                tool_choice="auto",
                suppress_text_on_tool_call=True,
            )
            calls = list(getattr(result, "tool_calls", []) or [])
            if not calls:
                content = str(getattr(result, "content", "") or "").strip()
                if content:
                    working.append({"role": "assistant", "content": content})
                break
            assistant_calls = []
            for call in calls:
                args = call.get("arguments") or {}
                call_id = str(call.get("id") or f"tool_{tool_round}_{len(assistant_calls)}")
                name = str(call.get("name") or "")
                assistant_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }
                )
            assistant_message: Dict[str, Any] = {"role": "assistant", "content": "", "tool_calls": assistant_calls}
            reasoning_content = str(getattr(result, "reasoning_content", "") or "").strip()
            if reasoning_content:
                assistant_message["reasoning_content"] = reasoning_content
            working.append(assistant_message)
            for call, assistant_call in zip(calls, assistant_calls):
                name = str(call.get("name") or "")
                args = call.get("arguments") or {}
                payload = self.executor.run(name, args)
                if name == "read_skill":
                    skill_name = str((args or {}).get("name") or "").strip()
                    if "error" not in payload and skill_name and skill_name not in self.skills_used:
                        self.skills_used.append(skill_name)
                self.emitter.emit("tool_call", name=name, arguments=args, result=payload)
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": assistant_call["id"],
                        "name": name,
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                )
        return working

    def _messages(
        self, *, side: BrokerSide, round_number: int, transcript_history: List[BrokerChatMessage]
    ) -> List[Dict[str, Any]]:
        own = self.request.seller_profile if side == "seller_broker" else self.request.buyer_profile
        other = self.request.buyer_profile if side == "seller_broker" else self.request.seller_profile
        card = self.request.compose_card
        notes = "；".join(card.notes) or "无"
        system = f"""{broker_system_prompt(side, self.prompt_variant)}

## Current session context

### Mode
{self.request.mode}

### Initiator
{card.direction}

### Current contract / client mandate
- Subject: {card.headline or card.scenario}
- Scenario: {card.scenario or card.headline}
- budget_target: {card.budget_target or '未定'}
- budget_reserve_private (your eyes only): {card.budget_reserve_private or '未显式给出'}
- non_negotiables: {'；'.join(card.non_negotiables) or '无'}
- notes: {notes}

### Your client profile
{self._profile_block(own)}

### Counterparty public profile
{self._profile_block(other)}

### Available negotiation skills
{skill_catalog_block(self.allowlist)}"""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        for item in transcript_history:
            if item.role == side:
                # Own past messages: plain content. Labels on own messages teach the
                # model to emit "[我方 · 第X轮]" prefixes into the public transcript.
                messages.append({"role": "assistant", "content": item.content})
            else:
                messages.append({"role": "user", "content": f"[对方 · 第{item.round}轮]\n{item.content}"})
        messages.append({"role": "user", "content": f"现在是第 {round_number} 轮，轮到你发言。"})
        return messages

    @staticmethod
    def _profile_block(profile) -> str:
        return "\n".join(
            [
                f"- 名称：{profile.nickname or profile.id}",
                f"- 描述：{profile.description or '无'}",
                f"- 教育：{profile.schools or '无'}",
                f"- 经历：{profile.employments or '无'}",
                f"- 标签：{'；'.join(profile.skills) or '无'}",
            ]
        )
