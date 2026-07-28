#!/usr/bin/env python3
"""离线重判工具 — metrics 体检地基。
读老 episode.json，重建 EpisodeOutput，反复调 qwen judge 判 metric，统计分布。
不跑对局，只重判，省时间。judge 固定走 eval config 的 aux（qwen），与历史一致。

用法：
  # M11 门控验证（不需要 judge）
  python rejudge.py --mode m11 --case R4P9 --episode 路径/xxx_episode.json

  # M6 稳定性：同一局重判 N 次
  python rejudge.py --mode m6 --case R4P9 --episode 路径/xxx_episode.json --n 10 --config configs/legacy/eval.glm52local.yaml
"""
import sys, json, statistics, argparse
from collections import Counter
sys.path.insert(0, '.')

from negoeval.schemas import EpisodeOutput
from negoeval import cases as cases_mod
from negoeval.grade import judge as jdg
from negoeval.llm.registry import build_provider


def load_case(case_id):
    for c in cases_mod.load_all():
        if c.case_id == case_id:
            return c
    raise ValueError(f"case {case_id} not found")


def load_episode(path):
    ep = json.load(open(path, encoding="utf-8"))
    return EpisodeOutput(**ep)


def make_judge(case, config_path):
    """复现 batch.py 的 judge 构建：judge_cfg = live_config.aux。"""
    from negoeval.llm.liveconfig import load_live_config
    live = load_live_config(config_path)
    judge_cfg = live.aux
    return build_provider("judge", mode="live", case=case, agent_profile="par", llm_config=judge_cfg)


def rejudge_m6(case_id, episode_path, n, config_path):
    case = load_case(case_id)
    out = load_episode(episode_path)
    judge = make_judge(case, config_path)
    vals = []
    for i in range(n):
        r = jdg.m6(case, out, judge)
        vals.append(r["value"])
        print(f"  #{i+1}: tier={r['value']} ({r.get('tier')})")
    c = Counter(vals)
    print(f"\n  分布: {dict(sorted(c.items()))}")
    print(f"  均值 {statistics.mean(vals):.2f} | 标准差 {statistics.pstdev(vals):.2f} | 众数 {c.most_common(1)[0]}")
    return vals


def check_m11(case_id, episode_path):
    case = load_case(case_id)
    out = load_episode(episode_path)
    r = jdg.m11(case, out, None)  # judge=None：门控对则不调 judge
    print(f"  M11 verdict={r.get('verdict')} | applicable={r.get('applicable')}")
    print(f"  notes: {r.get('judge_notes')}")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["m6", "m11"], required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--config", default="configs/legacy/eval.glm52local.yaml")
    args = ap.parse_args()
    if args.mode == "m11":
        check_m11(args.case, args.episode)
    else:
        rejudge_m6(args.case, args.episode, args.n, args.config)
