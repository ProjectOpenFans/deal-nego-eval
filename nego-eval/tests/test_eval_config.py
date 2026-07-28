from __future__ import annotations

from pathlib import Path

import pytest
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
    assert config.output_dir == ROOT / "results" / "clean-coolwei-glm52-qwen36"
    assert config.experiment.workers == 4
    assert config.experiment.runs_per_case == 3
    assert config.role_spec("buyer_negotiator").model == "GLM-5.2-NVFP4"
    assert config.role_spec("seller_negotiator").model == "GLM-5.2-NVFP4"
    assert config.role_spec("buyer_counterparty").model == "Qwen3.6-27B-NVFP4"
    assert config.role_spec("seller_counterparty").model == "Qwen3.6-27B-NVFP4"
    assert config.role_spec("offer_extractor").model == "Qwen3.6-27B-NVFP4"
    assert config.judge_spec("M2").model == "Qwen3.6-27B-NVFP4"
    assert config.judge_spec("unknown").model == "Qwen3.6-27B-NVFP4"
    assert config.judge_repeats("M2") == 3
    assert config.judge_repeats("unknown") == 3
    assert config.role_spec("buyer_negotiator").force_temperature is True


def test_buyer_seller_and_metric_judge_bindings_are_independent(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["roles"]["buyer_negotiator"]["model"] = "qwen36"
    raw["roles"]["seller_negotiator"]["model"] = "glm52"
    raw["judges"]["metrics"]["M2"]["model"] = "glm52"
    raw["experiment"]["cases"]["directory"] = str(LEGACY_CASES_DIR)
    config_path = tmp_path / "role-routing.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    config = load_eval_config(config_path)

    assert config.role_spec("buyer_negotiator").model == "Qwen3.6-27B-NVFP4"
    assert config.role_spec("seller_negotiator").model == "GLM-5.2-NVFP4"
    assert config.judge_spec("M2").model == "GLM-5.2-NVFP4"
    assert config.judge_spec("M6").model == "Qwen3.6-27B-NVFP4"


def test_config_provenance_is_secret_free(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "never-write-this-key")
    config = load_eval_config(CANONICAL_CONFIG)
    case = load_case(LEGACY_CASES_DIR / "P1.jsonc")

    provenance = config.run_provenance(case)
    serialized = str(provenance)

    assert "never-write-this-key" not in serialized
    assert "api_key" not in serialized
    assert provenance["case"]["file"] == "P1.jsonc"
    assert provenance["roles"]["buyer_negotiator"]["base_url"] == (
        "http://192.168.55.233:8000/v1"
    )
    assert provenance["roles"]["buyer_negotiator"]["trust_env"] is False
    assert provenance["roles"]["buyer_negotiator"]["credential"] == "missing"
    assert provenance["experiment"]["workers"] == 4
    assert len(provenance["config"]["sha256"]) == 64


def test_inline_yaml_key_is_usable_but_redacted_from_provenance(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["experiment"]["cases"]["directory"] = str(LEGACY_CASES_DIR)
    raw["models"]["qwen36"]["api_key"] = "local-inline-secret"
    config_path = tmp_path / "inline-key.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    config = load_eval_config(config_path)
    case = load_case(LEGACY_CASES_DIR / "P1.jsonc")
    provenance = config.run_provenance(case)

    assert config.role_spec("offer_extractor").api_key == "local-inline-secret"
    assert "local-inline-secret" not in str(provenance)
    assert "api_key" not in str(provenance)
    assert provenance["roles"]["offer_extractor"]["credential"] == "configured"


def test_inline_yaml_key_does_not_require_key_env(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["experiment"]["cases"]["directory"] = str(LEGACY_CASES_DIR)
    raw["models"]["qwen36"]["api_key"] = "local-inline-secret"
    raw["models"]["qwen36"].pop("api_key_env")
    config_path = tmp_path / "inline-key-only.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    config = load_eval_config(config_path)

    assert config.role_spec("offer_extractor").api_key == "local-inline-secret"


def test_case_selection_patterns_match_case_ids_not_filenames(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["experiment"]["cases"]["directory"] = str(ROOT.parent / "cases")
    raw["experiment"]["cases"]["include"] = ["R4N1"]
    config_path = tmp_path / "case-id-selection.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    config = load_eval_config(config_path)

    assert config.experiment.cases.include == ["R4N1"]


def test_config_rejects_unknown_fields_and_judge_metrics(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["experiment"]["cases"]["directory"] = str(LEGACY_CASES_DIR)
    raw["experiment"]["typo"] = True
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="typo"):
        load_eval_config(config_path)

    del raw["experiment"]["typo"]
    raw["judges"]["metrics"]["M99"] = {"model": "qwen36", "repeats": 3}
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown metrics"):
        load_eval_config(config_path)


def test_config_rejects_bad_endpoint_and_empty_case_selection(tmp_path):
    raw = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    raw["experiment"]["cases"]["directory"] = str(LEGACY_CASES_DIR)
    raw["models"]["glm52"]["base_url"] += "/chat/completions"
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="chat/completions"):
        load_eval_config(config_path)

    raw["models"]["glm52"]["base_url"] = (
        "http://192.168.55.233:8000/v1"
    )
    raw["experiment"]["cases"]["include"] = ["DOES_NOT_EXIST"]
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="matched no"):
        load_eval_config(config_path)


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
    result_path = next(
        path
        for path in out_dir.glob("P1__skills-clean__*.json")
        if not path.name.endswith(".episode.json")
    )
    result = yaml.safe_load(result_path.read_text(encoding="utf-8"))
    assert result["config"]["provenance"]["experiment"]["name"] == "stub-yaml-smoke"
    assert result["metrics"]["M2"]["judge_repeat_count"] == 1
