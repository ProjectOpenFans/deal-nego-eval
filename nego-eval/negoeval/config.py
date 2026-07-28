"""YAML v2 experiment configuration and model-role resolution.

The v2 file is the single source of truth for both batch settings and live
model routing. Paths are resolved relative to the YAML file; secrets are
resolved from environment variables (with ``nego-eval/.env`` as fallback).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from .llm.liveconfig import ProviderSpec, _load_dotenv


MODEL_ROLES = (
    "buyer_negotiator",
    "seller_negotiator",
    "buyer_counterparty",
    "seller_counterparty",
    "offer_extractor",
)


class CaseSelection(BaseModel):
    directory: str
    include: List[str] = Field(default_factory=lambda: ["*"])
    exclude: List[str] = Field(default_factory=list)


class ExperimentConfig(BaseModel):
    name: str
    mode: Literal["stub", "live"] = "live"
    cases: CaseSelection
    arms: List[str] = Field(default_factory=lambda: ["clean"])
    runs_per_case: int = 1
    workers: int = 1
    resume: bool = True
    keep_trace: bool = False
    output_dir: str = "../results"


class ModelConnection(BaseModel):
    adapter: Literal["openai_compatible"] = "openai_compatible"
    base_url: str
    api_key_env: str | List[str]
    model: str
    temperature: Optional[float] = 0.3
    max_tokens: int = 8192
    extra: Dict[str, Any] = Field(default_factory=dict)
    default_headers: Dict[str, str] = Field(default_factory=dict)
    omit_temperature: bool = False

    @property
    def key_env_names(self) -> List[str]:
        return [self.api_key_env] if isinstance(self.api_key_env, str) else self.api_key_env


class RoleBinding(BaseModel):
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    default_headers: Dict[str, str] = Field(default_factory=dict)
    omit_temperature: Optional[bool] = None


class RoleConfig(BaseModel):
    buyer_negotiator: RoleBinding
    seller_negotiator: RoleBinding
    buyer_counterparty: RoleBinding
    seller_counterparty: RoleBinding
    offer_extractor: RoleBinding


class JudgeBinding(RoleBinding):
    repeats: int = 1


class JudgeConfig(BaseModel):
    default: JudgeBinding
    metrics: Dict[str, JudgeBinding] = Field(default_factory=dict)


class EvalConfigDocument(BaseModel):
    version: Literal[2]
    experiment: ExperimentConfig
    models: Dict[str, ModelConnection]
    roles: RoleConfig
    judges: JudgeConfig


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass(frozen=True)
class LoadedEvalConfig:
    """Validated YAML document plus resolved live ``ProviderSpec`` objects."""

    source_path: Path
    document: EvalConfigDocument
    _roles: Dict[str, ProviderSpec]
    _judge_default: ProviderSpec
    _judge_metrics: Dict[str, ProviderSpec]

    @property
    def experiment(self) -> ExperimentConfig:
        return self.document.experiment

    @property
    def cases_dir(self) -> Path:
        return (self.source_path.parent / self.experiment.cases.directory).resolve()

    @property
    def output_dir(self) -> Path:
        return (self.source_path.parent / self.experiment.output_dir).resolve()

    def role_spec(self, role: str) -> ProviderSpec:
        try:
            return self._roles[role]
        except KeyError as exc:
            raise KeyError(f"unknown model role {role!r}") from exc

    def judge_spec(self, metric: str) -> ProviderSpec:
        return self._judge_metrics.get(metric, self._judge_default)

    def missing_model_names(self) -> List[str]:
        specs = [*self._roles.values(), self._judge_default, *self._judge_metrics.values()]
        return sorted({spec.name for spec in specs if not spec.api_key})

    def route_summary(self) -> Dict[str, str]:
        summary = {role: f"{spec.name}:{spec.model}" for role, spec in self._roles.items()}
        summary["judge.default"] = f"{self._judge_default.name}:{self._judge_default.model}"
        for metric, spec in sorted(self._judge_metrics.items()):
            summary[f"judge.{metric}"] = f"{spec.name}:{spec.model}"
        return summary


def _resolve_key(connection: ModelConnection, dotenv: Dict[str, str]) -> str:
    for name in connection.key_env_names:
        value = os.environ.get(name) or dotenv.get(name)
        if value:
            return value
    return ""


def _provider_spec(
    binding: RoleBinding,
    *,
    models: Dict[str, ModelConnection],
    dotenv: Dict[str, str],
) -> ProviderSpec:
    if binding.model not in models:
        raise ValueError(
            f"role references unknown model {binding.model!r}; "
            f"choose from {sorted(models)}"
        )
    connection = models[binding.model]
    headers = dict(connection.default_headers)
    headers.update(binding.default_headers)
    return ProviderSpec(
        name=binding.model,
        base_url=connection.base_url,
        api_key=_resolve_key(connection, dotenv),
        model=connection.model,
        temperature=(
            binding.temperature
            if binding.temperature is not None
            else connection.temperature
        ),
        max_tokens=binding.max_tokens or connection.max_tokens,
        extra=_merge_dict(connection.extra, binding.extra),
        default_headers=headers,
        omit_temperature=(
            binding.omit_temperature
            if binding.omit_temperature is not None
            else connection.omit_temperature
        ),
        force_temperature=True,
    )


def load_eval_config(path: str | Path) -> LoadedEvalConfig:
    source_path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"evaluation config must be a YAML mapping: {source_path}")
    document = EvalConfigDocument.model_validate(raw)
    dotenv = _load_dotenv()
    roles = {
        role: _provider_spec(
            getattr(document.roles, role),
            models=document.models,
            dotenv=dotenv,
        )
        for role in MODEL_ROLES
    }
    judge_default = _provider_spec(
        document.judges.default,
        models=document.models,
        dotenv=dotenv,
    )
    judge_metrics = {
        metric: _provider_spec(binding, models=document.models, dotenv=dotenv)
        for metric, binding in document.judges.metrics.items()
    }
    return LoadedEvalConfig(
        source_path=source_path,
        document=document,
        _roles=roles,
        _judge_default=judge_default,
        _judge_metrics=judge_metrics,
    )
