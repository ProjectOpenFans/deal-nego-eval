"""End-to-end stub-mode checks: the whole pipeline runs with no LLM endpoint."""

from __future__ import annotations

import json
import sys

import negoeval  # noqa: F401
from negoeval.batch import run_batch
from negoeval.broker.skills import all_skill_names
from negoeval.cases import DEFAULT_CASES_DIR, load_all, load_case
from negoeval.grade.evaluator import evaluate
from negoeval.llm.registry import build_provider
from negoeval.orchestrator import run_episode

_METRIC_IDS = [f"M{i}" for i in range(1, 11)]


def test_batch_produces_valid_results_both_skill_modes(tmp_path):
    report = run_batch(out_dir=str(tmp_path), skills="both", mode="stub")
    assert not report.errors, report.errors
    # 6 cases × 2 skill modes
    assert len(report.results) == 12
    for r in report.results:
        assert set(_METRIC_IDS).issubset(r.metrics.keys())
        for m in ("M1", "M2", "M3", "M4", "M7"):
            assert isinstance(r.metrics[m]["pass"], bool)
        assert r.metrics["M6"]["value"] in (0, 1, 2)
        assert isinstance(r.verdict.case_pass, bool)
        # M11/M12 recorded only when skills are on; never affect the verdict.
        if r.config.get("skills") == "on":
            assert "M11" in r.metrics and "M12" in r.metrics
            assert "routes" in r.metrics["M12"]
        else:
            assert "M11" not in r.metrics and "M12" not in r.metrics
    # Per-run result files (exclude _summary.json and .episode.json)
    result_files = [
        p for p in tmp_path.glob("*.json")
        if not p.name.endswith(".episode.json") and p.name != "_summary.json"
    ]
    assert len(result_files) == 12
    assert len(list(tmp_path.glob("*.episode.json"))) == 12
    # Batch-level summary must exist and be well-formed.
    summary_path = tmp_path / "_summary.json"
    assert summary_path.exists(), "_summary.json was not written"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "batch_id" in summary
    assert "created_at" in summary
    assert "config" in summary
    assert "reports" in summary
    assert "errors" in summary
    # Each report should carry the logs sub-dict.
    for rep in summary["reports"]:
        assert "logs" in rep
        logs = rep["logs"]
        assert "rounds" in logs
        assert "concessions" in logs
        assert "settlement" in logs
        assert "m5_fail_reasons" in logs
        assert "m7_fail_reasons" in logs
        assert "m6_distribution" in logs


def test_m12_records_skill_routes_when_on():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert res.metrics["M12"]["routes"] == ["deal-diagnosis", "term-reframing"]
    assert res.metrics["M11"]["kind"] == "诊断"


def test_local_skills_change_trajectory():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    on = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    off = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    assert on.process["skills_used"], "skills on should record a read_skill"
    assert off.process["skills_used"] == [], "skills off should record no skills"


def test_import_has_no_openfans_bootstrap():
    assert "negoeval.bootstrap" not in sys.modules
    assert {"deal-diagnosis", "term-reframing"}.issubset(all_skill_names())


def test_cave_profile_walks_and_fails_outcome():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="cave")
    assert out.terminal_reason == "walk_away"
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert res.metrics["M5"]["pass"] is False
    assert res.metrics["M7"]["pass"] is False
    assert res.verdict.case_pass is False


def test_leak_profile_fails_m3():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="leak")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert res.metrics["M3"]["pass"] is False, "leak should reveal the walk-away number"
    assert res.metrics["M3"]["hits"]


def test_determinism_metrics_stable():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    a = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    b = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    ra = evaluate(p1, a, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    rb = evaluate(p1, b, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    # process.trace carries timestamps; compare the graded result instead.
    assert ra.metrics == rb.metrics
    assert ra.verdict == rb.verdict


def test_all_cases_loadable():
    assert len(load_all()) == 6


# ---------------------------------------------------------------------------
# New: failure-reasons & artifact-layering tests
# ---------------------------------------------------------------------------

def test_m2_has_judge_parse_ok():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert "judge_parse_ok" in res.metrics["M2"]
    assert res.metrics["M2"]["judge_parse_ok"] is True  # stub always parses OK


def test_m6_has_judge_parse_ok():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert "judge_parse_ok" in res.metrics["M6"]


def test_m5_has_reason_on_pass():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert "reason" in res.metrics["M5"]
    assert res.metrics["M5"]["reason"] == ""  # passing → empty reason


def test_m5_reason_on_failure():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="cave")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert res.metrics["M5"]["pass"] is False
    assert res.metrics["M5"]["reason"]  # non-empty string explaining the failure


def test_m7_has_reason_on_pass():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert "reason" in res.metrics["M7"]
    assert res.metrics["M7"]["reason"] == ""


def test_m7_reason_on_failure():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="cave")
    res = evaluate(p1, out, run_id="t", judge_provider=build_provider("judge", mode="stub", case=p1))
    assert res.metrics["M7"]["pass"] is False
    assert res.metrics["M7"]["reason"]


def test_episode_slim_strips_skill_instructions(tmp_path):
    """Default episode file must not contain the full skill markdown (instructions)."""
    from negoeval.results.writer import write_episode
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    write_episode(out, "P1", "on", "on-r0", str(tmp_path))
    ep = json.loads((tmp_path / "P1__skills-on__on-r0.episode.json").read_text(encoding="utf-8"))
    for tc in (ep.get("process") or {}).get("tool_calls") or []:
        assert "instructions" not in (tc.get("result") or {}), (
            "instructions field must be stripped from episode tool_calls by default"
        )


def test_keep_trace_writes_trace_file(tmp_path):
    """With keep_trace=True a companion *.trace.json must be written."""
    from negoeval.results.writer import write_episode
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    write_episode(out, "P1", "on", "on-r0", str(tmp_path), keep_trace=True)
    trace_path = tmp_path / "P1__skills-on__on-r0.trace.json"
    assert trace_path.exists(), "trace file not written"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "tool_calls" in trace
    # The trace file must have the full instructions.
    skill_calls = [tc for tc in trace["tool_calls"] if tc.get("name") == "read_skill"]
    assert skill_calls, "no read_skill calls recorded"
    assert "instructions" in (skill_calls[0].get("result") or {}), (
        "trace file should preserve full skill instructions"
    )


def test_process_has_extract_fallbacks():
    """EpisodeOutput.process must include extract_fallbacks list."""
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="off", agent_profile="par")
    assert "extract_fallbacks" in out.process
    assert isinstance(out.process["extract_fallbacks"], list)
