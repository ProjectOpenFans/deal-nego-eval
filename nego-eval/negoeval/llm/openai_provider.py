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
        temperature: float = 0.2,
        max_tokens: int = 8192,
        extra_create_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers or None)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra = dict(extra_create_kwargs or {})

    def chat_completion(self, messages, temperature=None, max_tokens=None, enable_thinking=None) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=list(messages),
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.max_tokens,
            **self.extra,
        )
        return _clean(resp.choices[0].message.content)

    def chat_completion_with_tools(
        self, messages, tools, temperature=None, max_tokens=None, tool_choice=None, **kwargs
    ) -> ToolCallResult:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=list(messages),
            tools=tools,
            tool_choice=tool_choice or "auto",
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.max_tokens,
            **self.extra,
        )
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
