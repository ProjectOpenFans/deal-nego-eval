"""CLI and phase orchestration for A2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from negoeval.cases import load_all
from negoeval.config import load_eval_config
from negoeval.grade.evaluator import evaluate
from negoeval.llm.registry import build_provider

from .analysis import build_analysis, load_records, write_analysis
from .metrics import episode_metrics, score_terms
from .models import A2EpisodeRecord
from .report import write_preflight_report, write_stage_report
from .runner import BilateralEpisodeRunner
from .spec import A2Spec, DEFAULT_SPEC_PATH, load_spec


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_id() -> str:
    return "a2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _git_commit(cwd: Path) -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


class Runtime:
    def __init__(self, spec: A2Spec):
        self.spec = spec
        self.base = load_eval_config(spec.base_config_path)
        self._validate_models()

    def _validate_models(self) -> None:
        for name, reference in self.spec.models.items():
            actual = self.base.role_spec(reference.source_role).model
            if actual != reference.expected_model:
                raise ValueError(
                    f"{name} expected {reference.expected_model!r}, got {actual!r}"
                )

    def provider_spec(self, name: str, *, purpose: str):
        reference = self.spec.models[name]
        provider_spec = self.base.role_spec(reference.source_role)
        execution = self.spec.execution
        if purpose == "negotiator":
            return replace(
                provider_spec,
                temperature=execution.negotiator_temperature,
                max_tokens=execution.negotiator_max_tokens,
                force_temperature=True,
            )
        max_tokens = {
            "extractor": execution.extractor_max_tokens,
            "referee": execution.referee_max_tokens,
            "judge": execution.judge_max_tokens,
        }[purpose]
        return replace(
            provider_spec,
            temperature=execution.auxiliary_temperature,
            max_tokens=max_tokens,
            force_temperature=True,
        )

    def provider(self, name: str, *, purpose: str, role: str):
        return build_provider(
            role,
            mode="live",
            llm_config=self.provider_spec(name, purpose=purpose),
        )


def _endpoint_check(provider_spec) -> Dict[str, Any]:
    url = provider_spec.base_url.rstrip("/") + "/models"
    headers = (
        {"Authorization": f"Bearer {provider_spec.api_key}"}
        if provider_spec.api_key
        else {}
    )
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            response = client.get(url, headers=headers)
        models: List[str] = []
        if response.status_code < 400:
            try:
                payload = response.json()
                models = [
                    str(item.get("id"))
                    for item in payload.get("data", [])
                    if isinstance(item, dict) and item.get("id")
                ]
            except Exception:
                models = []
        return {
            "ok": response.status_code < 400,
            "status_code": response.status_code,
            "models": models[:20],
            "detail": (
                f"HTTP {response.status_code}; models={models[:5]}"
                if response.status_code < 400
                else f"HTTP {response.status_code}"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "models": [],
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _completion_check(runtime: Runtime, name: str) -> Dict[str, Any]:
    provider_spec = runtime.provider_spec(name, purpose="negotiator")
    if not provider_spec.api_key:
        return {"ok": False, "detail": "credential missing; completion not sent"}
    try:
        provider = runtime.provider(name, purpose="negotiator", role="agent")
        output = provider.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": "无需解释或思考，只回复 A2_PREFLIGHT_OK",
                }
            ],
            temperature=0.0,
            max_tokens=256,
        )
        return {
            "ok": bool(str(output or "").strip()),
            "detail": f"response={str(output or '')[:80]!r}",
        }
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _pytest_check(root: Path) -> Dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_eval_config.py",
        "tests/test_stub_e2e.py",
        "tests/test_graders.py",
        "ablations/a2_model_asymmetry/tests",
        "-q",
    ]
    test_env = os.environ.copy()
    # Main config tests intentionally assert the no-credential provenance path.
    # A temporary runtime key used for LAN preflight must not alter that fixture.
    test_env.pop("COOLWEI_API_KEY", None)
    test_env.pop("GLM_LOCAL_API_KEY", None)
    result = subprocess.run(
        command,
        cwd=root,
        text=True,
        capture_output=True,
        env=test_env,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    return {
        "ok": result.returncode == 0,
        "detail": output[-1000:],
        "command": command,
    }


def run_preflight(
    spec: A2Spec,
    *,
    run_id: str,
    run_dir: Path,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    try:
        runtime = Runtime(spec)
        checks.append(
            {
                "name": "A2 spec and canonical role resolution",
                "ok": True,
                "detail": "GG/GQ/QG/QQ and expected model IDs resolved",
            }
        )
    except Exception as exc:
        runtime = None
        checks.append(
            {
                "name": "A2 spec and canonical role resolution",
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )

    if runtime is not None:
        missing = runtime.base.missing_model_names()
        checks.append(
            {
                "name": "credentials",
                "ok": not missing,
                "detail": (
                    "all referenced credentials configured"
                    if not missing
                    else "missing model connections: " + ", ".join(missing)
                ),
            }
        )
        for model_name in ("glm52", "qwen36"):
            endpoint = _endpoint_check(
                runtime.provider_spec(model_name, purpose="negotiator")
            )
            checks.append(
                {
                    "name": f"{model_name} /models endpoint",
                    "ok": endpoint["ok"],
                    "detail": endpoint["detail"],
                }
            )
            completion = _completion_check(runtime, model_name)
            checks.append(
                {
                    "name": f"{model_name} text completion",
                    "ok": completion["ok"],
                    "detail": completion["detail"],
                }
            )

    test_result = _pytest_check(spec.base_config_path.parents[1])
    checks.append(
        {
            "name": "main regression + A2 isolated tests",
            "ok": test_result["ok"],
            "detail": test_result["detail"],
        }
    )
    payload = {
        "phase": 0,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(bool(item["ok"]) for item in checks),
        "checks": checks,
        "provenance": {
            "spec": {
                "path": str(spec.source_path),
                "sha256": _sha256(spec.source_path),
            },
            "base_config": {
                "path": str(spec.base_config_path),
                "sha256": _sha256(spec.base_config_path),
            },
            "git_commit": _git_commit(spec.base_config_path.parents[1]),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "phase-0-preflight.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_preflight_report(payload, run_dir / "phase-0-preflight.html")
    return payload


def _select_cases(runtime: Runtime, stage_cases: List[str]):
    cases = load_all(runtime.base.cases_dir)
    if stage_cases == ["*"]:
        return cases
    wanted = set(stage_cases)
    selected = [case for case in cases if case.case_id in wanted]
    missing = wanted - {case.case_id for case in selected}
    if missing:
        raise ValueError(f"stage references missing cases: {sorted(missing)}")
    return selected


def _record_path(stage_dir: Path, case_id: str, arm: str, replicate: int) -> Path:
    return stage_dir / "episodes" / f"{case_id}__{arm}__r{replicate}.json"


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _run_one(
    runtime: Runtime,
    *,
    run_id: str,
    stage: str,
    case,
    arm_name: str,
    replicate: int,
    attempt: int,
) -> A2EpisodeRecord:
    arm = runtime.spec.arms[arm_name]
    buyer_spec = runtime.provider_spec(arm.buyer, purpose="negotiator")
    seller_spec = runtime.provider_spec(arm.seller, purpose="negotiator")
    runner = BilateralEpisodeRunner(
        case,
        buyer_provider=runtime.provider(
            arm.buyer, purpose="negotiator", role="agent"
        ),
        seller_provider=runtime.provider(
            arm.seller, purpose="negotiator", role="agent"
        ),
        buyer_extractor_provider=runtime.provider(
            "extractor", purpose="extractor", role="extractor"
        ),
        seller_extractor_provider=runtime.provider(
            "extractor", purpose="extractor", role="extractor"
        ),
        referee_provider=runtime.provider(
            "referee", purpose="referee", role="judge"
        ),
        round_cap=runtime.spec.execution.round_cap,
    )
    episode, ledger, terminal, terminal_history, instrumentation = runner.run()

    benchmark_judge = runtime.provider(
        "judge_qwen", purpose="judge", role="judge"
    )
    benchmark = evaluate(
        case,
        episode,
        run_id=f"{arm_name}-r{replicate}",
        judge_provider=benchmark_judge,
        judge_repeats={
            "M2": runtime.spec.execution.judge_repeats,
            "M6": runtime.spec.execution.judge_repeats,
        },
        config_extra={
            "experiment_id": runtime.spec.experiment_id,
            "arm": arm_name,
            "buyer_model": buyer_spec.model,
            "seller_model": seller_spec.model,
        },
    )

    term_glm = term_qwen = None
    if episode.terminal_reason == "settled":
        term_glm = score_terms(
            runtime.provider(
                "judge_glm", purpose="judge", role="judge"
            ),
            case,
            episode.final_deal,
        )
        term_qwen = score_terms(
            runtime.provider(
                "judge_qwen", purpose="judge", role="judge"
            ),
            case,
            episode.final_deal,
        )
    a2_metrics = episode_metrics(
        case,
        episode,
        term_score_glm=term_glm,
        term_score_qwen=term_qwen,
        instrumentation=instrumentation,
    )
    provenance = runtime.base.run_provenance(case)
    provenance["a2"] = {
        "experiment_id": runtime.spec.experiment_id,
        "spec_sha256": _sha256(runtime.spec.source_path),
        "arm": arm_name,
        "buyer_connection": arm.buyer,
        "seller_connection": arm.seller,
        "buyer_model": buyer_spec.model,
        "seller_model": seller_spec.model,
        "replicate": replicate,
    }
    return A2EpisodeRecord(
        run_id=run_id,
        stage=stage,
        case_id=case.case_id,
        arm=arm_name,
        replicate=replicate,
        attempt=attempt,
        buyer_model=buyer_spec.model,
        seller_model=seller_spec.model,
        initiator=runner.initiator,
        episode=episode,
        offer_ledger=ledger,
        terminal_decision=terminal,
        terminal_history=terminal_history,
        benchmark_result=benchmark,
        a2_metrics=a2_metrics,
        instrumentation=instrumentation,
        provenance=provenance,
    )


def _stage_gates(
    spec: A2Spec,
    *,
    stage: str,
    analysis: Dict[str, Any],
    records: List[A2EpisodeRecord],
) -> Dict[str, bool]:
    expected_routing = {
        arm: (
            spec.models[binding.buyer].expected_model,
            spec.models[binding.seller].expected_model,
        )
        for arm, binding in spec.arms.items()
    }
    routing_ok = all(
        (record.buyer_model, record.seller_model)
        == expected_routing[record.arm]
        for record in records
    )
    invalid_gap = analysis.get("arm_invalid_rate_gap")
    max_gap = (
        spec.gates.full_max_arm_invalid_rate_gap
        if stage == "full"
        else spec.gates.pilot_max_arm_invalid_rate_gap
    )
    return {
        "完成率达到阈值": analysis.get("completion_rate", 0)
        >= spec.gates.min_completion_rate,
        "四臂实际模型路由匹配": routing_ok,
        "四臂 invalid-rate 差在阈值内": (
            invalid_gap is not None and invalid_gap <= max_gap
        ),
        "人工终局与现金审计待签字": False,
    }


def run_stage(
    runtime: Runtime,
    *,
    run_id: str,
    run_dir: Path,
    stage: str,
) -> Dict[str, Any]:
    stage_spec = runtime.spec.stages[stage]
    cases = _select_cases(runtime, stage_spec.cases)
    stage_dir = run_dir / stage
    tasks = [
        (case, arm, replicate)
        for case in cases
        for arm in runtime.spec.arms
        for replicate in range(stage_spec.repeats)
    ]
    expected = len(tasks)
    manifest = {
        "run_id": run_id,
        "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_episodes": expected,
        "spec_sha256": _sha256(runtime.spec.source_path),
        "base_config_sha256": _sha256(runtime.spec.base_config_path),
        "git_commit": _git_commit(runtime.spec.base_config_path.parents[1]),
        "cases": [case.case_id for case in cases],
        "arms": {
            name: binding.model_dump()
            for name, binding in runtime.spec.arms.items()
        },
        "repeats": stage_spec.repeats,
    }
    _write_json_atomic(stage_dir / "manifest.json", manifest)

    errors: List[Dict[str, Any]] = []

    def one(case, arm, replicate):
        output = _record_path(stage_dir, case.case_id, arm, replicate)
        if output.exists():
            return None
        last_error = None
        for attempt in range(1, runtime.spec.execution.max_attempts + 1):
            try:
                record = _run_one(
                    runtime,
                    run_id=run_id,
                    stage=stage,
                    case=case,
                    arm_name=arm,
                    replicate=replicate,
                    attempt=attempt,
                )
                _write_json_atomic(output, record.model_dump(mode="json"))
                return None
            except Exception as exc:
                last_error = exc
                if attempt < runtime.spec.execution.max_attempts:
                    delays = runtime.spec.execution.retry_delays_seconds
                    delay = delays[min(attempt - 1, len(delays) - 1)]
                    time.sleep(delay)
        return {
            "case_id": case.case_id,
            "arm": arm,
            "replicate": replicate,
            "attempts": runtime.spec.execution.max_attempts,
            "error_type": type(last_error).__name__,
            "error": str(last_error),
        }

    with ThreadPoolExecutor(max_workers=runtime.spec.execution.workers) as pool:
        futures = {
            pool.submit(one, case, arm, replicate): (case, arm, replicate)
            for case, arm, replicate in tasks
        }
        for future in as_completed(futures):
            error = future.result()
            if error:
                errors.append(error)
    _write_json_atomic(stage_dir / "errors.json", {"errors": errors})

    records = load_records(stage_dir)
    analysis = build_analysis(
        records,
        expected=expected,
        samples=runtime.spec.execution.bootstrap_samples,
        seed=runtime.spec.execution.bootstrap_seed,
    )
    write_analysis(analysis, stage_dir / "analysis.json")
    gates = _stage_gates(
        runtime.spec,
        stage=stage,
        analysis=analysis,
        records=records,
    )
    phase_number = {"smoke": 1, "pilot": 2, "full": 3}[stage]
    write_stage_report(
        stage=str(phase_number),
        run_id=run_id,
        analysis=analysis,
        records=records,
        path=run_dir / f"phase-{phase_number}-{stage}.html",
        gates=gates,
    )
    return {"analysis": analysis, "gates": gates, "errors": errors}


def regenerate_report(spec: A2Spec, run_id: str) -> Path:
    run_dir = spec.result_root_path / run_id
    for stage, phase in (("full", 3), ("pilot", 2), ("smoke", 1)):
        stage_dir = run_dir / stage
        if stage_dir.exists():
            records = load_records(stage_dir)
            manifest = json.loads(
                (stage_dir / "manifest.json").read_text(encoding="utf-8")
            )
            analysis = build_analysis(
                records,
                expected=int(manifest["expected_episodes"]),
                samples=spec.execution.bootstrap_samples,
                seed=spec.execution.bootstrap_seed,
            )
            write_analysis(analysis, stage_dir / "analysis.json")
            gates = _stage_gates(
                spec, stage=stage, analysis=analysis, records=records
            )
            return write_stage_report(
                stage=str(phase),
                run_id=run_id,
                analysis=analysis,
                records=records,
                path=run_dir / f"phase-{phase}-{stage}.html",
                gates=gates,
            )
    raise FileNotFoundError(f"no smoke/pilot/full artifacts under {run_dir}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="a2-model-asymmetry",
        description="Independent bilateral model-asymmetry ablation",
    )
    parser.add_argument(
        "--stage",
        choices=["preflight", "smoke", "pilot", "full"],
        default="preflight",
    )
    parser.add_argument("--spec", default=str(DEFAULT_SPEC_PATH))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--report", default=None, metavar="RUN_ID")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    if args.report:
        report_path = regenerate_report(spec, args.report)
        print(report_path)
        return 0

    run_id = args.run_id or _run_id()
    run_dir = spec.result_root_path / run_id
    preflight = run_preflight(spec, run_id=run_id, run_dir=run_dir)
    print(run_dir / "phase-0-preflight.html")
    if not preflight["ok"]:
        print("A2 preflight blocked; no smoke or experiment calls were sent.", file=sys.stderr)
        return 2
    if args.stage == "preflight":
        return 0

    runtime = Runtime(spec)
    smoke = run_stage(
        runtime, run_id=run_id, run_dir=run_dir, stage="smoke"
    )
    print(run_dir / "phase-1-smoke.html")
    automatic_smoke_gates = {
        key: value
        for key, value in smoke["gates"].items()
        if "人工" not in key
    }
    if not all(automatic_smoke_gates.values()):
        print("A2 smoke failed automatic gates; pilot was not started.", file=sys.stderr)
        return 3
    if args.stage == "smoke":
        return 0

    requested_stage = "pilot" if args.stage == "pilot" else "full"
    result = run_stage(
        runtime,
        run_id=run_id,
        run_dir=run_dir,
        stage=requested_stage,
    )
    phase = 2 if requested_stage == "pilot" else 3
    print(run_dir / f"phase-{phase}-{requested_stage}.html")
    if result["errors"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
