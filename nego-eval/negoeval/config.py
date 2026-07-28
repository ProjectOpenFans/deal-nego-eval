"""YAML v2 experiment configuration and model-role resolution.

The v2 file is the single source of truth for both batch settings and live
model routing. Paths are resolved relative to the YAML file; secrets are
resolved from environment variables (with ``nego-eval/.env`` as fallback).
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cases import load_all
from .llm.liveconfig import ProviderSpec, _load_dotenv


MODEL_ROLES = (
    "buyer_negotiator",
    "seller_negotiator",
    "buyer_counterparty",
    "seller_counterparty",
    "offer_extractor",
)
JUDGED_METRICS = ("M2", "M6", "M11", "M12")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseSelection(StrictConfigModel):
    directory: str
    include: List[str] = Field(default_factory=lambda: ["*"])
    exclude: List[str] = Field(default_factory=list)

    @field_validator("directory")
    @classmethod
    def _directory_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cases.directory must not be blank")
        return value


class ExperimentConfig(StrictConfigModel):
    name: str
    mode: Literal["stub", "live"] = "live"
    cases: CaseSelection
    arms: List[Literal["clean", "on", "off"]] = Field(
        default_factory=lambda: ["clean"], min_length=1
    )
    runs_per_case: int = Field(default=1, ge=1)
    workers: int = Field(default=1, ge=1)
    resume: bool = True
    keep_trace: bool = False
    output_dir: str = "../results"

    @field_validator("name", "output_dir")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ModelConnection(StrictConfigModel):
    adapter: Literal["openai_compatible"] = "openai_compatible"
    base_url: str
    api_key: Optional[str] = Field(default=None, repr=False)
    api_key_env: str | List[str] = Field(default_factory=list)
    model: str
    temperature: Optional[float] = 0.3
    max_tokens: int = Field(default=8192, ge=1)
    extra: Dict[str, Any] = Field(default_factory=dict)
    default_headers: Dict[str, str] = Field(default_factory=dict)
    omit_temperature: bool = False
    trust_env: bool = True
    timeout_seconds: float = Field(default=180.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=5)

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        normalized = value.rstrip("/")
        if normalized.endswith("/chat/completions"):
            raise ValueError("base_url must stop before /chat/completions")
        return normalized

    @field_validator("api_key_env")
    @classmethod
    def _valid_key_env(cls, value: str | List[str]) -> str | List[str]:
        names = [value] if isinstance(value, str) else value
        if any(not _ENV_NAME_RE.fullmatch(name) for name in names):
            raise ValueError("api_key_env must contain valid environment variable names")
        return value

    @model_validator(mode="after")
    def _credential_source_present(self) -> "ModelConnection":
        if not self.api_key and not self.key_env_names:
            raise ValueError("model connection requires api_key or api_key_env")
        return self

    @field_validator("model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be blank")
        return value

    @property
    def key_env_names(self) -> List[str]:
        return [self.api_key_env] if isinstance(self.api_key_env, str) else self.api_key_env


class RoleBinding(StrictConfigModel):
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = Field(default=None, ge=1)
    extra: Dict[str, Any] = Field(default_factory=dict)
    default_headers: Dict[str, str] = Field(default_factory=dict)
    omit_temperature: Optional[bool] = None


class RoleConfig(StrictConfigModel):
    buyer_negotiator: RoleBinding
    seller_negotiator: RoleBinding
    buyer_counterparty: RoleBinding
    seller_counterparty: RoleBinding
    offer_extractor: RoleBinding


class JudgeBinding(RoleBinding):
    repeats: int = Field(default=1, ge=1, le=10)


class JudgeConfig(StrictConfigModel):
    default: JudgeBinding
    metrics: Dict[str, JudgeBinding] = Field(default_factory=dict)

    @field_validator("metrics")
    @classmethod
    def _known_metrics_only(cls, value: Dict[str, JudgeBinding]) -> Dict[str, JudgeBinding]:
        unknown = sorted(set(value) - set(JUDGED_METRICS))
        if unknown:
            raise ValueError(f"judge overrides reference unknown metrics: {unknown}")
        return value


class EvalConfigDocument(StrictConfigModel):
    version: Literal[2]
    experiment: ExperimentConfig
    models: Dict[str, ModelConnection] = Field(min_length=1)
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
    _judge_repeats: Dict[str, int]

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

    def judge_repeats(self, metric: str) -> int:
        return self._judge_repeats.get(metric, self.document.judges.default.repeats)

    def missing_model_names(self) -> List[str]:
        specs = [*self._roles.values(), self._judge_default, *self._judge_metrics.values()]
        return sorted({spec.name for spec in specs if not spec.api_key})

    def route_summary(self) -> Dict[str, str]:
        summary = {role: f"{spec.name}:{spec.model}" for role, spec in self._roles.items()}
        summary["judge.default"] = f"{self._judge_default.name}:{self._judge_default.model}"
        for metric, spec in sorted(self._judge_metrics.items()):
            summary[f"judge.{metric}"] = f"{spec.name}:{spec.model}"
        return summary

    def run_provenance(self, case=None) -> Dict[str, Any]:
        """Return a secret-free, reproducible snapshot for each result artifact."""

        def provider(spec: ProviderSpec) -> Dict[str, Any]:
            return {
                "connection": spec.name,
                "base_url": spec.base_url,
                "model": spec.model,
                "temperature": spec.temperature,
                "max_tokens": spec.max_tokens,
                "omit_temperature": spec.omit_temperature,
                "trust_env": spec.trust_env,
                "timeout_seconds": spec.timeout_seconds,
                "max_retries": spec.max_retries,
                "extra": _redact(spec.extra),
                "credential": "configured" if spec.api_key else "missing",
            }

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "config": {
                "file": self.source_path.name,
                "sha256": hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
            },
            "experiment": self.experiment.model_dump(),
            "roles": {role: provider(spec) for role, spec in self._roles.items()},
            "judges": {
                metric: {
                    **provider(self.judge_spec(metric)),
                    "repeats": self.judge_repeats(metric),
                }
                for metric in JUDGED_METRICS
            },
        }
        if case is not None:
            payload["case"] = {
                "case_id": case.case_id,
                "file": (
                    Path(case.source_path).name
                    if getattr(case, "source_path", None)
                    else None
                ),
            }
        return payload


def _redact(value: Any) -> Any:
    """Remove likely credentials from arbitrary model extras."""
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if any(marker in key.lower() for marker in ("key", "token", "secret", "auth", "header"))
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _resolve_key(connection: ModelConnection, dotenv: Dict[str, str]) -> str:
    if connection.api_key:
        return connection.api_key
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
        trust_env=connection.trust_env,
        timeout_seconds=connection.timeout_seconds,
        max_retries=connection.max_retries,
    )


def load_eval_config(path: str | Path) -> LoadedEvalConfig:
    source_path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"evaluation config must be a YAML mapping: {source_path}")
    document = EvalConfigDocument.model_validate(raw)
    cases_dir = (source_path.parent / document.experiment.cases.directory).resolve()
    if not cases_dir.is_dir():
        raise ValueError(f"cases directory does not exist: {cases_dir}")
    case_ids = [case.case_id for case in load_all(cases_dir)]
    selected_ids = [
        case_id
        for case_id in case_ids
        if any(fnmatchcase(case_id, pattern) for pattern in document.experiment.cases.include)
        and not any(
            fnmatchcase(case_id, pattern)
            for pattern in document.experiment.cases.exclude
        )
    ]
    if not selected_ids:
        raise ValueError(
            f"case selection matched no .jsonc files in {cases_dir}: "
            f"include={document.experiment.cases.include}, "
            f"exclude={document.experiment.cases.exclude}"
        )
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
    judge_repeats = {
        metric: binding.repeats
        for metric, binding in document.judges.metrics.items()
    }
    return LoadedEvalConfig(
        source_path=source_path,
        document=document,
        _roles=roles,
        _judge_default=judge_default,
        _judge_metrics=judge_metrics,
        _judge_repeats=judge_repeats,
    )
