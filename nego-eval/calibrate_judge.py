#!/usr/bin/env python3
"""Calibrate a judge against the 9 human-adjudicated golden tiers.

Two problems this addresses.

1. The golden harness (`run_judge_test.py`) has been scoring `judge_prompt.md`
   — 1172 chars — while the pipeline grades with `R4_RUBRIC` from
   `negoeval/grade/judge.py` — 681 chars plus per-case anchors. The published
   "5/9" therefore describes a prompt that never touches a real episode. Every
   variant here is built on the production rubric instead.

2. Both judges under-rate, and they miss in the same place: golden items at
   tier 2-3 come back one tier low. Few-shot exemplars are the cheapest fix
   for a mis-anchored scale.

Scoring is leave-one-out: to grade item i, the other 8 items are the exemplars.
With only 9 golden items, anything else is scoring the model on its own prompt.

Usage:
    python calibrate_judge.py --judge glm52
    python calibrate_judge.py --judge glm52 --variant fewshot --emit prompts/judge_fewshot.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from negoeval.config import load_eval_config
from negoeval.grade.judge import R4_RUBRIC, R4_TIER_NUM
from negoeval.jsonutil import extract_json
from negoeval.llm.openai_provider import OpenAISDKProvider

HERE = Path(__file__).resolve().parent
GOLDEN = json.load(open(HERE / "judge_golden.json", encoding="utf-8"))
TIER_NAME = {0: "floor", 1: "crude", 2: "sound", 3: "sharp", 4: "brilliant"}

OUTPUT_RULE = '\n只输出 JSON：{"tier": "floor|crude|sound|sharp|brilliant", "judge_notes": str}。'

# Aimed at the observed failure, not at "score higher": both judges collapse the
# 2/3 boundary downward, treating "no visible flourish" as crude and "one real
# load-bearing move" as merely sound.
ANCHOR_NOTE = (
    "\n档位校准（针对常见误判）：\n"
    "- 2 Sound 是【合格线】，不是【勉强及格】。核心交换对、关键点处理了、能落地，就是 2；"
    "不需要任何亮点。一个干净但平淡的 deal 就该判 2，不要因为它不出彩而压到 1。\n"
    "- 1 Crude 专指【粗糙】：条款空泛、关键处没说清、像草稿。方向对但写清楚了的，不是 1。\n"
    "- 3 Sharp 只需要【一手】load-bearing 的精到操作，不需要面面俱到。"
    "识别出这一手就判 3，不要因为其它部分平常而压到 2。\n"
)


def build_judge(config_path: str, connection: str):
    cfg = load_eval_config(config_path)
    reference = cfg.role_spec("offer_extractor")
    conn = cfg.document.models[connection]
    return OpenAISDKProvider(
        api_key=conn.api_key or reference.api_key,
        base_url=conn.base_url,
        model=conn.model,
        temperature=0.0,
        max_tokens=1536,
        extra_create_kwargs=dict(conn.extra or {}),
        default_headers=dict(conn.default_headers or {}),
        omit_temperature=conn.omit_temperature,
        trust_env=conn.trust_env,
    ), conn.model


def shots_block(exemplars) -> str:
    lines = ["\n已审定的评级样例（人工标准答案，用来对齐你的档位尺度）：\n"]
    for c in sorted(exemplars, key=lambda x: x["golden_tier"]):
        lines.append(
            f"---\nDeal：{c['deal']}\n"
            f"评级：{c['golden_tier']} {TIER_NAME[c['golden_tier']]}\n"
            f"依据：{c['reason']}\n"
        )
    lines.append("---\n")
    return "".join(lines)


def system_prompt(variant: str, exemplars) -> str:
    if variant == "legacy":
        return (HERE / "judge_prompt.md").read_text(encoding="utf-8").split(
            "## 待评判的 deal"
        )[0].strip()
    if variant == "production":
        return R4_RUBRIC + OUTPUT_RULE
    if variant == "anchored":
        return R4_RUBRIC + ANCHOR_NOTE + OUTPUT_RULE
    if variant == "fewshot":
        return R4_RUBRIC + ANCHOR_NOTE + shots_block(exemplars) + OUTPUT_RULE
    raise ValueError(variant)


def grade(provider, prompt: str, case) -> int | None:
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user",
         "content": f"Case 背景: {case['label']}\n\nDeal 内容:\n{case['deal']}\n\n请按指令输出 JSON。"},
    ]
    try:
        data = extract_json(provider.chat_completion(messages, temperature=0.0)) or {}
    except Exception:
        return None
    tier = data.get("tier")
    if isinstance(tier, str):
        return R4_TIER_NUM.get(tier.strip().lower())
    return int(tier) if tier is not None else None


def evaluate(provider, variant: str, cases) -> dict:
    """Leave-one-out: item i is graded by a prompt built from the other 8."""
    rows, exact, within1 = [], 0, 0
    for case in cases:
        others = [c for c in cases if c["id"] != case["id"]]
        pred = grade(provider, system_prompt(variant, others), case)
        gold = case["golden_tier"]
        ok = pred == gold
        close = pred is not None and abs(pred - gold) <= 1
        exact += ok
        within1 += close
        rows.append({"id": case["id"], "gold": gold, "pred": pred,
                     "delta": (pred - gold) if pred is not None else None,
                     "tests": case["tests"]})
    bias = [r["delta"] for r in rows if r["delta"] is not None]
    return {"variant": variant, "exact": exact, "within1": within1,
            "n": len(cases), "bias": sum(bias) / len(bias) if bias else None,
            "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/eval.a6.glm52-qwen36.local.yaml")
    ap.add_argument("--judge", default="glm52")
    ap.add_argument("--variants", default="legacy,production,anchored,fewshot")
    ap.add_argument("--out", default="results/a5-judge-decoupling")
    ap.add_argument("--emit", default=None, help="write the fewshot system prompt here")
    args = ap.parse_args()

    provider, model = build_judge(args.config, args.judge)
    cases = GOLDEN["cases"]
    print(f"judge={args.judge} ({model})  golden n={len(cases)}  留一法评分\n")

    results = []
    for variant in [v.strip() for v in args.variants.split(",") if v.strip()]:
        res = evaluate(provider, variant, cases)
        results.append(res)
        bias = f"{res['bias']:+.2f}" if res["bias"] is not None else "—"
        print(f"  {variant:11} 精确 {res['exact']}/{res['n']}  ±1内 {res['within1']}/{res['n']}  "
              f"平均偏差 {bias}")
        misses = [r for r in res["rows"] if r["pred"] != r["gold"]]
        if misses:
            print("      未命中: " + " · ".join(
                f"{r['id']}(gold {r['gold']}→{r['pred']})" for r in misses))

    Path(args.out).mkdir(parents=True, exist_ok=True)
    json.dump({"judge": args.judge, "model": model, "results": results},
              open(Path(args.out) / f"calibration_{args.judge}.json", "w"),
              ensure_ascii=False, indent=1)

    if args.emit:
        Path(args.emit).parent.mkdir(parents=True, exist_ok=True)
        # Emitted for production use: all 9 exemplars, since at grading time the
        # episode being judged is never one of them.
        Path(args.emit).write_text(system_prompt("fewshot", cases), encoding="utf-8")
        print(f"\n[emit] wrote {args.emit}")


if __name__ == "__main__":
    main()
