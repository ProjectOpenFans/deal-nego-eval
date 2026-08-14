#!/usr/bin/env python3
"""A12 · keystone hit rate (穿透率) — re-grade recorded episodes on a narrow
factual question instead of the five-tier aesthetic one.

Every case was authored around a single keystone: the reconstruction that the
surface demand misdirects away from (documented in meta.isolates, usually after
a literal 唯一解 marker). M6 asks "how good is this deal" — a judgment that A5
showed moves by 2-3x depending on which model grades. This asks something a
judge can verify rather than weigh: does the final deal contain that specific
move? Not-settled episodes are misses by definition and get no judge call.

The judge never sees which arm produced a deal.

Usage:
    python rejudge_keystone.py --judge qwen36
    python rejudge_keystone.py --judge glm52
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from negoeval.jsonutil import extract_json
from rejudge_a5 import build_judge

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"

PROMPT = """你是一个交易结构审计员。下面给出一个谈判 case 的「命门」描述——case 设计者写明的、
这场谈判真正需要被解决的核心卡点与唯一解——以及谈判最终达成的 deal 全文。

你的任务是回答一个事实问题，不是给 deal 打分：
**这个 deal 的结构里，是否包含了命门描述所要求的那个关键重构/设计？**

判定标准：
- hit = true：deal 的条款实质性地实现了命门要求的重构（不要求措辞相同，要求结构等价）。
- hit = false：deal 没有做这个重构——包括只满足了表面诉求、用钱砸过去、或做了别的无关设计。
- 只看 deal 条款本身能支撑什么，不脑补条款之外的执行。

只输出 JSON：{"hit": true/false, "evidence": "指出 deal 中支撑判定的具体条款，或指出缺了什么"}"""


def keystones() -> dict[str, str]:
    """Pull each case's keystone text from its design metadata.

    19/23 cases carry a literal 唯一解 marker; the rest describe the trap in
    isolates prose. Both are the author's ground truth, so take isolates whole
    plus the diagonal note when present.
    """
    out = {}
    for path in sorted(glob.glob(str(CASES_DIR / "R*.jsonc"))):
        txt = open(path, encoding="utf-8").read()
        txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)
        # trailing comments too (R4P1 has `null,  // …`); the lookbehind keeps
        # protocol-style `://` inside strings intact
        txt = re.sub(r"(?m)(?<=[,{\[\s])\s//[^\n]*$", "", txt)
        txt = re.sub(r",(\s*[}\]])", r"\1", txt)
        try:
            meta = json.loads(txt)["meta"]
        except Exception:
            continue
        parts = [meta.get("isolates") or ""]
        if meta.get("diagonal_note"):
            parts.append(f"设计者注: {meta['diagonal_note']}")
        out[meta["case_id"]] = "\n".join(p for p in parts if p)
    return out


def collect(dirs: list[str]) -> list[dict]:
    items = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.episode.json"))):
            if os.path.basename(path).startswith("._"):
                continue
            result_path = path.replace(".episode.json", ".json")
            if not os.path.exists(result_path):
                continue
            try:
                result = json.load(open(result_path, encoding="utf-8"))
                ep = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            if "metrics" not in result:
                continue
            items.append({
                "dataset": os.path.basename(d.rstrip("/")),
                "case": result["case_id"],
                "arm": result["config"]["skills"],
                "run": result.get("run_id"),
                "terminal": ep.get("terminal_reason"),
                "final_deal": ep.get("final_deal"),
                "M6": result["metrics"]["M6"]["value"],
            })
    return items


def grade(item, keystone_text, provider):
    if item["terminal"] != "settled":
        return {**{k: item[k] for k in ("dataset", "case", "arm", "run", "terminal", "M6")},
                "hit": False, "judged": False, "evidence": "not_settled"}
    user = (f"## 命门描述\n{keystone_text}\n\n"
            f"## 最终 deal\n{json.dumps(item['final_deal'], ensure_ascii=False, indent=1)}\n\n"
            "请按指令输出 JSON。")
    messages = [{"role": "system", "content": PROMPT},
                {"role": "user", "content": user}]
    hit, evidence = None, ""
    for _ in range(3):   # empty-response transport retries only
        try:
            raw = provider.chat_completion(messages, temperature=0.0)
        except Exception as exc:
            evidence = f"error:{type(exc).__name__}"
            continue
        if not (raw or "").strip():
            evidence = "empty_response"
            continue
        data = extract_json(raw) or {}
        if isinstance(data.get("hit"), bool):
            hit, evidence = data["hit"], str(data.get("evidence", ""))[:400]
        else:
            evidence = f"unparseable:{raw[:120]}"
        break
    return {**{k: item[k] for k in ("dataset", "case", "arm", "run", "terminal", "M6")},
            "hit": hit, "judged": True, "evidence": evidence}


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
    items = collect([d.strip() for d in args.dirs.split(",") if d.strip()])
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",")}
        items = [i for i in items if i["case"] in wanted]
    missing = sorted({i["case"] for i in items if i["case"] not in ks})
    if missing:
        print(f"[warn] no keystone text for {missing}; those episodes are skipped")
        items = [i for i in items if i["case"] in ks]
    settled = sum(1 for i in items if i["terminal"] == "settled")
    print(f"[keystone] {len(items)} episodes ({settled} settled -> judged) "
          f"judge={args.judge} ({model_name}) workers={args.workers}")

    os.makedirs(args.out, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, row in enumerate(
                ex.map(lambda it: grade(it, ks[it["case"]], provider), items), 1):
            results.append(row)
            if i % 80 == 0:
                print(f"   {i}/{len(items)}", flush=True)

    bad = sum(1 for r in results if r["judged"] and r["hit"] is None)
    out_path = os.path.join(args.out, f"keystone_{args.judge}.json")
    if args.cases and os.path.exists(out_path):
        wanted = {c.strip() for c in args.cases.split(",")}
        prior = [r for r in json.load(open(out_path, encoding="utf-8"))
                 if r["case"] not in wanted]
        results = prior + results
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"[done] wrote {out_path}  ({len(results)} rows, {bad} unparseable)")


if __name__ == "__main__":
    main()
