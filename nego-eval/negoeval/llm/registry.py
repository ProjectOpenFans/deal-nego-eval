"""Build an LLM provider for a role, in stub (offline) or live mode."""

from __future__ import annotations

from typing import Any, Optional

from .provider import Role


def build_provider(
    role: Role,
    *,
    mode: str = "stub",
    case: Any = None,
    agent_profile: str = "par",
    llm_config: Any = None,
):
    if mode == "stub":
        from .stub import StubProvider

        return StubProvider(role, case=case, agent_profile=agent_profile)
    if mode == "live":
        # llm_config is a ProviderSpec (StepFun/Qwen/GLM), built by liveconfig.
        from .openai_provider import OpenAISDKProvider

        spec = llm_config
        return OpenAISDKProvider(
            api_key=spec.api_key,
            base_url=spec.base_url,
            model=spec.model,
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            extra_create_kwargs=spec.extra,
            default_headers=getattr(spec, "default_headers", None),
        )
    raise ValueError(f"unknown provider mode: {mode!r}")
