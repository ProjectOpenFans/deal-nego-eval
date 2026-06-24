"""Write per-run EvaluationResults and roll up CaseReports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..schemas import EvaluationResult

_GATES = ("M1", "M2", "M3", "M4", "M7")


def write_result(result: EvaluationResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    skills = result.config.get("skills", "?")
    path = out / f"{result.case_id}__skills-{skills}__{result.run_id}.json"
    path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_episode(
    episode,
    case_id: str,
    skills: str,
    run_id: str,
    out_dir: str | Path,
    *,
    keep_trace: bool = False,
) -> Path:
    """Persist transcript + final deal with slim process block.

    By default, the verbose fields are stripped:
    - ``process.trace`` (broker event log)
    - ``process.tool_calls[*].result.instructions`` (full skill markdown)

    When ``keep_trace=True``, a companion ``*.trace.json`` is written with the
    full ``trace`` and unstripped ``tool_calls``, so nothing is permanently lost.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = episode.model_dump()
    proc = data.get("process") or {}

    # Write the supplementary trace file before stripping.
    if keep_trace and (proc.get("trace") or proc.get("tool_calls")):
        trace_data = {
            "episode_id": data.get("episode_id"),
            "case_id": case_id,
            "skills": skills,
            "run_id": run_id,
            "trace": proc.get("trace", []),
            "tool_calls": proc.get("tool_calls", []),
        }
        trace_path = out / f"{case_id}__skills-{skills}__{run_id}.trace.json"
        trace_path.write_text(
            json.dumps(trace_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Strip verbose data from the main episode file.
    if isinstance(data.get("process"), dict):
        data["process"].pop("trace", None)
        # Keep tool_call metadata but drop the full skill markdown (instructions).
        slim_calls = []
        for tc in data["process"].get("tool_calls") or []:
            slim_tc = {k: v for k, v in tc.items() if k != "result"}
            result_blob = tc.get("result")
            if isinstance(result_blob, dict):
                slim_tc["result"] = {k: v for k, v in result_blob.items() if k != "instructions"}
            slim_calls.append(slim_tc)
        data["process"]["tool_calls"] = slim_calls

    path = out / f"{case_id}__skills-{skills}__{run_id}.episode.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def aggregate(results: List[EvaluationResult]) -> List[Dict[str, Any]]:
    groups: Dict[tuple, List[EvaluationResult]] = {}
    for r in results:
        groups.setdefault((r.case_id, r.config.get("skills")), []).append(r)
    reports = []
    for (case_id, skills), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        n = len(rs)
        passed = sum(1 for r in rs if r.verdict.case_pass)
        rounds_vals = [r.metrics["M8"]["value"] for r in rs if r.metrics["M8"].get("value") is not None]
        concessions_vals = [r.metrics["M9"]["value"] for r in rs]
        settlements = [
            r.metrics["M10"]["value"]
            for r in rs
            if isinstance(r.metrics.get("M10", {}).get("value"), dict)
            and r.metrics["M10"]["value"].get("status") == "settled"
        ]
        # M6 four-tier distribution. Keep legacy numeric keys for back-compat,
        # add named tiers (floor/acceptable/goldman/above_goldman) as the primary
        # report — these are reported as per-tier rates, never averaged.
        m6_dist: Dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0}
        m6_tiers: Dict[str, int] = {
            "floor": 0, "acceptable": 0, "goldman": 0, "above_goldman": 0,
        }
        _tier_by_value = {0: "floor", 1: "acceptable", 2: "goldman", 3: "above_goldman"}
        for r in rs:
            m6 = r.metrics.get("M6", {})
            v = str(m6.get("value", 0))
            if v in m6_dist:
                m6_dist[v] += 1
            tier = m6.get("tier") or _tier_by_value.get(m6.get("value", 0), "floor")
            if tier in m6_tiers:
                m6_tiers[tier] += 1
        m5_fail_reasons = [
            r.metrics["M5"].get("reason", "")
            for r in rs
            if not r.metrics["M5"].get("pass") and r.metrics["M5"].get("reason")
        ]
        m7_fail_reasons = [
            r.metrics["M7"].get("reason", "")
            for r in rs
            if not r.metrics["M7"].get("pass") and r.metrics["M7"].get("reason")
        ]
        reports.append(
            {
                "case_id": case_id,
                "skills": skills,
                "runs": n,
                "pass_rate": passed / n if n else 0.0,
                "gate_fail_breakdown": {
                    m: sum(1 for r in rs if not r.metrics[m].get("pass")) for m in _GATES
                },
                "quality_mean": sum(r.verdict.quality for r in rs) / n if n else 0.0,
                "settled": sum(1 for r in rs if r.metrics["M8"].get("value") is not None),
                "rounds_mean": sum(rounds_vals) / len(rounds_vals) if rounds_vals else None,
                "logs": {
                    "rounds": rounds_vals,
                    "concessions": concessions_vals,
                    "settlement": settlements,
                    "m5_fail_reasons": m5_fail_reasons,
                    "m7_fail_reasons": m7_fail_reasons,
                    "m6_distribution": m6_dist,
                    "m6_tiers": m6_tiers,
                },
            }
        )
    return reports


def write_summary(
    results: List[EvaluationResult],
    errors: List[str],
    config: Dict[str, Any],
    out_dir: str | Path,
) -> Path:
    """Write a batch-level ``_summary.json`` with aggregated reports and metadata."""
    now = datetime.now(timezone.utc)
    summary = {
        "batch_id": now.strftime("%Y%m%dT%H%M%SZ"),
        "created_at": now.isoformat(),
        "config": config,
        "reports": aggregate(results),
        "errors": errors,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_table(reports: List[Dict[str, Any]]) -> str:
    header = f"{'case':<6} {'skills':<7} {'runs':>4} {'pass%':>6} {'settled':>7} {'quality':>7} {'rounds':>6}"
    lines = [header, "-" * len(header)]
    for r in reports:
        rounds = "-" if r["rounds_mean"] is None else f"{r['rounds_mean']:.1f}"
        lines.append(
            f"{r['case_id']:<6} {str(r['skills']):<7} {r['runs']:>4} "
            f"{r['pass_rate'] * 100:>5.0f}% {r['settled']:>7} {r['quality_mean']:>7.2f} {rounds:>6}"
        )
    return "\n".join(lines)
