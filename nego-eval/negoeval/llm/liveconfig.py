"""Per-role live-model wiring for OpenAI-compatible model providers.

Agent-under-test runs on the ``agent`` provider; sim + M2/M6 judges + offer-extractor
run on the ``aux`` provider (a fixed neutral model, so opponent/grader stay constant
when you swap the agent).

Resolution: ``nego-eval/eval.config.yaml`` -> ``nego-eval/.env`` -> environment.
Keys are read from each preset's env var (or an inline ``api_key`` in the YAML).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_ROOT = Path(__file__).resolve().parents[2]  # nego-eval/
EVAL_CONFIG_PATH = _ROOT / "eval.config.yaml"
DOTENV_PATH = _ROOT / ".env"

PRESETS: Dict[str, Dict[str, Any]] = {
    "stepfun": {
        "base_url": "https://api.stepfun.com/step_plan/v1",
        "model": "step-3.7-flash",
        "key_env": ["STEP_API_KEY", "STEPFUN_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {"reasoning_effort": "low"},
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-max",
        "key_env": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {},
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.2",
        "key_env": ["ZHIPU_API_KEY", "GLM_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 4096,
        "extra": {"extra_body": {"thinking": {"type": "enabled"}}},
    },
    "glm_local": {
        "base_url": "https://ai.coolwei.com/models/glm_code/openai/v1",
        "model": "GLM-5.2-W4AFP8",
        "key_env": ["GLM_LOCAL_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 4096,
        "extra": {},
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
        "key_env": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "temperature": None,
        "max_tokens": 8192,
        "extra": {"extra_body": {"thinking": {"type": "enabled"}}},
        "omit_temperature": True,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "key_env": ["DEEPSEEK_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {"reasoning_effort": "high", "extra_body": {"thinking": {"type": "enabled"}}},
    },
    "deepseek_flash": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "key_env": ["DEEPSEEK_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {"reasoning_effort": "high", "extra_body": {"thinking": {"type": "enabled"}}},
    },
    "deepseek_pro": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "key_env": ["DEEPSEEK_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {"reasoning_effort": "high", "extra_body": {"thinking": {"type": "enabled"}}},
    },
    "glm52": {
        "base_url": "https://maas.devops.xiaohongshu.com/v1",
        "model": "glm-5.2",
        "key_env": ["MAAS_API_KEY", "KIMI_API_KEY"],
        "temperature": 0.3,
        "max_tokens": 8192,
        "extra": {},
        "default_headers": {
            "x-maas-user-email": "wangzhe101@xiaohongshu.com",
            "x-maas-app-id": "qs-api",
        },
    },
}

PROVIDER_ALIASES = {
    "deepseek_v4_flash": "deepseek_flash",
    "deepseek_v4_pro": "deepseek_pro",
}


@dataclass
class ProviderSpec:
    name: str
    base_url: str
    api_key: str
    model: str
    temperature: Optional[float] = 0.3
    max_tokens: int = 8192
    extra: Dict[str, Any] = field(default_factory=dict)
    default_headers: Dict[str, str] = field(default_factory=dict)
    omit_temperature: bool = False


@dataclass
class LiveConfig:
    agent: ProviderSpec
    aux: ProviderSpec


def _load_dotenv() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if DOTENV_PATH.exists():
        for line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _resolve_key(block: Dict[str, Any], preset: Dict[str, Any], dotenv: Dict[str, str]) -> str:
    if block.get("api_key"):
        return str(block["api_key"])
    for name in preset["key_env"]:
        val = os.environ.get(name) or dotenv.get(name)
        if val:
            return val
    return ""


def _spec(block: Dict[str, Any], dotenv: Dict[str, str]) -> ProviderSpec:
    provider = str(block.get("provider") or "stepfun").lower().replace("-", "_")
    provider = PROVIDER_ALIASES.get(provider, provider)
    preset = PRESETS.get(provider)
    if preset is None:
        raise ValueError(f"unknown provider {provider!r}; choose from {list(PRESETS)}")
    extra = copy.deepcopy(preset["extra"])
    if provider == "glm" and "thinking" in block:
        extra.setdefault("extra_body", {})["thinking"] = {
            "type": "enabled" if block["thinking"] else "disabled"
        }
    if provider == "kimi" and "thinking" in block:
        extra.setdefault("extra_body", {})["thinking"] = {
            "type": "enabled" if block["thinking"] else "disabled"
        }
    if provider == "stepfun" and "reasoning_effort" in block:
        extra["reasoning_effort"] = block["reasoning_effort"]
    if provider.startswith("deepseek"):
        if "thinking" in block:
            extra.setdefault("extra_body", {})["thinking"] = {
                "type": "enabled" if block["thinking"] else "disabled"
            }
        if "reasoning_effort" in block:
            extra["reasoning_effort"] = block["reasoning_effort"]
    headers = dict(preset.get("default_headers", {}))
    headers.update(block.get("default_headers", {}) or {})
    return ProviderSpec(
        name=provider,
        base_url=block.get("base_url") or preset["base_url"],
        api_key=_resolve_key(block, preset, dotenv),
        model=block.get("model") or preset["model"],
        temperature=block.get("temperature", preset["temperature"]),
        max_tokens=block.get("max_tokens", preset["max_tokens"]),
        extra=extra,
        default_headers=headers,
        omit_temperature=block.get("omit_temperature", preset.get("omit_temperature", False)),
    )


def load_live_config(path: Optional[str] = None) -> LiveConfig:
    cfg_path = Path(path) if path else EVAL_CONFIG_PATH
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    dotenv = _load_dotenv()
    agent_blk = data.get("agent") or {"provider": os.environ.get("NEGOEVAL_AGENT_PROVIDER", "stepfun")}
    aux_blk = data.get("aux") or {"provider": os.environ.get("NEGOEVAL_AUX_PROVIDER", "glm")}
    return LiveConfig(agent=_spec(agent_blk, dotenv), aux=_spec(aux_blk, dotenv))
