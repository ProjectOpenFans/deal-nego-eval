#!/usr/bin/env python3
"""
judge_calibration.py — pick a replacement judge after qwen went dark.

Fixes the transcript (never re-runs the agent) and only swaps the judge model,
so differences are pure judge behavior. Scores M6 (and M2 as a gate cross-check)
for each candidate judge, N times per episode, then reports:

  1. CONSISTENCY  — same episode + same judge, N repeats: do they agree?
  2. CALIBRATION  — does the new judge's tier match the qwen-era recorded tier?
  3. SELF-PREFERENCE — does a judge score its OWN family's agent episodes higher?

Usage:
  python judge_calibration.py --episodes-dir results/v2b_focus \
      --judges deepseek,glm,kimi --repeats 3 --out results/judge_cal

Run from repo root (needs negoeval importable). Judges are provider keys from
your PRESETS (deepseek / glm / kimi / stepfun). qwen excluded (dead).
"""
import argparse, json, glob, os, sys, statistics as st
from collections import defaultdict
from pathlib import Path

# --- repo imports ---
from negoeval.llm.liveconfig import _spec, _load_dotenv
from negoeval.llm.registry import build_provider
from negoeval.schemas import EpisodeOutput
from negoeval.cases import load_case, load_all
from negoeval.grade import judge as J

def build_judge(provider_key: str):
    dotenv = _load_dotenv()
    spec = _spec({"provider": provider_key}, dotenv)
    if not spec.api_key:
        raise SystemExit(f"[{provider_key}] no API key resolved — check .env")
    # judge wants temperature 0 determinism; force it via chat_completion arg later
    return build_provider("aux", mode="live", llm_config=spec)

def agent_family_of(path: str) -> str:
    # v2b_focus/<model>/<case>__... → model dir is the agent family
    parts = Path(path).parts
    for p in parts:
        if p in ("deepseek", "glm52local", "stepfun", "kimi", "glm"):
            return "deepseek" if p.startswith("deepseek") else ("glm" if p.startswith("glm") else p)
    return "unknown"

def load_episode(ep_path: str):
    d = json.load(open(ep_path, encoding="utf-8"))
    out = EpisodeOutput.model_validate(d)
    return out

def recorded_tier(result_json_path: str):
    """qwen-era M6 tier/value from the sibling result .json, as ground-truth-ish anchor."""
    try:
        r = json.load(open(result_json_path, encoding="utf-8"))
        m6 = r.get("metrics", {}).get("M6", {})
        return m6.get("value"), m6.get("tier")
    except Exception:
        return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes-dir", required=True)
    ap.add_argument("--judges", default="deepseek,glm,kimi")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--cases-dir", default=None)
    ap.add_argument("--out", default="results/judge_cal")
    ap.add_argument("--limit", type=int, default=0, help="cap #episodes (0=all)")
    args = ap.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    cases = {c.case_id: c for c in load_all(args.cases_dir)}

    ep_paths = sorted(glob.glob(f"{args.episodes_dir}/**/*.episode.json", recursive=True))
    if args.limit: ep_paths = ep_paths[:args.limit]
    if not ep_paths:
        raise SystemExit(f"no *.episode.json under {args.episodes_dir}")

    judges = {k: build_judge(k) for k in args.judges.split(",")}
    print(f"judges: {list(judges)}  episodes: {len(ep_paths)}  repeats: {args.repeats}\n")

    rows = []  # one per (episode, judge, repeat)
    for ep_path in ep_paths:
        case_id = Path(ep_path).name.split("__")[0]
        case = cases.get(case_id)
        if case is None:
            print(f"  skip {case_id}: not in cases dir"); continue
        out = load_episode(ep_path)
        family = agent_family_of(ep_path)
        rjson = ep_path.replace(".episode.json", ".json")
        rec_val, rec_tier = recorded_tier(rjson)

        for jkey, judge in judges.items():
            for rep in range(args.repeats):
                try:
                    # force determinism: patch judge.chat_completion temperature=0 via wrapper
                    res = J.m6(case, out, _T0(judge))
                    rows.append(dict(case=case_id, family=family, judge=jkey, rep=rep,
                                     value=res.get("value"), tier=res.get("tier"),
                                     parse_ok=res.get("judge_parse_ok"),
                                     rec_val=rec_val, rec_tier=rec_tier,
                                     ep=Path(ep_path).name))
                    print(f"  {case_id:7} fam={family:9} judge={jkey:9} rep{rep} "
                          f"-> {res.get('value')}({res.get('tier')})  [qwen:{rec_val}]")
                except Exception as e:
                    print(f"  {case_id} {jkey} rep{rep} ERROR {type(e).__name__}: {str(e)[:80]}")
    json.dump(rows, open(f"{args.out}/raw.json","w"), ensure_ascii=False, indent=2)

    # ---- Table 1: CONSISTENCY (variance within episode+judge across repeats) ----
    print("\n" + "="*66 + "\nTABLE 1 — CONSISTENCY (same ep+judge, repeats; want variance=0)\n" + "="*66)
    byjudge_incons = defaultdict(list)
    grp = defaultdict(list)
    for r in rows:
        grp[(r["case"], r["ep"], r["judge"])].append(r["value"])
    for (case, ep, jkey), vals in sorted(grp.items()):
        vals = [v for v in vals if v is not None]
        if len(vals) < 2: continue
        spread = max(vals) - min(vals)
        byjudge_incons[jkey].append(spread)
        flag = "" if spread == 0 else f"  <-- SPREAD {spread}"
        if spread: print(f"  {case:7} {jkey:9} vals={vals}{flag}")
    print("\n  per-judge mean spread (0 = perfectly consistent):")
    for jkey, spreads in byjudge_incons.items():
        print(f"    {jkey:9} mean_spread={st.mean(spreads):.2f}  max={max(spreads)}")

    # ---- Table 2: CALIBRATION vs qwen recorded tier ----
    print("\n" + "="*66 + "\nTABLE 2 — CALIBRATION (agreement with qwen-era recorded value)\n" + "="*66)
    for jkey in judges:
        agree = tot = 0
        for r in rows:
            if r["judge"] != jkey or r["value"] is None or r["rec_val"] is None: continue
            tot += 1; agree += int(r["value"] == r["rec_val"])
        rate = f"{100*agree/tot:.0f}%" if tot else "n/a"
        print(f"  {jkey:9} exact-tier agreement with qwen: {agree}/{tot} = {rate}")

    # ---- Table 3: SELF-PREFERENCE ----
    print("\n" + "="*66 + "\nTABLE 3 — SELF-PREFERENCE (judge scoring its own family higher?)\n" + "="*66)
    # mean value each judge gives to each agent family
    cell = defaultdict(list)
    for r in rows:
        if r["value"] is None: continue
        cell[(r["judge"], r["family"])].append(r["value"])
    fams = sorted({r["family"] for r in rows})
    print(f"  {'judge':10}" + "".join(f"{f:>12}" for f in fams))
    for jkey in judges:
        line = f"  {jkey:10}"
        for f in fams:
            vals = cell.get((jkey,f), [])
            line += f"{(st.mean(vals) if vals else float('nan')):>12.2f}"
        # flag own-family bias
        own = jkey if jkey in fams else ("glm" if jkey=="glm" else jkey)
        print(line)
    print("\n  read: compare each judge's score for ITS OWN family vs others.")
    print("  a judge that scores its own family notably higher = self-preference.")

    print(f"\nraw saved -> {args.out}/raw.json")

class _T0:
    """wrap a provider so chat_completion always runs at temperature=0 (judge determinism)."""
    def __init__(self, p): self._p = p
    def chat_completion(self, messages, temperature=None, max_tokens=None, enable_thinking=None):
        return self._p.chat_completion(messages, temperature=0.0, max_tokens=max_tokens)

if __name__ == "__main__":
    main()
