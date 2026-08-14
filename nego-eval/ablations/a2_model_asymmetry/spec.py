"""Strict, executable specification for A2."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_SPEC_PATH = PACKAGE_DIR / "prd.yaml"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelRef(StrictModel):
    source_role: str
    expected_model: str


class ArmSpec(StrictModel):
    buyer: Literal["glm52", "qwen36"]
    seller: Literal["glm52", "qwen36"]


class StageSpec(StrictModel):
    cases: List[str] = Field(min_length=1)
    repeats: int = Field(ge=1)


class ExecutionSpec(StrictModel):
    prompt_variant: Literal["clean"] = "clean"
    skills: Literal[False] = False
    round_cap: int = Field(default=12, ge=1)
    workers: int = Field(default=4, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    retry_delays_seconds: List[int] = Field(default_factory=lambda: [5, 15])
    negotiator_temperature: float = 0.3
    negotiator_max_tokens: int = Field(default=2048, ge=1)
    auxiliary_temperature: float = 0.0
    referee_max_tokens: int = Field(default=512, ge=1)
    extractor_max_tokens: int = Field(default=1024, ge=1)
    judge_max_tokens: int = Field(default=1536, ge=1)
    judge_repeats: int = Field(default=3, ge=1)
    bootstrap_samples: int = Field(default=10000, ge=100)
    bootstrap_seed: int = 20260729


class GateSpec(StrictModel):
    min_completion_rate: float = Field(ge=0, le=1)
    pilot_max_arm_invalid_rate_gap: float = Field(ge=0, le=1)
    full_max_arm_invalid_rate_gap: float = Field(ge=0, le=1)
    min_terminal_cash_audit_accuracy: float = Field(ge=0, le=1)
    require_routing_match: bool = True
    forbid_selective_rerun: bool = True


class A2Spec(StrictModel):
    version: Literal[1]
    experiment_id: Literal["a2-model-asymmetry"]
    title: str
    base_config: str
    result_root: str
    models: Dict[str, ModelRef]
    arms: Dict[str, ArmSpec]
    stages: Dict[str, StageSpec]
    execution: ExecutionSpec
    gates: GateSpec
    source_path: Path = Field(exclude=True)

    @model_validator(mode="after")
    def _contract_complete(self) -> "A2Spec":
        if set(self.arms) != {"GG", "GQ", "QG", "QQ"}:
            raise ValueError("A2 requires exactly GG, GQ, QG, and QQ")
        if set(self.stages) != {"smoke", "pilot", "full"}:
            raise ValueError("A2 requires smoke, pilot, and full stages")
        required_models = {
            "glm52",
            "qwen36",
            "extractor",
            "referee",
            "judge_glm",
            "judge_qwen",
        }
        if not required_models.issubset(self.models):
            raise ValueError(f"missing model refs: {sorted(required_models - set(self.models))}")
        return self

    @property
    def base_config_path(self) -> Path:
        return (self.source_path.parent / self.base_config).resolve()

    @property
    def result_root_path(self) -> Path:
        return (self.source_path.parent / self.result_root).resolve()


def load_spec(path: str | Path = DEFAULT_SPEC_PATH) -> A2Spec:
    source = Path(path).resolve()
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["source_path"] = source
    return A2Spec.model_validate(raw)

