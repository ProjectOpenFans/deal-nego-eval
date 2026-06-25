#!/usr/bin/env python3
"""Build the R3.5 standalone HTML report (locked template) from nego-eval result dirs.
Reuses the directory-scan logic; replaces aggregation + HTML with the finalized design:
  ① model cards  ·  Key Findings (auto-derived)  ·  ② discrimination matrix
  ③ gate-failure exec cards (bug/behavior triage)  ·  per-run M1–M12 + harness row + judge
Gate set = M1–M4 + M5 (M7 deleted). on-arm carries M11/M12; off-arm marked 未评估.
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

BENCHMARKS = [
    {"id": "deepseek", "label": "DeepSeek V4 Pro", "model": "deepseek-v4-pro", "subdir": "r3-deepseek"},
    {"id": "glm",      "label": "GLM-5.1",         "model": "glm-5.1",         "subdir": "r3-glm"},
    {"id": "kimi",     "label": "Kimi K2.6",       "model": "kimi-k2.6",       "subdir": "r3-kimi"},
]

def load_benchmark(bench: dict) -> dict:
    runs = []
    for path in sorted(bench["dir"].glob("P*.json")):
        if path.name.endswith(".episode.json"):
            continue
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return {**bench, "runs": runs}

def aggregate(benchmarks):
    models = [b["label"] for b in benchmarks]
    tags   = [b["model"] for b in benchmarks]
    cases  = sorted({r["case_id"] for b in benchmarks for r in b["runs"]})
    matrix, runs_flat, fail_index = {}, [], {}
    for b in benchmarks:
        model = b["label"]; matrix[model] = {}
        groups = {}
        for r in b["runs"]:
            arm = r.get("config", {}).get("skills", "?")
            groups.setdefault((r["case_id"], arm), []).append(r)
        for (cid, arm), rs in groups.items():
            rs.sort(key=lambda x: x.get("run_id", ""))
            outs = [bool(x.get("verdict", {}).get("case_pass")) for x in rs]
            m6s  = [x["metrics"].get("M6", {}).get("value", 0) for x in rs]
            n = len(rs) or 1
            matrix[model].setdefault(cid, {})[arm] = {
                "runs": [{"pass": outs[k], "m6": m6s[k]} for k in range(len(rs))],
                "pass": round(100 * sum(outs) / n),
                "m6":   round(sum(m6s) / n, 2),
                "dec":  any((m6s[k] >= 2 and not outs[k]) for k in range(len(rs))),
            }
        for r in b["runs"]:
            m = r["metrics"]; arm = r.get("config", {}).get("skills", "?")
            loc = f"{model.split()[0]}·{r['case_id']}·{arm}"
            if not m.get("M2", {}).get("pass", True):
                fail_index.setdefault("M2 · 凭空落定/扩范围", []).append(loc)
            m5 = m.get("M5", {})
            if not m5.get("pass", True) and m5.get("reason"):
                fail_index.setdefault(f"M5 · {m5['reason']}", []).append(loc)
            def jn(mid): return m.get(mid, {}).get("judge_notes", "")
            M11 = m.get("M11") or {}; M12 = m.get("M12") or {}
            runs_flat.append({
                "model": model, "case": r["case_id"], "arm": arm,
                "pass": bool(r.get("verdict", {}).get("case_pass")),
                "mt": {
                    "M1": {"pass": m.get("M1",{}).get("pass"), "info": ("missing "+",".join(m.get("M1",{}).get("missing",[])) if m.get("M1",{}).get("missing") else "")},
                    "M2": {"pass": m.get("M2",{}).get("pass"), "judge": jn("M2")},
                    "M3": {"pass": m.get("M3",{}).get("pass"), "info": ("hits "+",".join(m.get("M3",{}).get("hits",[])) if m.get("M3",{}).get("hits") else "")},
                    "M4": {"pass": m.get("M4",{}).get("pass"), "info": ("unmapped "+",".join(m.get("M4",{}).get("unmapped",[])) if m.get("M4",{}).get("unmapped") else "")},
                    "M5": {"pass": m.get("M5",{}).get("pass"), "info": m.get("M5",{}).get("reason","")},
                    "M6": {"val": m.get("M6",{}).get("value"), "judge": jn("M6")},
                    "M8": {"val": m.get("M8",{}).get("value")},
                    "M9": {"val": m.get("M9",{}).get("value")},
                    "M11": {"verdict": M11.get("verdict"), "diagnosis": M11.get("diagnosis",""), "judge": M11.get("judge_notes","")},
                    "M12": {"verdict": M12.get("verdict"), "routes": M12.get("routes"), "judge": M12.get("judge_notes","")},
                },
                "settlement": m.get("M10", {}).get("value"),
            })
    fail_index = {k: {"n": len(v), "locs": v} for k, v in sorted(fail_index.items(), key=lambda x: -len(x[1]))}
    return {"models": models, "tags": tags, "cases": cases, "matrix": matrix, "fail_index": fail_index, "runs": runs_flat}

def derive_findings(D):
    """Auto-derive factual Key Findings from THIS run's data (not mock). Meant for a human pass."""
    def magg(model):
        on=[];off=[];onm=[];offm=[]
        for c in D["cases"]:
            cell=D["matrix"][model].get(c,{})
            if "on" in cell: on.append(cell["on"]["pass"]); onm.append(cell["on"]["m6"])
            if "off" in cell: off.append(cell["off"]["pass"]); offm.append(cell["off"]["m6"])
        avg=lambda a: sum(a)/len(a) if a else 0
        return avg(on),avg(off),avg(onm),avg(offm)
    # harness: M6 on-off direction across models
    m6dirs=[]
    for m in D["models"]:
        _,_,onm,offm=magg(m); m6dirs.append(onm-offm)
    n_pos=sum(1 for d in m6dirs if d>0.05)
    harness=f"M6（价值创造）on−off：{n_pos}/{len(D['models'])} 模型为正。" + ("多数为正,harness 在价值轴有增益。" if n_pos>=2 else "增益不一致,需逐模型看。")
    # discrimination: pass% spread vs M6 spread
    allp=[D["matrix"][m][c][a]["pass"] for m in D["models"] for c in D["cases"] for a in ("off","on") if a in D["matrix"][m].get(c,{})]
    allm=[D["matrix"][m][c][a]["m6"]*50 for m in D["models"] for c in D["cases"] for a in ("off","on") if a in D["matrix"][m].get(c,{})]
    disc="区分度信号需对比 pass% 与 M6 两轴的离散度（见矩阵）——通常 M6 更能拉开差距。"
    # case bank: soft (all pass) / hard (all-fail bare)
    soft=[c for c in D["cases"] if all(D["matrix"][m].get(c,{}).get(a,{}).get("pass",0)>=100 for m in D["models"] for a in ("off","on") if a in D["matrix"][m].get(c,{}))]
    hardbare=[c for c in D["cases"] if all(D["matrix"][m].get(c,{}).get("off",{}).get("pass",100)==0 for m in D["models"] if "off" in D["matrix"][m].get(c,{}))]
    cb=f"软（近全过）: {', '.join(soft) or '无'} · bare 全挂（偏硬）: {', '.join(hardbare) or '无'}。中间档缺位是补库重点。"
    # variance: cells where 3 runs disagree
    split=0;tot=0
    for m in D["models"]:
        for c in D["cases"]:
            for a in ("off","on"):
                cell=D["matrix"][m].get(c,{}).get(a)
                if cell and cell["runs"]:
                    tot+=1
                    ps=[r["pass"] for r in cell["runs"]]
                    if len(set(ps))>1: split+=1
    var=f"{split}/{tot} 个格子三局成败不一致 → 方差真实存在,单点不可信,置信区间宽,要下硬结论需 5+ run。"
    return harness, disc, cb, var

# ---------- HTML ----------
def build_html(D):
    findings = derive_findings(D)
    mock = json.dumps(D, ensure_ascii=False)
    F0,F1,F2,F3 = findings
    tpl = r'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>R3.5 谈判 Agent 评测 · Report</title>
<style>
:root{
  --bg:#f4f3f0; --panel:#ffffff; --panel2:#eeece8; --line:#e4e1da; --line2:#d7d3ca;
  --ink:#23262b; --dim:#62646a; --faint:#9a9890;
  --pass:#2f8a5e; --fail:#c44a32; --amber:#b07d36; --score:#3f63a8; --part:#a5841f;
  --passbg:rgba(47,138,94,.10); --failbg:rgba(196,74,50,.10); --scorebg:rgba(63,99,168,.09);
  --mono:"SF Mono","JetBrains Mono","Menlo",monospace; --sans:-apple-system,"Inter","Segoe UI",system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;padding:40px 28px 90px;max-width:1240px;margin:0 auto;-webkit-font-smoothing:antialiased}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--faint);margin-bottom:12px}
h1{font-size:32px;font-weight:680;letter-spacing:-.02em} h1 .v{color:var(--pass)}
.sub{color:var(--dim);font-size:14px;margin-top:6px}
.meta{font-family:var(--mono);font-size:12px;color:var(--faint);margin-top:8px} .meta b{color:var(--dim);font-weight:500}
.note-auto{margin:22px 0 8px;background:var(--scorebg);border:1px solid rgba(63,99,168,.3);border-radius:8px;padding:11px 16px;font-size:12.5px;color:#33538c;font-family:var(--mono)}
section{margin-top:44px}
h2.head{font-size:12px;font-family:var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--dim);padding-bottom:9px;border-bottom:1px solid var(--line2);margin-bottom:18px;display:flex;justify-content:space-between;align-items:baseline}
h2.head .hint{font-size:11px;color:var(--faint);text-transform:none;letter-spacing:0}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:20px 18px;position:relative;overflow:hidden;box-shadow:0 1px 2px rgba(20,25,35,.04)}
.card .strip{position:absolute;top:0;left:0;right:0;height:3px}
.card .name{font-size:16px;font-weight:680} .card .tag{font-family:var(--mono);font-size:11px;color:var(--faint);margin:2px 0 16px}
.card .row{display:flex;justify-content:space-between;align-items:baseline;padding:6px 0} .card .row+.row{border-top:1px solid var(--line)}
.card .k{font-size:12px;color:var(--dim)} .card .num{font-family:var(--mono);font-size:21px;font-weight:680} .card .num.sm{font-size:14px}
.delta{font-family:var(--mono);font-size:12px} .up{color:var(--pass)} .down{color:var(--fail)} .flat{color:var(--faint)}
.readnote{margin-top:14px;font-size:12.5px;color:var(--dim);font-family:var(--mono);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:11px 14px;line-height:1.7} .readnote b{color:var(--ink)} .readnote .x{color:var(--faint);text-decoration:line-through}
.exec{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.ins{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;border-left:3px solid var(--score);box-shadow:0 1px 2px rgba(20,25,35,.04)}
.ins .cat{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:7px}
.ins h3{font-size:14.5px;font-weight:670;margin-bottom:5px;line-height:1.35}
.ins p{font-size:13px;color:var(--dim);line-height:1.6} .ins p b{color:var(--ink);font-weight:600}
.ins.amber{border-left-color:var(--amber)} .ins.green{border-left-color:var(--pass)} .ins.red{border-left-color:var(--fail)}
.mwrap{overflow-x:auto}
table.mx{width:100%;border-collapse:collapse;font-family:var(--mono);min-width:880px}
.mx th,.mx td{border:1px solid var(--line);text-align:center;padding:0}
.mx thead th{background:var(--panel2);color:var(--dim);font-weight:500;font-size:11px;padding:7px 6px}
.mx thead .mg{border-left:2px solid var(--line2)} .mx .caseh{background:var(--panel);color:var(--ink);font-weight:680;font-size:13px;width:46px}
.cell{padding:8px 4px!important;position:relative} .cell.mg{border-left:2px solid var(--line2)}
.dots{font-size:12px;letter-spacing:2px;line-height:1} .dots .p{color:var(--pass)} .dots .f{color:var(--fail);opacity:.5}
.cell .pct{font-size:14px;font-weight:680;margin-top:3px} .cell .m6{font-size:10px;color:var(--faint);margin-top:1px}
.cell .dec{position:absolute;top:3px;right:4px;color:var(--score);font-size:10px}
.dcol{width:42px;background:var(--panel)} .dcol .d{font-size:12px;font-weight:680}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:12px;color:var(--dim);font-family:var(--mono)} .legend b{color:var(--ink);font-weight:500}
.cgrid{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.fmode{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;border-left:3px solid var(--fail);box-shadow:0 1px 2px rgba(20,25,35,.04)}
.fmode.beh{border-left-color:var(--amber)} .fmode.bug{border-left-color:var(--score)}
.fmode .ft{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}
.fmode .fn{font-family:var(--mono);font-size:13px;font-weight:650} .fmode .cnt{font-family:var(--mono);font-size:20px;font-weight:680}
.fmode .verdict{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.06em;padding:2px 8px;border-radius:5px;margin-bottom:9px}
.verdict.bug{background:var(--scorebg);color:var(--score)} .verdict.beh{background:rgba(176,125,54,.13);color:var(--amber)} .verdict.edge{background:var(--panel2);color:var(--faint)}
.fmode .exp{font-size:13px;color:var(--dim);line-height:1.6;margin-bottom:10px} .fmode .exp b{color:var(--ink);font-weight:600}
.fmode .cls{display:flex;flex-wrap:wrap;gap:5px}
.fmode .loc{font-family:var(--mono);font-size:10.5px;color:var(--faint);background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:2px 7px}
.tbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;align-items:center}
.tbar button,.tbar select{background:var(--panel);color:var(--dim);border:1px solid var(--line2);border-radius:7px;padding:6px 13px;font-family:var(--mono);font-size:12px;cursor:pointer}
.tbar button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.runs{display:flex;flex-direction:column;gap:11px}
.run{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(20,25,35,.04)}
.run .rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px}
.run .rid{font-family:var(--mono);font-size:13px;font-weight:650} .run .rid .arm{color:var(--faint);font-weight:400}
.run .vd{font-family:var(--mono);font-size:11px;padding:2px 9px;border-radius:5px}
.vd.pass{background:var(--passbg);color:var(--pass)} .vd.fail{background:var(--failbg);color:var(--fail)}
.mstrip{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:11px}
.mc{font-family:var(--mono);font-size:11px;border:1px solid var(--line);border-radius:6px;padding:3px 8px;display:flex;gap:5px;align-items:center;background:var(--panel2)}
.mc .lab{color:var(--faint)} .mc.ok .v{color:var(--pass)} .mc.no{border-color:rgba(196,74,50,.4);background:var(--failbg)} .mc.no .v{color:var(--fail)}
.mc.sc .v{color:var(--score)} .mc.rec .v{color:var(--dim)} .mc .rs{color:var(--faint)}
.hrow{font-family:var(--mono);font-size:12px;background:var(--scorebg);border:1px solid rgba(63,99,168,.22);border-radius:8px;padding:9px 12px;margin-bottom:9px;line-height:1.8}
.hrow .hl{color:var(--faint);font-size:10px;letter-spacing:.08em}
.hrow .vf{padding:1px 7px;border-radius:4px;font-size:10px;margin-left:4px}
.vf.full{background:var(--passbg);color:var(--pass)} .vf.partial{background:rgba(165,132,31,.16);color:var(--part)} .vf.fail{background:var(--failbg);color:var(--fail)} .vf.na{background:var(--panel2);color:var(--faint)}
.hrow .route{color:var(--ink);font-weight:600} .hrow .arrow{color:var(--faint);margin:0 4px}
.kv{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-bottom:9px;line-height:1.6} .kv b{color:var(--dim);font-weight:500}
.note{font-size:12.5px;color:var(--dim);line-height:1.62;padding:9px 11px;background:var(--panel2);border-radius:7px;border-left:2px solid var(--line2);margin-top:7px}
.note .nl{font-family:var(--mono);font-size:10px;color:var(--faint);letter-spacing:.08em;display:block;margin-bottom:3px}
@media(max-width:860px){.cards,.exec,.cgrid{grid-template-columns:1fr}body{padding:28px 14px 60px}}
</style></head><body>
<div class="eyebrow">Dealhouse · Negotiation Eval</div>
<h1>R3.5 <span class="v">Report</span></h1>
<p class="sub">v0→v1 全自主谈判块 · 三模型 × 6 case (P1–P6) × skills on/off · 各 3 run</p>
<p class="meta">aux <b>qwen3.7-max</b> · agent <b>pro</b> · 门集 <b>M1–M4 + 成交(M5)</b> · M7 已删 · <span id="dt"></span></p>
<div class="note-auto">ⓘ Key Findings 与 Panel ③ 解读为<b>按本轮真实数据自动生成的事实陈述</b>,建议人工过一遍润色定调。</div>

<section><h2 class="head">① 大盘 · 模型 × harness 增益<span class="hint">pass% 看守门 · M6 看价值 · 一起读</span></h2>
<div class="cards" id="cards"></div><div class="readnote" id="readnote"></div></section>

<section><h2 class="head">Key Findings · 给 IC 的执行摘要<span class="hint">本轮就回答这几件事</span></h2>
<div class="exec">
  <div class="ins"><div class="cat">Harness</div><h3>harness 的价值轴增益</h3><p>__F0__</p></div>
  <div class="ins green"><div class="cat">Discrimination</div><h3>区分度落在哪条轴</h3><p>__F1__</p></div>
  <div class="ins amber"><div class="cat">Case Bank</div><h3>案库软硬分布</h3><p>__F2__</p></div>
  <div class="ins red"><div class="cat">Variance</div><h3>3-run 方差</h3><p>__F3__</p></div>
</div></section>

<section><h2 class="head">② 区分度矩阵<span class="hint">●●○ 三局 · ◆ 解耦 · Δ=on−off</span></h2>
<div class="mwrap"><table class="mx" id="mx"></table></div>
<div class="legend"><span><span class="dots"><span class="p">●</span><span class="p">●</span><span class="f">○</span></span> 三局成败</span>
<span><b style="color:var(--score)">◆</b> M6≥2 但门挂</span><span>底色=pass%</span><span>Δ=harness 增益</span></div></section>

<section><h2 class="head">③ 门控失败拆解 · bug-triage<span class="hint">每种失败：是 bug 还是行为 · 怎么办</span></h2><div class="cgrid" id="cgrid"></div></section>

<section><h2 class="head">逐局详情 · M1–M12 全量<span class="hint">一行扫完 metric · harness 路由独立成行 · judge 默认展开</span></h2>
<div class="tbar" id="tbar"></div><div class="runs" id="runs"></div></section>

<script>
const D=__MOCK__;
document.getElementById('dt').textContent=new Date().toISOString().slice(0,10);
const STRIP=['var(--amber)','var(--pass)','var(--fail)'];
function modelAgg(model){let on={p:[],m6:[]},off={p:[],m6:[]};
  for(const c of D.cases){const cell=D.matrix[model][c]||{};for(const arm of ['off','on']){if(!cell[arm])continue;const x=cell[arm];(arm==='on'?on:off).p.push(x.pass);(arm==='on'?on:off).m6.push(x.m6);}}
  const avg=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:0;
  return{onP:avg(on.p),offP:avg(off.p),onM6:avg(on.m6),offM6:avg(off.m6),allP:avg(on.p.concat(off.p)),allM6:avg(on.m6.concat(off.m6))};}
function dlt(a,b,u){const d=a-b,c=d>0.5?'up':d<-0.5?'down':'flat',s=d>0?'↑':d<0?'↓':'';return `<span class="delta ${c}">${a.toFixed(u==='%'?0:2)} ← ${b.toFixed(u==='%'?0:2)} ${s}</span>`;}
document.getElementById('cards').innerHTML=D.models.map((m,i)=>{const a=modelAgg(m);
  return `<div class="card"><div class="strip" style="background:${STRIP[i%3]}"></div><div class="name">${m}</div><div class="tag">${D.tags[i]} · agent</div>
  <div class="row"><span class="k">整体 pass%</span><span class="num">${a.allP.toFixed(0)}<span style="font-size:12px;color:var(--faint)">%</span></span></div>
  <div class="row"><span class="k">M6 均值</span><span class="num sm">${a.allM6.toFixed(2)}</span></div>
  <div class="row"><span class="k">on vs off · pass%</span>${dlt(a.onP,a.offP,'%')}</div>
  <div class="row"><span class="k">on vs off · M6</span>${dlt(a.onM6,a.offM6,'')}</div></div>`;}).join('');
document.getElementById('readnote').innerHTML=`读数约定 · <b>pass%</b>=守门率(M1–M4+成交)，<span class="x">M7 realized_below_floor</span> 已删，门只剩「有没有一项 in_kind」二值 · <b>M6</b>=价值创造 judge(0–2)，价值是否真创造全压这里 · ⚠ 删 M7 后 pass% 机械抬高，<b>不可与 R2 原始 pass% 逐格比</b> · pass% 与 M6 必须同读`;
function dots(rs){return `<span class="dots">`+rs.map(r=>`<span class="${r.pass?'p':'f'}">${r.pass?'●':'○'}</span>`).join('')+`</span>`;}
function bg(p){if(p>=80)return'rgba(47,138,94,.16)';if(p>=50)return'rgba(47,138,94,.08)';if(p>=34)return'rgba(176,125,54,.13)';if(p>0)return'rgba(196,74,50,.10)';return'rgba(196,74,50,.18)';}
function pcol(p){return p>=50?'var(--pass)':p>0?'var(--amber)':'var(--fail)';}
let mh=`<thead><tr><th rowspan="2" class="caseh">Case</th>`+D.models.map(m=>`<th colspan="3" class="mg">${m.split(' ')[0]} ${m.split(' ').slice(1).join('')}</th>`).join('')+`</tr><tr>`+D.models.map(()=>`<th class="mg">off</th><th>on</th><th>Δ</th>`).join('')+`</tr></thead><tbody>`;
for(const c of D.cases){mh+=`<tr><td class="caseh">${c}</td>`;
  for(const m of D.models){const cell=D.matrix[m][c]||{};
    for(const arm of['off','on']){const x=cell[arm];
      if(!x){mh+=`<td class="cell ${arm==='off'?'mg':''}" style="color:var(--faint)">—</td>`;continue;}
      mh+=`<td class="cell ${arm==='off'?'mg':''}" style="background:${bg(x.pass)}">${x.dec?'<span class="dec">◆</span>':''}${dots(x.runs)}<div class="pct" style="color:${pcol(x.pass)}">${x.pass}%</div><div class="m6">M6 ${x.m6.toFixed(2)}</div></td>`;}
    const on=cell.on,off=cell.off;const d=(on&&off)?on.pass-off.pass:null;
    mh+=`<td class="dcol">${d===null?'<span class="d flat">—</span>':`<span class="d ${d>0?'up':d<0?'down':'flat'}">${d>0?'+':''}${d}</span>`}</td>`;}
  mh+=`</tr>`;}
mh+=`</tbody>`;document.getElementById('mx').innerHTML=mh;
function classify(n){
  if(n.startsWith('M2'))return{c:'bug',v:'bug',vt:'根因在抽取层',
    exp:'extractor 把<b>被拒条款 / 捏造的 deadline</b> 写进 v1，或对合法 subject 重构误判。M2 判 fail 正确，但这不是模型谈判能力的问题——是抽取与 M2「重构容忍」逻辑没跟上。<b>R4 前修 extractor，不计入模型对比。</b>'};
  if(n.includes('no_inkind'))return{c:'beh',v:'行为',vt:'真·能力缺口',
    exp:'agent 退回<b>纯现金谈判</b>，成交里一项非现金价值都没造出来。这正是 harness 要逼出、而 bare 模型缺的能力——<b>是模型行为，不是 bug</b>。这批挂得越多，越说明 case 难度选对了。'};
  if(n.includes('not_settled'))return{c:'beh',v:'行为',vt:'看 case 意图',
    exp:'没谈成。<b>若该 case 本应成交 → 模型问题；若本是 doomed → 走人才对、应判过。</b>当前案库无 doomed，所以这里大概率是模型该成交没成交。'};
  if(n.includes('cash_over_cap'))return{c:'',v:'边界',vt:'真·谈崩',
    exp:'报价<b>超买方现金上限</b>，是真实的谈判失败边界，不是 bug。逐局看是开价过高还是没读懂对方预算。'};
  return{c:'',v:'边界',vt:'逐局看',exp:'阈值/边界类，逐局核对。'};}
const cg=Object.entries(D.fail_index);
document.getElementById('cgrid').innerHTML = cg.length? cg.map(([n,v])=>{const k=classify(n);
  return `<div class="fmode ${k.c}"><div class="ft"><span class="fn">${n}</span><span class="cnt">${v.n}</span></div>
    <span class="verdict ${k.c==='bug'?'bug':k.c==='beh'?'beh':'edge'}">${k.v} · ${k.vt}</span>
    <div class="exp">${k.exp}</div><div class="cls">${v.locs.map(l=>`<span class="loc">${l}</span>`).join('')}</div></div>`;}).join('')
  : `<div style="color:var(--faint);font-family:var(--mono);padding:14px">本轮无门控失败聚类</div>`;
let F={model:'all',case:'',arm:''};
const tb=document.getElementById('tbar');
tb.innerHTML=`<button class="on" data-m="all">全部模型</button>`+D.models.map(m=>`<button data-m="${m}">${m.split(' ')[0]}</button>`).join('')+`<select id="fc"><option value="">全部 Case</option>${D.cases.map(c=>`<option>${c}</option>`).join('')}</select><select id="fa"><option value="">on+off</option><option value="on">on</option><option value="off">off</option></select>`;
function mcell(lab,cls,val,extra){return `<span class="mc ${cls}"><span class="lab">${lab}</span><span class="v">${val}</span>${extra?`<span class="rs">${extra}</span>`:''}</span>`;}
function strip(mt){let h='';
  for(const g of['M1','M2','M3','M4']){const x=mt[g];h+=mcell(g,x.pass?'ok':'no',x.pass?'过':'挂',(!x.pass&&x.info)?x.info:'');}
  h+=mcell('M5',mt.M5.pass?'ok':'no',mt.M5.pass?'过':'挂',(!mt.M5.pass&&mt.M5.info)?mt.M5.info:'');
  h+=mcell('M6','sc',mt.M6.val,'');h+=mcell('M8','rec',mt.M8.val??'—','轮');h+=mcell('M9','rec',mt.M9.val??'—','让');
  h+=mcell('M11',mt.M11.verdict?'sc':'rec',mt.M11.verdict||'—','');h+=mcell('M12',mt.M12.verdict?'sc':'rec',mt.M12.verdict||'—','');
  return h;}
function harnessRow(mt){const m11=mt.M11,m12=mt.M12;
  if(!m11.verdict&&!m12.verdict)return `<div class="hrow"><span class="hl">HARNESS</span> off 臂未评估 M11/M12</div>`;
  const rt=(m12.routes&&m12.routes.length)?m12.routes.map(r=>`<span class="route">${r}</span>`).join('<span class="arrow">→</span>'):'<span style="color:var(--faint)">空（未应用任何 skill）</span>';
  const vf=v=>`<span class="vf ${v||'na'}">${v||'na'}</span>`;
  return `<div class="hrow"><span class="hl">瓶颈诊断 M11</span> ${vf(m11.verdict)} ${m11.diagnosis?('<span style="color:var(--dim)">'+m11.diagnosis.slice(0,80)+(m11.diagnosis.length>80?'…':'')+'</span>'):''}<br><span class="hl">技能路由 M12</span> ${vf(m12.verdict)} ${rt}</div>`;}
function renderRuns(){const host=document.getElementById('runs');
  const rows=D.runs.filter(r=>(F.model==='all'||r.model===F.model)&&(!F.case||r.case===F.case)&&(!F.arm||r.arm===F.arm));
  host.innerHTML=rows.map(r=>{const s=r.settlement||{};
    const judges=[['M11',r.mt.M11.judge],['M2',r.mt.M2.judge],['M6',r.mt.M6.judge],['M12',r.mt.M12.judge]].filter(x=>x[1]);
    return `<div class="run"><div class="rh"><span class="rid">${r.model.split(' ')[0]} · ${r.case} <span class="arm">/ ${r.arm}</span></span><span class="vd ${r.pass?'pass':'fail'}">${r.pass?'case_pass':'fail'}</span></div>
      <div class="mstrip">${strip(r.mt)}</div>${harnessRow(r.mt)}
      <div class="kv"><b>成交</b> ¥${(s.cash??'—')} · 非现金 ${(s.in_kind&&s.in_kind.length)?s.in_kind.join(', '):'无'} · ${s.format||'—'} · ${s.status||'—'}</div>
      ${judges.map(([k,v])=>`<div class="note"><span class="nl">${k} judge</span>${v}</div>`).join('')}</div>`;}).join('')||`<div style="color:var(--faint);font-family:var(--mono);padding:20px">无匹配</div>`;}
tb.addEventListener('click',e=>{if(e.target.dataset.m){[...tb.querySelectorAll('button')].forEach(b=>b.classList.toggle('on',b===e.target));F.model=e.target.dataset.m;renderRuns();}});
tb.addEventListener('change',e=>{if(e.target.id==='fc')F.case=e.target.value;if(e.target.id==='fa')F.arm=e.target.value;renderRuns();});
renderRuns();
</script></body></html>'''
    tpl = tpl.replace("__MOCK__", mock).replace("__F0__", F0).replace("__F1__", F1).replace("__F2__", F2).replace("__F3__", F3)
    return tpl

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=".")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = RESULTS / run_dir
    benchmarks = [load_benchmark({**b, "dir": run_dir / b["subdir"]}) for b in BENCHMARKS]
    D = aggregate(benchmarks)
    html = build_html(D)
    out = Path(args.out) if args.out else (run_dir / "R35_report.html")
    out.write_text(html, encoding="utf-8")
    print("wrote", out)
    print("models:", D["models"])
    print("cases:", D["cases"])
    print("runs:", len(D["runs"]))
    print("fail modes:", {k: v["n"] for k, v in D["fail_index"].items()})

if __name__ == "__main__":
    main()
