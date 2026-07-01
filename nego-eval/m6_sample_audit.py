#!/usr/bin/env python3
"""M6 抽样审计 — 分层抽样重判，对比历史判分，验稳定性+正确性。
先自验（clean-r2应判0），通过才跑抽样。每局重判N次取众数。
用法: python m6_sample_audit.py --config eval.glm52local.yaml --n 3
"""
import sys, json, glob, os, argparse
from collections import defaultdict, Counter
sys.path.insert(0,'.')
from negoeval.schemas import EpisodeOutput
from negoeval import cases as cases_mod
from negoeval.grade import judge as jdg
from negoeval.llm.registry import build_provider
from negoeval.llm.liveconfig import load_live_config

_cc={}
def load_case(cid):
    if cid not in _cc:
        _cc[cid]=next(c for c in cases_mod.load_all() if c.case_id==cid)
    return _cc[cid]

def make_judge(case,cfg):
    live=load_live_config(cfg)
    return build_provider("judge",mode="live",case=case,agent_profile="par",llm_config=live.aux)

def judge_n(case_id, ep_path, cfg, n):
    case=load_case(case_id)
    out=EpisodeOutput(**json.load(open(ep_path,encoding='utf-8')))
    judge=make_judge(case,cfg)
    vals=[jdg.m6(case,out,judge)['value'] for _ in range(n)]
    return Counter(vals).most_common(1)[0][0], vals

def selfcheck(cfg):
    """自验：clean-r2 应稳定判 0。"""
    ep='results/01_R4_core/glm52_crashrate/R4P9__skills-clean__clean-r2.episode.json'
    if not os.path.exists(ep):
        print("⚠ 自验局不存在，跳过自验（风险：工具未验证）"); return True
    mode,vals=judge_n('R4P9',ep,cfg,3)
    ok = mode==0
    print(f"[自验] clean-r2 重判{vals} 众数{mode} | 期望0 | {'✓通过' if ok else '✗工具可疑！'}")
    return ok

def build_sample():
    """分层抽样：每case按可用档位抽局。"""
    pool=defaultdict(lambda: defaultdict(list))
    for f in glob.glob('results/01_R4_core/**/*.json', recursive=True):
        bn=os.path.basename(f)
        if any(x in bn for x in ['episode','trace','summary']): continue
        case=bn.split('__')[0]
        if case not in ('R4P1','R4P2','R4P3','R4P6','R4P9'): continue
        ep=f.replace('.json','.episode.json')
        if not os.path.exists(ep): continue
        try:
            v=json.load(open(f))['metrics']['M6']['value']
            pool[case][v].append(ep)
        except: pass
    # 每case每档抽最多2局
    sample=[]
    for case in ['R4P1','R4P2','R4P3','R4P6','R4P9']:
        for tier in range(5):
            for ep in pool[case][tier][:2]:
                sample.append((case,tier,ep))
    return sample

def main(cfg,n):
    if not selfcheck(cfg):
        print("自验未通过，停止抽样（避免用坏工具下结论）"); return
    print("="*70)
    sample=build_sample()
    print(f"分层抽样 {len(sample)} 局，每局重判{n}次取众数\n")
    agree=0; disagree=[]
    print(f"{'case':6}{'arm/hist':12}{'重判':18}{'众数':6}{'历史':6}{'一致'}")
    print("-"*60)
    for case,hist_tier,ep in sample:
        mode,vals=judge_n(case,ep,cfg,n)
        ok=mode==hist_tier
        if ok: agree+=1
        else: disagree.append((case,hist_tier,mode,os.path.basename(ep)))
        arm='clean' if 'clean' in ep else ('on' if '__on' in ep else 'off')
        print(f"{case:6}{arm+'/'+str(hist_tier):12}{str(dict(Counter(vals))):18}{mode:<6}{hist_tier:<6}{'✓' if ok else '✗'}")
    print("-"*60)
    rate=agree/len(sample)*100
    print(f"\n一致率: {agree}/{len(sample)} = {rate:.0f}%")
    if disagree:
        print("\n不一致局（需人工核验谁对）:")
        for case,h,m,name in disagree:
            print(f"  {case} {name}: 历史{h} → 重判{m}")
    print(f"\n判读: {'✓ M6全量大概率稳' if rate>=90 else ('⚠ 有噪声但可控' if rate>=80 else '✗ 系统问题需深挖')}")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="eval.glm52local.yaml")
    ap.add_argument("--n",type=int,default=3)
    main(ap.parse_args().config, ap.parse_args().n)
