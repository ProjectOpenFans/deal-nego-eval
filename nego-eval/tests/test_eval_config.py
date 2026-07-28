from __future__ import annotations

from pathlib import Path

import yaml

from negoeval.cases import LEGACY_CASES_DIR, load_case
from negoeval.cli import main
from negoeval.config import load_eval_config
from negoeval.grade.evaluator import _judge_for
from negoeval.orchestrator import _live_role_specs


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CONFIG = ROOT / "configs" / "eval.clean.glm52-qwen36.yaml"


def test_canonical_v2_config_resolves_paths_and_models():
    config = load_eval_config(CANONICAL_CONFIG)

    assert config.cases_dir == ROOT.parent / "cases"
    assert config.output_dir == ROOT / "results" / "clean-glm52-qwen36"
    assert config.role_spec("buyer_negotiator").model == "glm-5.2"
    assert config.role_spec("seller_negotiator").model == "glm-5.2"
    assert config.role_spec("buyer_counterparty").model == "qwen3.6"
    assert config.role_spec("seller_counterparty").model == "qwen3.6"
    assert config.role_spec("offer_extractor").model == "qwen3.6"
    assert config.judge_spec("M2").model == "qwen3.6"
    assert config.judge_spec("unknown").model == "qwen3.6"
    assert config.role_spec("buyer_negotiator").force_temperature is True


def test_buyer_seller_and_metric_judge_bindings_are_independent(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["roles"]["buyer_negotiator"]["model"] = "qwen36"
    raw["roles"]["seller_negotiator"]["model"] = "glm52"
    raw["judges"]["metrics"]["M2"]["model"] = "glm52"
    config_path = tmp_path / "role-routing.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    config = load_eval_config(config_path)

    assert config.role_spec("buyer_negotiator").model == "qwen3.6"
    assert config.role_spec("seller_negotiator").model == "glm-5.2"
    assert config.judge_spec("M2").model == "glm-5.2"
    assert config.judge_spec("M6").model == "qwen3.6"


def test_orchestrator_selects_models_by_case_side():
    class RoleNames:
        @staticmethod
        def role_spec(role):
            return role

    sell_case = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    buy_case = load_case(LEGACY_CASES_DIR / "P3.jsonc")

    assert _live_role_specs(sell_case, RoleNames()) == (
        "seller_negotiator",
        "buyer_counterparty",
        "offer_extractor",
    )
    assert _live_role_specs(buy_case, RoleNames()) == (
        "buyer_negotiator",
        "seller_counterparty",
        "offer_extractor",
    )


def test_evaluator_selects_metric_specific_judge_with_default_fallback():
    judges = {"default": object(), "M6": object()}

    assert _judge_for(judges, "M6") is judges["M6"]
    assert _judge_for(judges, "M2") is judges["default"]


def test_cli_runs_directly_from_v2_yaml_in_stub_mode(tmp_path):
    out_dir = tmp_path / "out"
    config_path = tmp_path / "eval.yaml"
    model = {
        "adapter": "openai_compatible",
        "base_url": "https://example.invalid/v1",
        "api_key_env": "NOT_NEEDED_IN_STUB_MODE",
        "model": "stub-model",
    }
    role = {"model": "stub"}
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "experiment": {
                    "name": "stub-yaml-smoke",
                    "mode": "stub",
                    "cases": {
                        "directory": str(LEGACY_CASES_DIR),
                        "include": ["P1"],
                        "exclude": [],
                    },
                    "arms": ["clean"],
                    "runs_per_case": 1,
                    "workers": 1,
                    "resume": False,
                    "keep_trace": False,
                    "output_dir": str(out_dir),
                },
                "models": {"stub": model},
                "roles": {
                    "buyer_negotiator": role,
                    "seller_negotiator": role,
                    "buyer_counterparty": role,
                    "seller_counterparty": role,
                    "offer_extractor": role,
                },
                "judges": {"default": role, "metrics": {}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert main(["--config", str(config_path)]) == 0
    assert len(list(out_dir.glob("P1__skills-clean__*.json"))) == 2
    assert len(list(out_dir.glob("_summary*.json"))) == 1
