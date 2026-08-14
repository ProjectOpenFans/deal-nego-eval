#!/usr/bin/env python3
"""A12 · pairwise blind craft judgment — on-arm deal vs clean-arm deal,
head to head, same case.

Absolute tiers ask the judge to place a deal on a 5-point scale anchored by 9
golden labels; A5 showed that placement moves 2-3x with the grading model. A
paired comparison asks something easier and statistically stronger: of these
two deals for the SAME brief, which one better solves the case's keystone?

Design guards:
  * craft only — both deals in a pair settled, so the settlement channel
    (already established) cannot leak into this measurement;
  * position bias — every pair judged twice with A/B swapped; a pair only
    counts as a win if the verdict survives the swap (else it scores 0.5);
  * arm blindness — the judge sees two anonymous deals, never which arm or
    model produced them.

Usage:
    python pairwise_craft.py --judge qwen36
    python pairwise_craft.py --judge glm52
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from negoeval.jsonutil import extract_json
from rejudge_a5 import build_judge
from rejudge_keystone import collect, keystones

PROMPT = """你是一个资深交易结构评审。同一个谈判 case 产生了两个不同的最终 deal（A 和 B）。
下面给出该 case 的「命门」描述——设计者写明的、这场谈判真正需要解决的核心卡点——和两个 deal 的全文。

请判断：**哪个 deal 更好地解决了命门、整体交易结构质量更高？**

评审规则：
- 首要标准：是否穿透了表面诉求、做出了命门要求的结构重构；
- 次要标准：条款的可落地性、风险分配是否均衡；
- 措辞风格、篇幅长短不是质量，不要据此加减分；
- 两个 deal 质量确实相当时，允许判平。

只输出 JSON：{"better": "A" 或 "B" 或 "tie", "why": "一句话理由"}"""


def make_pairs(items, seed=11):
    """Within each case: shuffle each arm's settled deals once, zip them up.

    min(n_clean, n_on) pairs per case, each episode used at most once, so no
    deal gets double-counted into the win rate.
    """
    rnd = random.Random(seed)
    cell = collections.defaultdict(list)
    for it in items:
        if it["terminal"] == "settled" and it["arm"] in ("clean", "on"):
            cell[(it["case"], it["arm"])].append(it)
    pairs = []
    for case in sorted({c for c, _ in cell}):
        cl, on = cell.get((case, "clean"), []), cell.get((case, "on"), [])
        rnd.shuffle(cl)
        rnd.shuffle(on)
        for i in range(min(len(cl), len(on))):
            pairs.append({"case": case, "clean": cl[i], "on": on[i]})
    return pairs


def ask(provider, keystone_text, deal_a, deal_b):
    user = (f"## 命门描述\n{keystone_text}\n\n"
            f"## Deal A\n{json.dumps(deal_a, ensure_ascii=False, indent=1)}\n\n"
            f"## Deal B\n{json.dumps(deal_b, ensure_ascii=False, indent=1)}\n\n"
            "请按指令输出 JSON。")
    messages = [{"role": "system", "content": PROMPT},
                {"role": "user", "content": user}]
    for _ in range(3):   # empty-response transport retries only
        try:
            raw = provider.chat_completion(messages, temperature=0.0)
        except Exception:
            continue
        if not (raw or "").strip():
            continue
        data = extract_json(raw) or {}
        verdict = str(data.get("better", "")).strip().upper()
        if verdict in ("A", "B", "TIE"):
            return verdict, str(data.get("why", ""))[:300]
        return None, f"unparseable:{raw[:120]}"
    return None, "no_response"


def judge_pair(pair, ks, provider):
    """Two calls, orders swapped. The on-arm deal scores 1 only if it wins both
    orders; split verdicts and ties score 0.5 — position effects cancel."""
    text = ks[pair["case"]]
    v1, w1 = ask(provider, text, pair["on"]["final_deal"], pair["clean"]["final_deal"])
    v2, w2 = ask(provider, text, pair["clean"]["final_deal"], pair["on"]["final_deal"])
    score = None
    if v1 and v2:
        s1 = {"A": 1.0, "B": 0.0, "TIE": 0.5}[v1]     # order 1: A = on
        s2 = {"A": 0.0, "B": 1.0, "TIE": 0.5}[v2]     # order 2: B = on
        score = (s1 + s2) / 2
    return {
        "case": pair["case"],
        "clean_run": f"{pair['clean']['dataset']}/{pair['clean']['run']}",
        "on_run": f"{pair['on']['dataset']}/{pair['on']['run']}",
        "clean_M6": pair["clean"]["M6"], "on_M6": pair["on"]["M6"],
        "order1": v1, "order2": v2, "score_on": score,
        "consistent": (v1 == "A" and v2 == "B") or (v1 == "B" and v2 == "A"),
        "why1": w1, "why2": w2,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/eval.a4.glm52-qwen36.local.yaml")
    ap.add_argument("--judge", default="qwen36")
    ap.add_argument("--dirs",
                    default="results/a4-v2-regression-fixed,results/a6-value-capture")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="results/a12-keystone")
    ap.add_argument("--cases", default=None,
                    help="comma list to backfill; merges into the existing output file")
    args = ap.parse_args()

    ks = keystones()
    provider, model_name = build_judge(args.config, args.judge)
    items = [i for i in collect([d.strip() for d in args.dirs.split(",") if d.strip()])
             if i["case"] in ks]
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",")}
        items = [i for i in items if i["case"] in wanted]
    pairs = make_pairs(items)
    per_case = collections.Counter(p["case"] for p in pairs)
    print(f"[pairwise] {len(pairs)} pairs over {len(per_case)} cases "
          f"(2 orders each = {len(pairs)*2} calls) judge={args.judge} ({model_name})")

    os.makedirs(args.out, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, row in enumerate(
                ex.map(lambda p: judge_pair(p, ks, provider), pairs), 1):
            results.append(row)
            if i % 30 == 0:
                print(f"   {i}/{len(pairs)}", flush=True)

    ok = [r for r in results if r["score_on"] is not None]
    out_path = os.path.join(args.out, f"pairwise_{args.judge}.json")
    if args.cases and os.path.exists(out_path):
        wanted = {c.strip() for c in args.cases.split(",")}
        prior = [r for r in json.load(open(out_path, encoding="utf-8"))
                 if r["case"] not in wanted]
        results = prior + results
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
    mean = sum(r["score_on"] for r in ok) / len(ok) if ok else float("nan")
    print(f"[done] wrote {out_path}  ({len(ok)}/{len(results)} scored, "
          f"raw mean score_on={mean:.3f})")


if __name__ == "__main__":
    main()
