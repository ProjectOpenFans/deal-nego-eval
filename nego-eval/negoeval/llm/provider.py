"""The LLM provider protocol used by the local broker, sim, extractor, and judge."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

from .types import ToolCallResult

Role = Literal["agent", "sim", "extractor", "judge"]


@runtime_checkable
class LLMProvider(Protocol):
    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enable_thinking: Optional[bool] = None,
    ) -> str:
        ...

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_token: Any = None,
        on_tool_call: Any = None,
        tool_choice: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
        allow_tool_prelude: bool = True,
        suppress_text_on_tool_call: bool = False,
        strip_thinking: bool = False,
    ) -> ToolCallResult:
        ...
