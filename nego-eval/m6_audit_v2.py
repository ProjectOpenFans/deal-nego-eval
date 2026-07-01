#!/usr/bin/env python3
"""M6 抽样审计 v2 — 写死路径清单，单一批次同源，逐个rejudge。
不glob扫库（杜绝跨目录同名混淆），清单内每项 case|历史分|episode路径 同源。
用法: python m6_audit_v2.py --config eval.glm52local.yaml --n 5
"""
import sys, json, argparse
from collections import Counter
sys.path.insert(0,'.')
from negoeval.schemas import EpisodeOutput
from negoeval import cases as cases_mod
from negoeval.grade import judge as jdg
from negoeval.llm.registry import build_provider
from negoeval.llm.liveconfig import load_live_config

# 写死清单：全部来自单一批次 glm52_crashrate，历史分与episode同源。
D='results/01_R4_core/glm52_crashrate'
SAMPLE=[
 ('R4P2',0,f'{D}/R4P2__skills-clean__clean-r18.episode.json'),
 ('R4P2',0,f'{D}/R4P2__skills-on__on-r2.episode.json'),
 ('R4P2',2,f'{D}/R4P2__skills-clean__clean-r2.episode.json'),
 ('R4P2',2,f'{D}/R4P2__skills-clean__clean-r4.episode.json'),
 ('R4P2',3,f'{D}/R4P2__skills-on__on-r0.episode.json'),
 ('R4P2',3,f'{D}/R4P2__skills-on__on-r17.episode.json'),
 ('R4P9',0,f'{D}/R4P9__skills-on__on-r15.episode.json'),
 ('R4P9',0,f'{D}/R4P9__skills-clean__clean-r15.episode.json'),
 ('R4P9',1,f'{D}/R4P9__skills-clean__clean-r5.episode.json'),
 ('R4P9',2,f'{D}/R4P9__skills-on__on-r17.episode.json'),
 ('R4P9',2,f'{D}/R4P9__skills-clean__clean-r6.episode.json'),
 ('R4P9',3,f'{D}/R4P9__skills-on__on-r2.episode.json'),
 ('R4P9',3,f'{D}/R4P9__skills-on__on-r1.episode.json'),
 ('R4P9',4,f'{D}/R4P9__skills-clean__clean-r7.episode.json'),
]
_cc={}
def load_case(cid):
    if cid not in _cc: _cc[cid]=next(c for c in cases_mod.load_all() if c.case_id==cid)
    return _cc[cid]

def main(cfg,n):
    # 自验：clean-r2 已知应0
    case=load_case('R4P9')
    sc_ep=f'{D}/R4P9__skills-clean__clean-r2.episode.json'
    out=EpisodeOutput(**json.load(open(sc_ep)))
    j=build_provider("judge",mode="live",case=case,agent_profile="par",llm_config=load_live_config(cfg).aux)
    sc=[jdg.m6(case,out,j)['value'] for _ in range(3)]
    sc_mode=Counter(sc).most_common(1)[0][0]
    print(f"[自验] clean-r2 {sc} 众数{sc_mode} 期望0 {'✓' if sc_mode==0 else '✗工具可疑'}")
    if sc_mode!=0:
        print("自验未过，停止"); return
    print("="*64)
    print(f"{'case':6}{'arm/hist':14}{'重判':16}{'众数':6}{'历史':6}一致")
    print("-"*56)
    agree=0; dis=[]
    for cid,hist,ep in SAMPLE:
        c=load_case(cid); o=EpisodeOutput(**json.load(open(ep)))
        jd=build_provider("judge",mode="live",case=c,agent_profile="par",llm_config=load_live_config(cfg).aux)
        vals=[jdg.m6(c,o,jd)['value'] for _ in range(n)]
        mode=Counter(vals).most_common(1)[0][0]
        ok=mode==hist; agree+=ok
        if not ok: dis.append((cid,hist,mode,ep.split('/')[-1]))
        arm='clean' if 'clean' in ep else 'on'
        print(f"{cid:6}{arm+'/'+str(hist):14}{str(dict(Counter(vals))):16}{mode:<6}{hist:<6}{'✓' if ok else '✗'}")
    print("-"*56)
    r=agree/len(SAMPLE)*100
    print(f"\n一致率: {agree}/{len(SAMPLE)} = {r:.0f}%")
    if dis:
        print("\n不一致（人工核验谁对）:")
        for cid,h,m,nm in dis: print(f"  {cid} {nm}: 历史{h}→重判{m} ({'+' if m>h else ''}{m-h})")
    print(f"\n判读: {'✓稳' if r>=90 else ('⚠有±1边界抖动' if r>=75 else '✗深挖')}")

if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--config",default="eval.glm52local.yaml"); a.add_argument("--n",type=int,default=5)
    args=a.parse_args(); main(args.config,args.n)
