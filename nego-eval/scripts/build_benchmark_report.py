#!/usr/bin/env python3
"""Build a standalone HTML report from nego-eval result directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

BENCHMARKS = [
    {
        "id": "deepseek",
        "label": "DeepSeek V4 Flash",
        "model": "deepseek-v4-flash",
        "subdir": "deepseek-r3",
    },
    {
        "id": "glm52",
        "label": "GLM-5.2",
        "model": "glm-5.2",
        "subdir": "glm-5.2-full",
    },
    {
        "id": "kimi",
        "label": "Kimi K2.6",
        "model": "kimi-k2.6",
        "subdir": "kimi-k2.6-full",
    },
]

GATES = ("M1", "M2", "M3", "M4")
METRIC_LABELS = {
    "M1": "结构完整",
    "M2": "忠实表达",
    "M3": "不泄底线",
    "M4": "不乱许诺",
    "M5": "成交结果",
    "M6": "价值创造",
    "M8": "轮次",
    "M9": "让步",
    "M10": "成交条款",
    "M11": "瓶颈诊断",
    "M12": "技能路径",
}


def load_benchmark(bench: dict) -> dict:
    summary_path = bench["dir"] / "_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    runs = []
    for path in sorted(bench["dir"].glob("P*.json")):
        if path.name.endswith(".episode.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        runs.append(data)
    return {**bench, "summary": summary, "runs": runs}


def fmt_settlement(val: dict | None) -> str:
    if not val or not isinstance(val, dict):
        return "—"
    cash = val.get("cash")
    cur = val.get("currency", "CNY")
    ink = ", ".join(val.get("in_kind") or []) or "无"
    fmt = val.get("format") or "—"
    status = val.get("status", "—")
    cash_s = f"¥{cash:,.0f}" if cash is not None else "未定"
    return f"{cash_s} {cur} · 非现金: {ink} · {fmt} · {status}"


def metric_badge(mid: str, m: dict) -> tuple[str, str]:
    kind = m.get("kind", "")
    if mid in GATES or mid == "M5":
        ok = m.get("pass")
        if ok is True:
            return "pass", "过"
        if ok is False:
            return "fail", "挂"
        return "na", "—"
    if mid == "M6":
        v = m.get("value")
        return ("score", str(v)) if v is not None else ("na", "—")
    if mid in ("M11", "M12"):
        v = m.get("verdict", "—")
        cls = "pass" if v in ("full", "pass") else "partial" if v == "partial" else "fail" if v == "fail" else "na"
        return cls, str(v)
    if mid in ("M8", "M9"):
        v = m.get("value")
        return ("na", str(v)) if v is not None else ("na", "—")
    if mid == "M10":
        return "na", "见下"
    return "na", "—"


def extra_detail(mid: str, m: dict) -> str:
    parts = []
    if m.get("reason"):
        parts.append(m["reason"])
    if m.get("hits"):
        parts.append("泄露: " + ", ".join(m["hits"]))
    if m.get("realized_value") is not None and not m.get("pass", True):
        parts.append(f"实现价值 ¥{m['realized_value']:,.0f}")
    if m.get("routes"):
        parts.append("路径: " + " → ".join(m["routes"]))
    if m.get("diagnosis"):
        parts.append(m["diagnosis"])
    if m.get("judge_notes"):
        parts.append(m["judge_notes"])
    return " · ".join(parts) if parts else ""


def build_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>谈判 Agent 评测报告 · DeepSeek / GLM / Kimi</title>
  <style>
    :root {{
      --bg: #f6f4ef;
      --card: #fffdf9;
      --ink: #1c1917;
      --muted: #78716c;
      --line: #e7e5e4;
      --pass: #15803d;
      --pass-bg: #dcfce7;
      --fail: #b91c1c;
      --fail-bg: #fee2e2;
      --partial: #a16207;
      --partial-bg: #fef3c7;
      --accent: #0f766e;
      --accent2: #7c3aed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "SF Pro Text", "PingFang SC", "Helvetica Neue", sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 .25rem; letter-spacing: -.02em; }}
    .sub {{ color: var(--muted); margin-bottom: 2rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 1.1rem 1.25rem;
      box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }}
    .card h2 {{ margin: 0 0 .75rem; font-size: 1.05rem; }}
    .card .model {{ color: var(--muted); font-size: .85rem; margin-bottom: .5rem; }}
    .stat-row {{ display: flex; gap: 1.5rem; flex-wrap: wrap; }}
    .stat {{ }}
    .stat b {{ display: block; font-size: 1.6rem; font-weight: 650; }}
    .stat span {{ font-size: .8rem; color: var(--muted); }}
    .toolbar {{ display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
    .toolbar button, .toolbar select {{
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 999px;
      padding: .4rem .85rem;
      font-size: .85rem;
      cursor: pointer;
    }}
    .toolbar button.active {{ background: var(--ink); color: #fff; border-color: var(--ink); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }}
    th, td {{ padding: .55rem .65rem; text-align: left; border-bottom: 1px solid var(--line); font-size: .82rem; }}
    th {{ background: #f5f5f4; font-weight: 600; position: sticky; top: 0; }}
    tr:last-child td {{ border-bottom: none; }}
    .pill {{
      display: inline-block;
      padding: .12rem .45rem;
      border-radius: 999px;
      font-size: .72rem;
      font-weight: 600;
    }}
    .pill.pass {{ background: var(--pass-bg); color: var(--pass); }}
    .pill.fail {{ background: var(--fail-bg); color: var(--fail); }}
    .pill.partial {{ background: var(--partial-bg); color: var(--partial); }}
    .pill.score {{ background: #e0e7ff; color: #3730a3; }}
    .pill.na {{ background: #f5f5f4; color: var(--muted); }}
    .section {{ margin-top: 2.5rem; }}
    .section h2 {{ font-size: 1.2rem; margin-bottom: 1rem; }}
    .run-grid {{ display: grid; gap: 1rem; }}
    .run {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
    }}
    .run-head {{
      display: flex; justify-content: space-between; align-items: center; gap: 1rem;
      padding: .85rem 1rem; cursor: pointer; user-select: none;
    }}
    .run-head:hover {{ background: #fafaf9; }}
    .run-title {{ font-weight: 650; }}
    .run-meta {{ font-size: .8rem; color: var(--muted); }}
    .run-body {{ display: none; padding: 0 1rem 1rem; border-top: 1px solid var(--line); }}
    .run.open .run-body {{ display: block; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: .5rem; margin: .75rem 0; }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: .45rem .55rem;
      font-size: .78rem;
    }}
    .metric .id {{ font-weight: 650; }}
    .metric .name {{ color: var(--muted); font-size: .72rem; }}
    .settlement {{ font-size: .85rem; background: #f5f5f4; border-radius: 8px; padding: .6rem .75rem; margin: .5rem 0; }}
    .note {{ font-size: .8rem; color: #44403c; margin-top: .35rem; }}
    .verdict-ok {{ color: var(--pass); font-weight: 600; }}
    .verdict-no {{ color: var(--fail); font-weight: 600; }}
    .tag-ds {{ color: var(--accent); }}
    .tag-glm {{ color: var(--accent2); }}
    .tag-kimi {{ color: #c2410c; }}
    @media (max-width: 700px) {{
      th, td {{ font-size: .75rem; padding: .45rem; }}
      .metrics {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>谈判 Agent 评测报告</h1>
    <p class="sub">aux 固定 <strong>qwen3.7-max</strong> · P1–P6 · skills on/off · 各 1 run</p>
    <div class="cards" id="summary-cards"></div>

    <div class="toolbar">
      <button class="active" data-filter="all">全部</button>
      <button data-filter="deepseek">DeepSeek</button>
      <button data-filter="glm52">GLM-5.2</button>
      <button data-filter="kimi">Kimi K2.6</button>
      <select id="case-filter">
        <option value="">全部 Case</option>
      </select>
      <select id="skills-filter">
        <option value="">全部 Skills</option>
        <option value="on">skills on</option>
        <option value="off">skills off</option>
      </select>
    </div>

    <table id="overview">
      <thead>
        <tr>
          <th>Agent</th><th>Case</th><th>Skills</th><th>过关</th><th>成交</th><th>M6</th><th>轮次</th><th>主要失败</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>

    <div class="section">
      <h2>逐局详情</h2>
      <div class="run-grid" id="runs"></div>
    </div>
  </div>
  <script>
    const DATA = {data_json};

    const AGENT_TAG = {{ deepseek: 'tag-ds', glm52: 'tag-glm', kimi: 'tag-kimi' }};
    function agentTag(id) {{ return AGENT_TAG[id] || ''; }}
    const METRIC_LABELS = {json.dumps(METRIC_LABELS, ensure_ascii=False)};
    const GATES = {json.dumps(list(GATES))};

    function summarize(bench) {{
      const runs = bench.runs;
      const passed = runs.filter(r => r.verdict.case_pass).length;
      const settled = runs.filter(r => r.metrics.M8?.value != null).length;
      const m6 = runs.reduce((s, r) => s + (r.metrics.M6?.value ?? 0), 0) / (runs.length || 1);
      return {{ passed, total: runs.length, settled, m6 }};
    }}

    function failReasons(r) {{
      const out = [];
      for (const g of GATES) {{
        if (r.metrics[g] && r.metrics[g].pass === false) out.push(g);
      }}
      if (r.metrics.M5 && !r.metrics.M5.pass && r.metrics.M5.reason) out.push('M5:' + r.metrics.M5.reason);
      return out.join(', ') || '—';
    }}

    function pill(cls, text) {{
      return `<span class="pill ${{cls}}">${{text}}</span>`;
    }}

    function metricCell(mid, m) {{
      if (!m) return pill('na', '—');
      if (GATES.includes(mid) || mid === 'M5') return pill(m.pass ? 'pass' : 'fail', m.pass ? '过' : '挂');
      if (mid === 'M6') return pill('score', String(m.value ?? '—'));
      if (mid === 'M11' || mid === 'M12') {{
        const v = m.verdict || '—';
        const cls = v === 'full' || v === 'pass' ? 'pass' : v === 'partial' ? 'partial' : v === 'fail' ? 'fail' : 'na';
        return pill(cls, v);
      }}
      if (mid === 'M8' || mid === 'M9') return pill('na', String(m.value ?? '—'));
      return pill('na', '—');
    }}

    function fmtSettlement(v) {{
      if (!v) return '—';
      const cash = v.cash != null ? `¥${{Number(v.cash).toLocaleString()}}` : '未定';
      const ink = (v.in_kind && v.in_kind.length) ? v.in_kind.join(', ') : '无';
      return `${{cash}} ${{v.currency || 'CNY'}} · 非现金: ${{ink}} · ${{v.format || '—'}} · ${{v.status || '—'}}`;
    }}

    function renderCards() {{
      const el = document.getElementById('summary-cards');
      el.innerHTML = DATA.benchmarks.map(b => {{
        const s = summarize(b);
        const tag = agentTag(b.id);
        return `<div class="card">
          <h2 class="${{tag}}">${{b.label}}</h2>
          <div class="model">${{b.model}}</div>
          <div class="stat-row">
            <div class="stat"><b>${{s.passed}}/${{s.total}}</b><span>全过关</span></div>
            <div class="stat"><b>${{s.settled}}</b><span>成交局数</span></div>
            <div class="stat"><b>${{s.m6.toFixed(2)}}</b><span>M6 均值</span></div>
          </div>
        </div>`;
      }}).join('');
    }}

    function renderOverview(filter) {{
      const tbody = document.querySelector('#overview tbody');
      const caseF = document.getElementById('case-filter').value;
      const skillsF = document.getElementById('skills-filter').value;
      const rows = [];
      for (const b of DATA.benchmarks) {{
        if (filter !== 'all' && b.id !== filter) continue;
        for (const r of b.runs) {{
          if (caseF && r.case_id !== caseF) continue;
          if (skillsF && r.config.skills !== skillsF) continue;
          const settled = r.metrics.M8?.value != null;
          rows.push(`<tr>
            <td class="${{agentTag(b.id)}}">${{b.label}}</td>
            <td>${{r.case_id}}</td>
            <td>${{r.config.skills}}</td>
            <td>${{r.verdict.case_pass ? pill('pass','YES') : pill('fail','NO')}}</td>
            <td>${{settled ? pill('pass','成交') : pill('fail','未成交')}}</td>
            <td>${{pill('score', String(r.metrics.M6?.value ?? '—'))}}</td>
            <td>${{r.metrics.M8?.value ?? '—'}}</td>
            <td style="max-width:220px">${{failReasons(r)}}</td>
          </tr>`);
        }}
      }}
      tbody.innerHTML = rows.join('');
    }}

    function extraDetail(mid, m) {{
      const p = [];
      if (m.reason) p.push(m.reason);
      if (m.hits) p.push('泄露: ' + m.hits.join(', '));
      if (m.realized_value != null && m.pass === false) p.push(`实现价值 ¥${{m.realized_value}}`);
      if (m.routes) p.push('路径: ' + m.routes.join(' → '));
      if (m.diagnosis) p.push(m.diagnosis);
      if (m.judge_notes) p.push(m.judge_notes);
      return p.join(' · ');
    }}

    function renderRuns(filter) {{
      const el = document.getElementById('runs');
      const caseF = document.getElementById('case-filter').value;
      const skillsF = document.getElementById('skills-filter').value;
      const html = [];
      for (const b of DATA.benchmarks) {{
        if (filter !== 'all' && b.id !== filter) continue;
        for (const r of b.runs) {{
          if (caseF && r.case_id !== caseF) continue;
          if (skillsF && r.config.skills !== skillsF) continue;
          const mids = Object.keys(r.metrics).sort();
          const metricsHtml = mids.map(mid => {{
            const m = r.metrics[mid];
            return `<div class="metric">
              <div class="id">${{mid}} ${{metricCell(mid, m)}}</div>
              <div class="name">${{METRIC_LABELS[mid] || ''}}</div>
              ${{extraDetail(mid, m) ? `<div class="note">${{extraDetail(mid, m)}}</div>` : ''}}
            </div>`;
          }}).join('');
          const vCls = r.verdict.case_pass ? 'verdict-ok' : 'verdict-no';
          html.push(`<div class="run">
            <div class="run-head" onclick="this.parentElement.classList.toggle('open')">
              <div>
                <div class="run-title"><span class="${{agentTag(b.id)}}">${{b.label}}</span> · ${{r.case_id}} · skills ${{r.config.skills}}</div>
                <div class="run-meta">gates=${{r.verdict.gates_pass}} outcome=${{r.verdict.outcome_pass}} · quality ${{r.verdict.quality}}</div>
              </div>
              <div class="${{vCls}}">${{r.verdict.case_pass ? 'PASS' : 'FAIL'}}</div>
            </div>
            <div class="run-body">
              <div class="settlement">${{fmtSettlement(r.metrics.M10?.value)}}</div>
              <div class="metrics">${{metricsHtml}}</div>
            </div>
          </div>`);
        }}
      }}
      el.innerHTML = html.join('');
    }}

    function initFilters() {{
      const cases = [...new Set(DATA.benchmarks.flatMap(b => b.runs.map(r => r.case_id)))].sort();
      const sel = document.getElementById('case-filter');
      cases.forEach(c => {{
        const o = document.createElement('option');
        o.value = c; o.textContent = c;
        sel.appendChild(o);
      }});
      let current = 'all';
      const refresh = () => {{ renderOverview(current); renderRuns(current); }};
      document.querySelectorAll('.toolbar button[data-filter]').forEach(btn => {{
        btn.addEventListener('click', () => {{
          document.querySelectorAll('.toolbar button[data-filter]').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          current = btn.dataset.filter;
          refresh();
        }});
      }});
      document.getElementById('case-filter').addEventListener('change', refresh);
      document.getElementById('skills-filter').addEventListener('change', refresh);
    }}

    renderCards();
    initFilters();
    renderOverview('all');
    renderRuns('all');
  </script>
</body>
</html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Build benchmark HTML report")
    p.add_argument(
        "--run-dir",
        default=None,
        help="session directory under results/ (e.g. 20260624T120000Z) or absolute path",
    )
    args = p.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = RESULTS / run_dir
    else:
        # Default: newest timestamped session directory.
        candidates = sorted(
            (d for d in RESULTS.iterdir() if d.is_dir() and d.name[:8].isdigit()),
            key=lambda d: d.name,
            reverse=True,
        )
        if not candidates:
            raise SystemExit(f"no result sessions under {RESULTS}")
        run_dir = candidates[0]

    out_path = run_dir / "benchmark-report.html"
    benchmarks = [
        {**b, "dir": run_dir / b["subdir"]} for b in BENCHMARKS
    ]
    benchmarks = [load_benchmark(b) for b in benchmarks]
    # Strip Path objects for JSON
    payload = {
        "aux": "qwen3.7-max",
        "run_dir": str(run_dir),
        "benchmarks": [
            {
                "id": b["id"],
                "label": b["label"],
                "model": b["model"],
                "summary": b["summary"],
                "runs": b["runs"],
            }
            for b in benchmarks
        ],
    }
    html = build_html(payload)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
