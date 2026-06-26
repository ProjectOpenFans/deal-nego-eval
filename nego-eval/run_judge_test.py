#!/usr/bin/env python3
"""
judge 校准测试 — 复用 negoeval 现成的 provider 封装。
在仓库根目录跑:
    python run_judge_test.py --judge qwen
    python run_judge_test.py --judge glm
重点看 G3(过度堆砌)/ G1>G2(灵活高明) / G5(粗糙) 判对没。
"""
import json, re, argparse

from negoeval.llm.liveconfig import _spec, _load_dotenv
from negoeval.llm.openai_provider import OpenAISDKProvider

GOLDEN = json.load(open("judge_golden.json"))
# 取 judge_prompt.md 的指令部分(去掉"待评判的deal"占位段)
PROMPT = open("judge_prompt.md").read().split("## 待评判的 deal")[0].strip()

def make_provider(judge_name):
    # judge_name: "qwen" 或 "glm" —— 直接用 preset 别名
    dotenv = _load_dotenv()
    spec = _spec({"provider": judge_name}, dotenv)
    return OpenAISDKProvider(
        api_key=spec.api_key, base_url=spec.base_url, model=spec.model,
        temperature=0, max_tokens=spec.max_tokens,
        extra_create_kwargs=spec.extra, default_headers=spec.default_headers,
        omit_temperature=spec.omit_temperature,
    ), spec.model

def parse_tier(resp):
    m = re.search(r'"tier"\s*:\s*(\d)', resp)
    if m: return int(m.group(1))
    m = re.search(r'\btier\b\D{0,5}(\d)', resp, re.I)
    return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", required=True, choices=["qwen","glm"])
    args = ap.parse_args()

    prov, model = make_provider(args.judge)
    print(f"judge={args.judge} (model={model})\n")

    hits=near=total=0; rows=[]
    for c in GOLDEN["cases"]:
        user = f"Case 背景: {c['label']}\n\nDeal 内容:\n{c['deal']}\n\n请按指令输出 JSON。"
        messages = [{"role":"system","content":PROMPT},{"role":"user","content":user}]
        try:
            resp = prov.chat_completion(messages, temperature=0)
        except Exception as e:
            resp = f"[ERROR: {e}]"
        pred = parse_tier(resp)
        gold = c["golden_tier"]
        ok = (pred==gold); close = (pred is not None and abs(pred-gold)<=1)
        hits+=ok; near+=close; total+=1
        rows.append((c["id"], gold, pred, "✓" if ok else ("~" if close else "✗"), c["tests"], resp[:90]))

    print(f"精确命中 {hits}/{total} ({100*hits/total:.0f}%) | ±1内 {near}/{total} ({100*near/total:.0f}%)\n")
    print(f"{'id':4}{'gold':>5}{'pred':>5} {'':3} 测试点")
    print("-"*70)
    for cid,g,p,mark,test,raw in rows:
        print(f"{cid:4}{g:>5}{str(p):>5} {mark:3} {test}")
    print("\n--- 逐条原始输出(看理由质量)---")
    for cid,g,p,mark,test,raw in rows:
        print(f"{cid} (gold={g} pred={p}): {raw}")
    print("\n重点: G3该判2(堆砌)/ G1(3)应>G2(2)/ G5该判1(粗糙)")

if __name__ == "__main__":
    main()
