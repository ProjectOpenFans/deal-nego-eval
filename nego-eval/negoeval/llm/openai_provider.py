"""LLM provider using the official ``openai`` SDK.

Implements the surface used by the local broker, sim, extractor, and judge.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

from .types import ToolCallResult

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_REQUEST_LOCK = threading.Lock()
_REQUEST_SEQUENCE = 0


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
        force_temperature: bool = False,
        trust_env: bool = True,
        timeout_seconds: float = 180.0,
        max_retries: int = 0,
        role: str = "unknown",
    ):
        from openai import OpenAI
        import httpx

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers or None,
            http_client=httpx.Client(
                trust_env=trust_env,
                timeout=httpx.Timeout(timeout_seconds),
            ),
            max_retries=max_retries,
        )
        self.base_url = base_url
        self.model = model
        self.role = role
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra = dict(extra_create_kwargs or {})
        self.omit_temperature = omit_temperature
        self.force_temperature = force_temperature
        # === _ds_fix_messages ===
        self._is_deepseek = ('deepseek' in (base_url or '').lower()) or ('deepseek' in (model or '').lower())

    def _request_start(self, messages, *, tools: bool) -> tuple[int, float]:
        global _REQUEST_SEQUENCE
        with _REQUEST_LOCK:
            _REQUEST_SEQUENCE += 1
            request_id = _REQUEST_SEQUENCE
        chars = sum(len(str(message.get("content") or "")) for message in messages)
        print(
            f"[llm:start] id={request_id} role={self.role} model={self.model} "
            f"messages={len(messages)} chars={chars} tools={str(tools).lower()}",
            flush=True,
        )
        return request_id, time.monotonic()

    def _request_done(self, request_id: int, started: float, resp) -> None:
        usage = getattr(resp, "usage", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        print(
            f"[llm:done] id={request_id} role={self.role} model={self.model} "
            f"seconds={time.monotonic() - started:.2f} output_tokens={output_tokens}",
            flush=True,
        )

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
        value = self.temperature if self.force_temperature or temperature is None else temperature
        return {} if value is None else {"temperature": value}

    def chat_completion(self, messages, temperature=None, max_tokens=None, enable_thinking=None) -> str:
        messages = self._ds_fix_messages(messages)
        request_id, started = self._request_start(messages, tools=False)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=list(messages),
                max_tokens=max_tokens or self.max_tokens,
                **self._temperature_kwargs(temperature),
                **self.extra,
            )
        except Exception as exc:
            print(
                f"[llm:error] id={request_id} role={self.role} model={self.model} "
                f"seconds={time.monotonic() - started:.2f} error={type(exc).__name__}",
                flush=True,
            )
            raise
        self._request_done(request_id, started, resp)
        return _clean(resp.choices[0].message.content)

    def chat_completion_with_tools(
        self, messages, tools, temperature=None, max_tokens=None, tool_choice=None, **kwargs
    ) -> ToolCallResult:
        messages = self._ds_fix_messages(messages)
        request_id, started = self._request_start(messages, tools=True)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=list(messages),
                tools=tools,
                tool_choice=tool_choice or "auto",
                max_tokens=max_tokens or self.max_tokens,
                **self._temperature_kwargs(temperature),
                **self.extra,
            )
        except Exception as exc:
            print(
                f"[llm:error] id={request_id} role={self.role} model={self.model} "
                f"seconds={time.monotonic() - started:.2f} error={type(exc).__name__}",
                flush=True,
            )
            raise
        self._request_done(request_id, started, resp)
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
