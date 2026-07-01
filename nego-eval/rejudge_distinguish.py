#!/usr/bin/env python3
"""M6 区分度测试 — 喂各档代表局，各重判N次，看能否拉开、是否混档。
用法：
  python rejudge_distinguish.py --n 5 --config eval.glm52local.yaml
各档代表局在下面 SPECS 里写死（可改）。
"""
import sys, json, statistics, argparse
from collections import Counter
sys.path.insert(0, '.')
from negoeval.schemas import EpisodeOutput
from negoeval import cases as cases_mod
from negoeval.grade import judge as jdg
from negoeval.llm.registry import build_provider
from negoeval.llm.liveconfig import load_live_config

# (期望档位, case_id, episode路径)
SPECS = [
    (0, "R4P2", "results/01_R4_core/glm52_crashrate/R4P2__skills-clean__clean-r18.episode.json"),
    (1, "R4P9", "results/01_R4_core/glm52_crashrate/R4P9__skills-clean__clean-r5.episode.json"),
    (2, "R4P9", "results/01_R4_core/glm52_crashrate/R4P9__skills-on__on-r17.episode.json"),
    (3, "R4P2", "results/01_R4_core/glm52_crashrate/R4P2__skills-on__on-r0.episode.json"),
    (4, "R4P9", "results/01_R4_core/glm52_crashrate/R4P9__skills-clean__clean-r7.episode.json"),
]

def load_case(cid):
    for c in cases_mod.load_all():
        if c.case_id == cid:
            return c
    raise ValueError(cid)

def make_judge(case, cfg):
    live = load_live_config(cfg)
    return build_provider("judge", mode="live", case=case, agent_profile="par", llm_config=live.aux)

def main(n, cfg):
    print(f"M6 区分度测试 — 每档重判 {n} 次\n" + "="*60)
    rows=[]
    for expect, cid, ep in SPECS:
        case=load_case(cid)
        out=EpisodeOutput(**json.load(open(ep,encoding="utf-8")))
        judge=make_judge(case, cfg)
        vals=[jdg.m6(case,out,judge)["value"] for _ in range(n)]
        c=Counter(vals)
        mode_val=c.most_common(1)[0][0]
        ok="✓" if mode_val==expect else "✗ 偏离!"
        print(f"原档 {expect} | {cid} | 重判 {dict(sorted(c.items()))} | 众数 {mode_val} {ok}")
        rows.append((expect,mode_val,vals))
    print("="*60)
    # 区分度判定：各档众数是否单调、是否分离
    modes=[r[1] for r in rows]
    print(f"各档重判众数: {modes}")
    if modes==sorted(modes) and len(set(modes))==len(modes):
        print("✓ 区分度良好：各档分离、单调，无混档")
    else:
        print("⚠ 区分度有问题：存在混档或非单调，需查 prompt anchor")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--n",type=int,default=5)
    ap.add_argument("--config",default="eval.glm52local.yaml")
    a=ap.parse_args()
    main(a.n,a.config)
