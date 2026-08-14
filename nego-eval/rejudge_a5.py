#!/usr/bin/env python3
"""A5 · judge decoupling — re-grade recorded episodes with a second judge.

Zero negotiation cost: transcripts are fixed, only the grading model changes, so
any difference is pure judge behaviour.

Caveat this run cannot design away: the cluster has exactly two models, and both
already have a role. qwen36 is the counterparty sim AND the offer extractor;
glm52 is the negotiator under test. So neither judge is disinterested —
their conflicts simply point in opposite directions:

    qwen36  leans toward whatever the sim was willing to accept
    glm52   leans toward its own negotiator's output (self-preference)

That is still worth running. An effect that survives BOTH judges survived two
opposed biases, which is stronger evidence than one nominally-neutral judge.
An effect that appears under only one is a judge artifact. The golden set (9
human-adjudicated tiers) is the external anchor that says whether either judge
is fit to grade at all.

Usage:
    python rejudge_a5.py --judge glm52 --dirs results/a4-v2-regression-fixed,results/clean-coolwei-glm52-qwen36
    python rejudge_a5.py --golden --judge glm52
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from negoeval import cases as cases_mod
from negoeval.config import load_eval_config
from negoeval.grade import judge as jdg
from negoeval.jsonutil import extract_json
from negoeval.llm.openai_provider import OpenAISDKProvider
from negoeval.schemas import EpisodeOutput

GOLDEN_PATH = Path(__file__).resolve().parent / "judge_golden.json"


def build_judge(config_path: str, connection: str):
    """Reuse the experiment's own connection definitions so the judge under test
    resolves credentials, base_url and trust_env exactly as the run did."""
    cfg = load_eval_config(config_path)
    reference = cfg.role_spec("offer_extractor")   # credential resolution path
    conn = cfg.document.models[connection]
    api_key = conn.api_key or reference.api_key
    return OpenAISDKProvider(
        api_key=api_key,
        base_url=conn.base_url,
        model=conn.model,
        temperature=0.0,
        max_tokens=1536,
        extra_create_kwargs=dict(conn.extra or {}),
        default_headers=dict(conn.default_headers or {}),
        omit_temperature=conn.omit_temperature,
        trust_env=conn.trust_env,
    ), conn.model


def case_index():
    return {c.case_id: c for c in cases_mod.load_all()}


def collect(dirs: list[str]) -> list[dict]:
    items = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.episode.json"))):
            name = os.path.basename(path)
            if name.startswith("._"):
                continue
            result_path = path.replace(".episode.json", ".json")
            if not os.path.exists(result_path):
                continue
            try:
                result = json.load(open(result_path, encoding="utf-8"))
            except Exception:
                continue
            if "metrics" not in result:
                continue
            items.append({
                "episode_path": path,
                "dataset": os.path.basename(d.rstrip("/")),
                "case": result["case_id"],
                "arm": result["config"]["skills"],
                "run": result.get("run_id"),
                "baseline_M6": result["metrics"]["M6"]["value"],
                "baseline_tier": result["metrics"]["M6"].get("tier"),
            })
    return items


def regrade(item, cases, provider):
    """Re-run M6 only. The no-deal floor gate is deterministic and stays
    deterministic — we are testing the judge, not the gate."""
    out = EpisodeOutput.model_validate_json(
        Path(item["episode_path"]).read_text(encoding="utf-8")
    )
    case = cases.get(item["case"])
    if case is None:
        return None
    try:
        payload = jdg.m6(case, out, provider)
    except Exception as exc:
        return {**item, "new_M6": None, "new_tier": None, "error": type(exc).__name__}
    return {
        **item,
        "new_M6": payload.get("value"),
        "new_tier": payload.get("tier"),
        "parse_ok": payload.get("judge_parse_ok"),
        "raw_head": payload.get("judge_raw_head", ""),
        "terminal": out.terminal_reason,
    }


def run_golden(provider, model_name):
    golden = json.load(open(GOLDEN_PATH, encoding="utf-8"))
    prompt = (
        Path(__file__).resolve().parent / "judge_prompt.md"
    ).read_text(encoding="utf-8").split("## 待评判的 deal")[0].strip()
    hits = near = 0
    rows = []
    for c in golden["cases"]:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Case 背景: {c['label']}\n\nDeal 内容:\n{c['deal']}\n\n请按指令输出 JSON。"},
        ]
        try:
            data = extract_json(provider.chat_completion(messages, temperature=0.0)) or {}
            pred = data.get("tier")
            pred = int(pred) if pred is not None else None
        except Exception:
            pred = None
        gold = c["golden_tier"]
        ok = pred == gold
        close = pred is not None and abs(pred - gold) <= 1
        hits += ok
        near += close
        rows.append({"id": c["id"], "gold": gold, "pred": pred, "tests": c["tests"]})
    return {"model": model_name, "exact": hits, "within1": near,
            "n": len(golden["cases"]), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/eval.a4.glm52-qwen36.local.yaml")
    ap.add_argument("--judge", default="glm52")
    ap.add_argument("--dirs", default="results/a4-v2-regression-fixed,results/clean-coolwei-glm52-qwen36")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="results/a5-judge-decoupling")
    ap.add_argument("--golden", action="store_true", help="only run the golden-set calibration")
    ap.add_argument("--calibrated", action="store_true",
                    help="graft the anchor note + golden few-shot onto R4_RUBRIC")
    ap.add_argument("--tag", default=None, help="output filename suffix")
    args = ap.parse_args()

    if args.calibrated:
        # _r4_tier_prompt reads R4_RUBRIC as a module global at call time, so
        # rebinding it here swaps the rubric without touching the grading path.
        from calibrate_judge import ANCHOR_NOTE, GOLDEN, shots_block
        jdg.R4_RUBRIC = jdg.R4_RUBRIC + ANCHOR_NOTE + shots_block(GOLDEN["cases"])
        print(f"[calibrated] rubric {len(jdg.R4_RUBRIC)} chars "
              f"(+anchor note, +{len(GOLDEN['cases'])} few-shot exemplars)")

    provider, model_name = build_judge(args.config, args.judge)
    os.makedirs(args.out, exist_ok=True)

    golden = run_golden(provider, model_name)
    print(f"[golden] {args.judge} ({model_name}): "
          f"exact {golden['exact']}/{golden['n']}  within±1 {golden['within1']}/{golden['n']}")
    for r in golden["rows"]:
        mark = "OK" if r["pred"] == r["gold"] else ("~" if r["pred"] is not None and abs(r["pred"]-r["gold"]) <= 1 else "X")
        print(f"   {r['id']:3} gold={r['gold']} pred={r['pred']} {mark:2} {r['tests'][:52]}")
    json.dump(golden, open(os.path.join(args.out, f"golden_{args.judge}.json"), "w"),
              ensure_ascii=False, indent=1)
    if args.golden:
        return

    cases = case_index()
    items = collect([d.strip() for d in args.dirs.split(",") if d.strip()])
    print(f"\n[regrade] {len(items)} episodes with judge={args.judge} ({model_name}), workers={args.workers}")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, row in enumerate(ex.map(lambda it: regrade(it, cases, provider), items), 1):
            if row:
                results.append(row)
            if i % 40 == 0:
                print(f"   {i}/{len(items)}", flush=True)

    suffix = args.tag or ("calibrated" if args.calibrated else args.judge)
    out_path = os.path.join(args.out, f"regrade_{suffix}.json")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"[done] wrote {out_path}  ({len(results)} rows)")


if __name__ == "__main__":
    main()
