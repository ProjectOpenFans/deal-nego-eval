"""Provider wrapper for ablation-local latency and token estimates."""

from __future__ import annotations

import time
from typing import Any, Dict, List


def _message_chars(messages) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


class InstrumentedProvider:
    """Delegates to a canonical provider without changing its behavior.

    The canonical OpenAI provider does not expose usage to callers, so A2 labels
    char/4 token counts as estimates instead of pretending they are exact.
    """

    def __init__(self, provider, *, label: str):
        self.provider = provider
        self.label = label
        self.calls: List[Dict[str, Any]] = []
        self.model = getattr(provider, "model", "")

    def _record(self, *, kind: str, messages, output: str, started: float) -> None:
        input_chars = _message_chars(messages)
        output_chars = len(output or "")
        self.calls.append(
            {
                "label": self.label,
                "kind": kind,
                "seconds": time.monotonic() - started,
                "input_chars": input_chars,
                "output_chars": output_chars,
                "estimated_input_tokens": round(input_chars / 4),
                "estimated_output_tokens": round(output_chars / 4),
            }
        )

    def chat_completion(self, messages, **kwargs):
        started = time.monotonic()
        output = self.provider.chat_completion(messages=messages, **kwargs)
        self._record(
            kind="chat_completion",
            messages=messages,
            output=str(output or ""),
            started=started,
        )
        return output

    def chat_completion_with_tools(self, messages, tools, **kwargs):
        started = time.monotonic()
        output = self.provider.chat_completion_with_tools(
            messages=messages,
            tools=tools,
            **kwargs,
        )
        content = str(getattr(output, "content", "") or "")
        self._record(
            kind="chat_completion_with_tools",
            messages=messages,
            output=content,
            started=started,
        )
        return output

    def summary(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "model": self.model,
            "calls": len(self.calls),
            "seconds": sum(float(item["seconds"]) for item in self.calls),
            "input_chars": sum(int(item["input_chars"]) for item in self.calls),
            "output_chars": sum(int(item["output_chars"]) for item in self.calls),
            "estimated_input_tokens": sum(
                int(item["estimated_input_tokens"]) for item in self.calls
            ),
            "estimated_output_tokens": sum(
                int(item["estimated_output_tokens"]) for item in self.calls
            ),
        }

