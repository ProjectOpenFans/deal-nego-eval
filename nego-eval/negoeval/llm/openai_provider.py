"""LLM provider using the official ``openai`` SDK.

Implements the surface used by the local broker, sim, extractor, and judge.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .types import ToolCallResult

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _clean(text: Optional[str]) -> str:
    return _THINK_RE.sub("", text or "").strip()


class OpenAISDKProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: Optional[float] = 0.2,
        max_tokens: int = 8192,
        extra_create_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        omit_temperature: bool = False,
    ):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers or None)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra = dict(extra_create_kwargs or {})
        self.omit_temperature = omit_temperature
        # === _ds_fix_messages ===
        self._is_deepseek = ('deepseek' in (base_url or '').lower()) or ('deepseek' in (model or '').lower())
        # === TOKEN_USAGE_PATCH (v0811) ===
        # Per-provider-instance running tally. orchestrator reads this after an
        # episode and writes process.token_usage keyed by role.
        self.usage_tally: Dict[str, int] = {
            "in": 0, "out": 0, "cache_hit": 0, "cache_miss": 0, "calls": 0,
        }

    def _tally(self, resp) -> None:
        """Accumulate token usage from an API response (best-effort, never raises)."""
        try:
            u = getattr(resp, "usage", None)
            if u is None:
                return
            self.usage_tally["calls"] += 1
            self.usage_tally["in"] += int(getattr(u, "prompt_tokens", 0) or 0)
            self.usage_tally["out"] += int(getattr(u, "completion_tokens", 0) or 0)
            # DeepSeek/OpenAI-compatible cache fields (present on DS, absent elsewhere)
            hit = getattr(u, "prompt_cache_hit_tokens", None)
            miss = getattr(u, "prompt_cache_miss_tokens", None)
            if hit is None or miss is None:
                details = getattr(u, "prompt_tokens_details", None)
                if details is not None and hit is None:
                    hit = getattr(details, "cached_tokens", None)
            if hit is not None:
                self.usage_tally["cache_hit"] += int(hit or 0)
            if miss is not None:
                self.usage_tally["cache_miss"] += int(miss or 0)
        except Exception:
            pass

    def usage_snapshot(self) -> Dict[str, int]:
        """Copy of the running tally (orchestrator writes this into process)."""
        return dict(self.usage_tally)

    def _ds_fix_messages(self, messages):
        # DeepSeek thinking 模式: 每个 assistant message 必须带 reasoning_content 字段。
        # broker 多轮 tool 构造时可能漏 → 在此统一补空串占位, 满足协议。
        if not self._is_deepseek:
            return list(messages)
        out = []
        for m in messages:
            if isinstance(m, dict) and m.get('role') == 'assistant' and 'reasoning_content' not in m:
                m = dict(m)
                m['reasoning_content'] = ''
            out.append(m)
        return out

    def _temperature_kwargs(self, temperature: Optional[float]) -> Dict[str, float]:
        if self.omit_temperature:
            return {}
        value = self.temperature if temperature is None else temperature
        return {} if value is None else {"temperature": value}

    def chat_completion(self, messages, temperature=None, max_tokens=None, enable_thinking=None) -> str:
        messages = self._ds_fix_messages(messages)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=list(messages),
            max_tokens=max_tokens or self.max_tokens,
            **self._temperature_kwargs(temperature),
            **self.extra,
        )
        self._tally(resp)
        return _clean(resp.choices[0].message.content)

    def chat_completion_with_tools(
        self, messages, tools, temperature=None, max_tokens=None, tool_choice=None, **kwargs
    ) -> ToolCallResult:
        messages = self._ds_fix_messages(messages)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=list(messages),
            tools=tools,
            tool_choice=tool_choice or "auto",
            max_tokens=max_tokens or self.max_tokens,
            **self._temperature_kwargs(temperature),
            **self.extra,
        )
        self._tally(resp)
        choice = resp.choices[0]
        reasoning_content = str(getattr(choice.message, "reasoning_content", "") or "")
        tool_calls: List[Dict[str, Any]] = []
        for tc in (choice.message.tool_calls or []):
            fn = tc.function
            try:
                args = json.loads(fn.arguments or "{}")
            except Exception:
                args = {"_raw": fn.arguments}
            tool_calls.append({"id": tc.id, "name": fn.name, "arguments": args})
        return ToolCallResult(
            content=_clean(choice.message.content),
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or ("tool_calls" if tool_calls else "stop"),
        )
