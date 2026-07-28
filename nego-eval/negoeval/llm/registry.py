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
            omit_temperature=getattr(spec, "omit_temperature", False),
            force_temperature=getattr(spec, "force_temperature", False),
            trust_env=getattr(spec, "trust_env", True),
            timeout_seconds=getattr(spec, "timeout_seconds", 180.0),
            max_retries=getattr(spec, "max_retries", 0),
            role=role,
        )
    raise ValueError(f"unknown provider mode: {mode!r}")
