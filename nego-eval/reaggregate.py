#!/usr/bin/env python3
"""重聚合：在现有 result JSON 上按新口径重算 quality（gate on case_pass），
不重跑对局。M6=quality if case_pass else 0。
用法: python reaggregate.py <results_dir> [<results_dir2> ...]
"""
import json, glob, os, sys, re
from collections import defaultdict

def load(dirs):
    rows=[]
    for d in dirs:
        for f in glob.glob(f"{d}/*.json"):
            b=os.path.basename(f)
            if "episode" in b or "summary" in b: continue
            mm=re.match(r"(R4\w+)__skills-(\w+)__([\w-]+)\.json",b)
            if not mm: continue
            x=json.load(open(f)); m=x["metrics"]; v=x.get("verdict",{})
            model="GLM" if "glm" in d.lower() else ("DS" if "ds" in d.lower() else x.get("config",{}).get("agent_model","?"))
            rows.append(dict(case=mm.group(1),arm=mm.group(2),model=model,
                M5=m["M5"]["pass"], M5reason=m["M5"].get("reason",""),
                M6=m["M6"]["value"],
                gates=v.get("gates_pass"), case_pass=v.get("case_pass"),
                old_quality=v.get("quality")))
    return rows

def new_quality(r):
    return r["M6"] if r["case_pass"] else 0

def main(dirs):
    rows=load(dirs)
    cases=sorted(set(r["case"] for r in rows))
    models=sorted(set(r["model"] for r in rows))

    print("="*76)
    print("重聚合: 旧口径(M6直给) vs 新口径(gate on case_pass, 失败=0)")
    print("="*76)
    for model in models:
        print(f"\n### {model} ###")
        print(f"{'case':6}{'arm':6}{'n':>3}{'旧qmean':>8}{'新qmean':>8}{'Δ':>7}")
        by=defaultdict(list)
        for r in rows:
            if r["model"]==model: by[(r["case"],r["arm"])].append(r)
        for c in cases:
            for arm in ["clean","on"]:
                rs=by.get((c,arm))
                if not rs: continue
                n=len(rs)
                old=sum(r["old_quality"] for r in rs)/n
                new=sum(new_quality(r) for r in rs)/n
                print(f"{c:6}{arm:6}{n:>3}{old:>8.3f}{new:>8.3f}{new-old:>+7.3f}")
        # 模型整体 clean vs on 新口径
        print(f"  --- {model} 整体(新口径) ---")
        for arm in ["clean","on"]:
            rs=[r for r in rows if r["model"]==model and r["arm"]==arm]
            n=len(rs)
            new=sum(new_quality(r) for r in rs)/n
            print(f"    [{arm:5}] n={n}  新qmean={new:.3f}")
        cl=[r for r in rows if r["model"]==model and r["arm"]=="clean"]
        on=[r for r in rows if r["model"]==model and r["arm"]=="on"]
        dnew=sum(new_quality(r) for r in on)/len(on) - sum(new_quality(r) for r in cl)/len(cl)
        print(f"    → clean→on 提升(新口径): {dnew:+.3f}")

    # 被清零统计
    print("\n"+"="*76)
    cleared=[r for r in rows if not r["case_pass"] and r["M6"]>0]
    print(f"被清零的局: {len(cleared)}/{len(rows)} ({len(cleared)/len(rows):.1%})")
    m5=[r for r in cleared if not r["M5"]]
    gate=[r for r in cleared if r["M5"] and not r["gates"]]
    print(f"  M5挂: {len(m5)}  (over budget {sum(1 for r in m5 if 'cash_over_cap' in r['M5reason'])} / not settled {sum(1 for r in m5 if r['M5reason']=='not_settled')})")
    print(f"  gate挂: {len(gate)}")

if __name__=="__main__":
    dirs=sys.argv[1:] if len(sys.argv)>1 else ["ds_zip/night_ds","glm_zip2/night_glm"]
    main(dirs)
