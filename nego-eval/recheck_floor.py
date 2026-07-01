#!/usr/bin/env python3
"""历史 floor(0) 局重判复核 — 量化 judge 误判率。
取所有历史判0的局，重判，统计仍判0 vs 被纠正到更高档的比例。
用法：
  python recheck_floor.py --config eval.glm52local.yaml --n 1 --sample 3
  --n: 每局重判几次（取众数）；--sample: 每个case_arm抽样几局（0=全量）
"""
import sys, json, glob, os, argparse
from collections import defaultdict, Counter
sys.path.insert(0,'.')
from negoeval.schemas import EpisodeOutput
from negoeval import cases as cases_mod
from negoeval.grade import judge as jdg
from negoeval.llm.registry import build_provider
from negoeval.llm.liveconfig import load_live_config

_case_cache={}
def load_case(cid):
    if cid not in _case_cache:
        _case_cache[cid]=next(c for c in cases_mod.load_all() if c.case_id==cid)
    return _case_cache[cid]

_judge_cache={}
def make_judge(case,cfg):
    if cfg not in _judge_cache:
        live=load_live_config(cfg)
        _judge_cache[cfg]=("live",live.aux)
    mode,aux=_judge_cache[cfg]
    return build_provider("judge",mode="live",case=case,agent_profile="par",llm_config=aux)

def main(cfg,n,sample):
    # 收集历史判0的局
    floor_runs=defaultdict(list)
    for f in glob.glob('results/01_R4_core/**/*.json',recursive=True):
        bn=os.path.basename(f)
        if any(x in bn for x in ['episode','trace','summary']): continue
        try:
            d=json.load(open(f))
            if d['metrics']['M6']['value']==0:
                ep=f.replace('.json','.episode.json')
                if os.path.exists(ep):
                    case=d.get('case_id','?')
                    arm='clean' if 'clean' in bn else ('on' if '__on' in bn else 'off')
                    floor_runs[(case,arm)].append((ep,d['metrics']['M6'].get('judge_notes','')[:80]))
        except: pass

    print(f"历史 floor(0) 复核 | 每局重判{n}次 | 抽样{'全量' if sample==0 else sample}/组\n"+"="*60)
    grand_still0=0; grand_total=0; corrected=[]
    for (case,arm),runs in sorted(floor_runs.items()):
        picks=runs if sample==0 else runs[:sample]
        still0=0
        for ep,oldnote in picks:
            c=load_case(case); out=EpisodeOutput(**json.load(open(ep,encoding='utf-8')))
            judge=make_judge(c,cfg)
            vals=[jdg.m6(c,out,judge)['value'] for _ in range(n)]
            mode_v=Counter(vals).most_common(1)[0][0]
            if mode_v==0: still0+=1
            else: corrected.append((case,arm,os.path.basename(ep),mode_v))
            grand_total+=1
        grand_still0+=still0
        print(f"  {case}_{arm}: 复核{len(picks)}局 | 仍判0: {still0} | 被纠正: {len(picks)-still0}")
    print("="*60)
    rate=(grand_total-grand_still0)/grand_total*100 if grand_total else 0
    print(f"总计: {grand_total}局 | 仍判0: {grand_still0} | 被纠正: {grand_total-grand_still0} | 误判率: {rate:.0f}%")
    if corrected:
        print("\n被纠正的局（历史判0→重判更高）:")
        for case,arm,name,v in corrected:
            print(f"  {case}_{arm} {name}: 0 → {v}")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="eval.glm52local.yaml")
    ap.add_argument("--n",type=int,default=1)
    ap.add_argument("--sample",type=int,default=3)
    a=ap.parse_args()
    main(a.config,a.n,a.sample)
