"""Standalone Chinese HTML reports for A2 phases."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

from .models import A2EpisodeRecord


_STYLE = """
:root{--bg:#f5f7fb;--paper:#fff;--ink:#172033;--muted:#66738a;--line:#dce3ee;
--violet:#6846c7;--soft:#f0eaff;--green:#14734a;--greenbg:#e4f7ed;
--red:#a92f3e;--redbg:#ffebee;--amber:#986000;--amberbg:#fff4d9}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f1ebff,#f5f7fb 360px);
color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
"Microsoft YaHei",sans-serif}.wrap{width:min(1180px,calc(100% - 34px));margin:auto}
header{padding:46px 0 30px}h1{font-size:clamp(30px,5vw,52px);line-height:1.08;margin:0}
.lede{color:var(--muted);font-size:17px;max-width:850px}.pill{display:inline-block;padding:4px 9px;
border-radius:999px;font-size:12px;font-weight:800}.ok{background:var(--greenbg);color:var(--green)}
.bad{background:var(--redbg);color:var(--red)}.warn{background:var(--amberbg);color:var(--amber)}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card,section{background:var(--paper);
border:1px solid var(--line);border-radius:16px;padding:19px;box-shadow:0 10px 28px rgba(34,50,84,.07)}
.card h3{margin:0 0 12px}.big{font-size:28px;font-weight:800}.muted{color:var(--muted)}
section{margin:18px 0}h2{margin:0 0 14px}.table{overflow:auto;border:1px solid var(--line);
border-radius:12px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:10px 12px;
border-bottom:1px solid var(--line);text-align:left;font-size:13px;vertical-align:top}th{background:#f3f0fa}
tr:last-child td{border-bottom:0}code{background:#eef1f6;padding:2px 5px;border-radius:5px}
details{border-top:1px solid var(--line);padding:10px 0}details:first-child{border-top:0}
summary{cursor:pointer;font-weight:700}pre{white-space:pre-wrap;background:#182033;color:#eef2ff;
padding:13px;border-radius:10px;max-height:480px;overflow:auto;font-size:12px}
.gate{padding:14px;border-left:4px solid var(--violet);background:var(--soft);border-radius:9px}
footer{padding:25px 0 45px;color:var(--muted);font-size:12px}
.mx{display:grid;grid-template-columns:auto 1fr 1fr;gap:1px;background:var(--line);
border:1px solid var(--line);border-radius:12px;overflow:hidden;max-width:660px;margin:14px 0}
.mx>div{background:var(--paper);padding:13px 15px}.mx .hd{background:#f3f0fa;font-size:12px;
font-weight:800;color:var(--muted);display:flex;align-items:center}
.mx .arm{font-size:21px;font-weight:800;color:var(--violet);letter-spacing:.04em}
.mx .arm.sym{color:var(--muted)}.mx .d{font-size:12.5px;color:var(--muted);line-height:1.55}
.note{border-left:4px solid var(--amber);background:var(--amberbg);padding:12px 15px;
border-radius:0 9px 9px 0;margin:13px 0;font-size:13.5px}
.note b{display:block;font-size:11px;letter-spacing:.1em;text-transform:uppercase;
color:var(--amber);margin-bottom:5px}
.flag{border-left:4px solid var(--red);background:var(--redbg);padding:12px 15px;
border-radius:0 9px 9px 0;margin:13px 0;font-size:13.5px}
.flag b{display:block;font-size:11px;letter-spacing:.1em;text-transform:uppercase;
color:var(--red);margin-bottom:5px}
.sig{color:var(--green);font-weight:800}.nsig{color:var(--muted)}
dl.terms{margin:0;display:grid;grid-template-columns:auto 1fr;gap:7px 16px;font-size:13.5px}
dl.terms dt{font-weight:800;white-space:nowrap}dl.terms dd{margin:0;color:var(--muted)}
@media(max-width:850px){.cards{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){
.cards{grid-template-columns:1fr}.mx{grid-template-columns:1fr}
dl.terms{grid-template-columns:1fr}.wrap{width:calc(100% - 22px)}}
"""


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _money(value: Any) -> str:
    if value is None:
        return "—"
    return f"¥{float(value):,.0f}"


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def _representative_records(
    records: List[A2EpisodeRecord], limit: int = 12
) -> List[A2EpisodeRecord]:
    """Select every case first, then add deterministic anomaly examples."""

    def priority(record: A2EpisodeRecord):
        return (
            0 if not record.valid else 1,
            0 if record.a2_metrics.get("condition_disagreement") else 1,
            {"walk_away": 0, "round_cap": 1, "settled": 2}.get(
                record.episode.terminal_reason, 3
            ),
            record.arm,
            record.replicate,
        )

    ordered = sorted(records, key=lambda item: (item.case_id, priority(item)))
    selected: List[A2EpisodeRecord] = []
    seen_cases = set()
    for record in ordered:
        if record.case_id not in seen_cases:
            selected.append(record)
            seen_cases.add(record.case_id)
    selected_ids = {id(record) for record in selected}
    for record in sorted(records, key=priority):
        if len(selected) >= limit:
            break
        if id(record) not in selected_ids:
            selected.append(record)
            selected_ids.add(id(record))
    return selected[:limit]


def write_preflight_report(payload: Dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    checks = payload.get("checks", [])
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('name', '')))}</td>"
        f"<td><span class='pill {'ok' if item.get('ok') else 'bad'}'>"
        f"{'通过' if item.get('ok') else '阻塞'}</span></td>"
        f"<td>{html.escape(str(item.get('detail', '')))}</td>"
        "</tr>"
        for item in checks
    )
    status = "通过" if payload.get("ok") else "阻塞"
    status_class = "ok" if payload.get("ok") else "bad"
    body = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A2 Phase 0 · Preflight</title><style>{_STYLE}</style></head><body>
<header class="wrap"><span class="pill {status_class}">Phase 0 {status}</span>
<h1>A2 环境与契约预检</h1>
<p class="lede">双 Broker 消融在发出任何正式实验请求前验证模型、凭据、配置、测试和隔离边界。</p></header>
<main class="wrap"><section><h2>检查结果</h2><div class="table"><table>
<thead><tr><th>检查</th><th>状态</th><th>证据</th></tr></thead><tbody>{rows}</tbody>
</table></div></section>
<section><h2>Provenance</h2><pre>{html.escape(json.dumps(payload.get('provenance', {}), ensure_ascii=False, indent=2))}</pre></section>
</main><footer class="wrap">run_id: {html.escape(str(payload.get('run_id','')))}</footer>
</body></html>"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def write_stage_report(
    *,
    stage: str,
    run_id: str,
    analysis: Dict[str, Any],
    records: List[A2EpisodeRecord],
    path: str | Path,
    gates: Dict[str, Any],
) -> Path:
    target = Path(path)
    arm_cards = []
    for arm, summary in analysis.get("arms", {}).items():
        arm_cards.append(
            f"""<article class="card"><h3>{arm}</h3>
<div class="big">{_fmt((summary.get('settlement_rate') or 0)*100,0)}%</div>
<div class="muted">成交率 · {summary.get('settled',0)}/{summary.get('valid',0)}</div>
<p>现金中位数：<b>{_money(summary.get('cash_median'))}</b><br>
买方剩余：<b>{_fmt(summary.get('buyer_surplus_mean'))}</b><br>
条件优势：<b>{_fmt(summary.get('condition_consensus_mean'))}</b><br>
质量均值：<b>{_fmt(summary.get('quality_mean'))}</b></p></article>"""
        )

    contrast_rows = []
    for metric, comparisons in analysis.get("contrasts", {}).items():
        for name, result in comparisons.items():
            ci = result.get("ci95") or [None, None]
            contrast_rows.append(
                "<tr>"
                f"<td>{html.escape(metric)}</td><td>{html.escape(name)}</td>"
                f"<td>{_fmt(result.get('effect'),3)}</td>"
                f"<td>[{_fmt(ci[0],3)}, {_fmt(ci[1],3)}]</td>"
                f"<td>{result.get('n_cases',0)}</td></tr>"
            )

    quality_rows = []
    efficiency_rows = []
    price_rows = []
    condition_rows = []
    dimension_labels = {
        "deliverables": "交付物",
        "payment_and_acceptance": "付款与验收",
        "timing": "时间/期限",
        "rights_and_authorization": "权利与授权",
        "obligations_and_risk": "义务与风险",
        "cancellation": "取消/退出",
        "in_kind": "非现金对价",
    }
    for arm, summary in analysis.get("arms", {}).items():
        quality_rows.append(
            "<tr>"
            f"<td>{arm}</td>"
            + "".join(
                f"<td>{_percent(summary.get(f'M{metric}_pass_rate'))}</td>"
                for metric in range(1, 6)
            )
            + f"<td>{_fmt(summary.get('M6_mean'))}</td></tr>"
        )
        efficiency_rows.append(
            "<tr>"
            f"<td>{arm}</td><td>{summary.get('valid', 0)}/{summary.get('expected', 0)}</td>"
            f"<td>{summary.get('settled', 0)} / {summary.get('walk_away', 0)} / {summary.get('round_cap', 0)}</td>"
            f"<td>{_fmt(summary.get('rounds_mean'))}</td>"
            f"<td>{_fmt(summary.get('buyer_concession_moves_mean'))}</td>"
            f"<td>{_fmt(summary.get('seller_concession_moves_mean'))}</td>"
            f"<td>{_fmt(summary.get('estimated_input_tokens_mean'), 0)}</td>"
            f"<td>{_fmt(summary.get('estimated_output_tokens_mean'), 0)}</td>"
            f"<td>{_fmt(summary.get('latency_seconds_mean'), 1)}s</td></tr>"
        )
        price_rows.append(
            "<tr>"
            f"<td>{arm}</td><td>{summary.get('cash_n', 0)}</td>"
            f"<td>{_money(summary.get('cash_min'))}</td>"
            f"<td>{_money(summary.get('cash_q25'))}</td>"
            f"<td>{_money(summary.get('cash_median'))}</td>"
            f"<td>{_money(summary.get('cash_q75'))}</td>"
            f"<td>{_money(summary.get('cash_max'))}</td></tr>"
        )
        for dimension, payload in summary.get(
            "condition_dimensions", {}
        ).items():
            condition_rows.append(
                "<tr>"
                f"<td>{arm}</td><td>{html.escape(dimension_labels.get(dimension, dimension))}</td>"
                f"<td>{_fmt(payload.get('mean'))}</td>"
                f"<td>{payload.get('n_consensus', 0)}</td>"
                f"<td>{payload.get('disagreements', 0)}</td></tr>"
            )

    transcript_rows = []
    for record in _representative_records(records):
        transcript = "\n\n".join(
            f"R{turn.round} {turn.speaker}: {turn.message}"
            for turn in record.episode.transcript
        )
        transcript_rows.append(
            f"""<details><summary>{record.case_id} · {record.arm} · r{record.replicate}
 · {record.episode.terminal_reason}</summary>
<p>cash={_money(record.a2_metrics.get('cash'))} ·
 condition={_fmt(record.a2_metrics.get('condition_consensus'))} ·
 valid={record.valid}</p><pre>{html.escape(transcript)}</pre></details>"""
        )

    gate_rows = "".join(
        f"<li><span class='pill {'ok' if value else 'bad'}'>{'通过' if value else '未通过'}</span> "
        f"{html.escape(name)}</li>"
        for name, value in gates.items()
    )

    def _ci(result: Dict[str, Any], digits: int = 3, scale: float = 1.0) -> str:
        """Render an effect + CI, marking whether the interval excludes zero."""
        low, high = (result.get("ci95") or [None, None])
        effect = result.get("effect")
        if effect is None:
            return "<td colspan='2' class='muted'>无配对样本</td>"
        excludes_zero = (
            low is not None and high is not None and (low > 0 or high < 0)
        )
        cls = "sig" if excludes_zero else "nsig"
        return (
            f"<td class='{cls}'>{_fmt(effect * scale, digits)}</td>"
            f"<td class='{cls}'>[{_fmt(low * scale, digits)}, {_fmt(high * scale, digits)}]"
            f"{' ✓' if excludes_zero else ''}</td>"
        )

    metric_labels = {
        "settled": "成交率",
        "walk_away": "谈崩率",
        "round_cap": "超时未决率",
        "M6": "M6 均值",
    }

    seat_rows = []
    for metric, per_seat in analysis.get("seat_contrasts", {}).items():
        for name, result in per_seat.items():
            seat = "卖方座位" if name.startswith("seller") else "买方座位"
            scale = 100.0 if metric != "M6" else 1.0
            seat_rows.append(
                f"<tr><td>{seat}</td><td>{metric_labels.get(metric, metric)}</td>"
                + _ci(result, 1 if metric != "M6" else 3, scale)
                + f"<td>{result.get('n_cases', 0)}</td></tr>"
            )

    pairwise_rows = []
    for metric, comparisons in analysis.get("pairwise_contrasts", {}).items():
        scale = 100.0 if metric != "M6" else 1.0
        for name, result in comparisons.items():
            pairwise_rows.append(
                f"<tr><td>{metric_labels.get(metric, metric)}</td>"
                f"<td>{html.escape(name.replace('_minus_', ' − '))}</td>"
                + _ci(result, 1 if metric != "M6" else 3, scale)
                + f"<td>{result.get('n_cases', 0)}</td></tr>"
            )

    terminal_labels = {
        "settled": "成交",
        "walk_away": "谈崩",
        "round_cap": "超时未决",
    }
    m6_terminal_rows = []
    for reason, payload in analysis.get("m6_by_terminal", {}).items():
        distribution = payload.get("distribution", {})
        m6_terminal_rows.append(
            f"<tr><td>{terminal_labels.get(reason, reason)}</td>"
            f"<td>{payload.get('n', 0)}</td>"
            + "".join(
                f"<td>{distribution.get(str(tier), 0)}</td>" for tier in range(5)
            )
            + f"<td><b>{_fmt(payload.get('mean'))}</b></td></tr>"
        )

    settled_m6_rows = []
    unconditional = analysis.get("pairwise_contrasts", {}).get("M6", {})
    for name, result in analysis.get("settled_only_m6_contrasts", {}).items():
        raw = unconditional.get(name, {})
        settled_m6_rows.append(
            f"<tr><td>{html.escape(name.replace('_minus_', ' − '))}</td>"
            f"<td>{_fmt(raw.get('effect'))}</td>"
            + _ci(result)
            + f"<td>{result.get('n_cases', 0)}</td></tr>"
        )

    coverage_labels = {
        "cash": "成交现金价",
        "buyer_surplus_share": "买方剩余占比",
        "condition_consensus": "条件优势（双盲一致）",
    }
    coverage_rows = []
    for metric, payload in analysis.get("metric_coverage", {}).items():
        case_ids = payload.get("case_ids") or []
        coverage_rows.append(
            f"<tr><td>{coverage_labels.get(metric, metric)}</td>"
            f"<td>{payload.get('episodes',0)}/{payload.get('episodes_total',0)}</td>"
            f"<td>{_percent(payload.get('coverage'))}</td>"
            f"<td>{payload.get('cases',0)}</td>"
            f"<td class='muted'>{html.escape('、'.join(case_ids)) or '—'}</td></tr>"
        )

    cash_robust = analysis.get("cash_robustness", {}) or {}
    loo_rows = []
    for name, payload in (cash_robust.get("leave_one_out") or {}).items():
        effect = payload.get("effect")
        dropping = payload.get("dropping") or {}
        if not dropping or effect in (None, 0):
            continue
        worst_case, worst_value = min(
            dropping.items(), key=lambda item: abs(item[1] or 0)
        )
        share = 1 - abs((worst_value or 0) / effect) if effect else None
        loo_rows.append(
            f"<tr><td>{html.escape(name.replace('_minus_', ' − '))}</td>"
            f"<td>{_money(effect)}</td>"
            f"<td>{html.escape(worst_case)}</td>"
            f"<td>{_money(worst_value)}</td>"
            f"<td><b>{_percent(share)}</b></td></tr>"
        )

    normalized_rows = []
    for case_id, payload in (cash_robust.get("normalized") or {}).items():
        ratios = payload.get("ratios") or {}
        normalized_rows.append(
            f"<tr><td>{html.escape(case_id)}</td><td>{_money(payload.get('base'))}</td>"
            + "".join(
                f"<td>{_fmt(ratios[arm], 2) if ratios.get(arm) is not None else '—'}</td>"
                for arm in ("GG", "QG", "GQ", "QQ")
            )
            + "</tr>"
        )

    agreement = analysis.get("condition_agreement", {}) or {}
    agreement_rows = "".join(
        f"<tr><td>{html.escape(dimension_labels.get(dimension, dimension))}</td>"
        f"<td>{payload.get('n',0)}</td><td>{_percent(payload.get('agreement'))}</td></tr>"
        for dimension, payload in (agreement.get("by_dimension") or {}).items()
    )
    body = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A2 Phase {html.escape(stage)} report</title><style>{_STYLE}</style></head><body>
<header class="wrap"><span class="pill {'ok' if all(gates.values()) else 'warn'}">
Phase {html.escape(stage)}</span><h1>A2 模型能力不对称消融</h1>
<p class="lede">双 Broker、四模型臂、clean prompt。价格仅在成交局比较；条件分由 GLM 与 Qwen 盲审方向一致时计入。</p></header>
<main class="wrap">
<section><h2>实验设置与术语（先读这一节）</h2>
<p>本实验让<b>两个经纪人 agent 直接对谈</b>——一个代表买方、一个代表卖方，中间没有模拟器、没有陪练。
每一方只看得到自己委托人的私有信息（目标、底线、必须项、红线），看不到对方的。
唯一被操纵的变量是：<b>这两个座位上分别放哪个模型</b>。</p>
<h3>四个臂的名字怎么读</h3>
<p>臂名是两个字母：<b>第一个字母 = 买方经纪人用的模型，第二个字母 = 卖方经纪人用的模型。</b>
<code>G</code> = GLM-5.2（较强），<code>Q</code> = Qwen3.6-27B（较弱）。所以 <code>GQ</code> = 买方 GLM、卖方 Qwen。</p>
<div class="mx">
<div class="hd"></div><div class="hd">卖方经纪人 = G</div><div class="hd">卖方经纪人 = Q</div>
<div class="hd">买方经纪人 = G</div>
<div><div class="arm sym">GG</div><div class="d">双方都是 GLM。<b>等强基线</b>——任何差异都不来自模型。</div></div>
<div><div class="arm">GQ</div><div class="d">强买方 vs 弱卖方。若"强模型谈判更强"成立，买方应占便宜。</div></div>
<div class="hd">买方经纪人 = Q</div>
<div><div class="arm">QG</div><div class="d">弱买方 vs 强卖方。GQ 的镜像，卖方应占便宜。</div></div>
<div><div class="arm sym">QQ</div><div class="d">双方都是 Qwen。<b>第二条等强基线</b>，与 GG 构成能力档位对照。</div></div>
</div>
<p><b>GQ 与 QG 是一对镜像</b>（把"哪一侧更强"翻转过来）；<b>GG 与 QQ 是两条等强基线</b>（把"两侧一样强"钉在高低两个档位）。
所以三个核心问题是：不对称有没有方向性（GQ vs QG）、异质配对是否不同于同质配对（vs equal）、以及纯能力档位效应（QQ vs GG）。</p>
<h3>术语表</h3>
<dl class="terms">
<dt>臂 / arm</dt><dd>一种实验条件。这里就是四种模型配对之一。</dd>
<dt>座位 / seat</dt><dd>买方或卖方这个位置。"卖方座位 Q−G" = 把卖方换成 Qwen 相对换成 GLM 的差别，买方那侧被平均掉。</dd>
<dt>equal 基线</dt><dd>同一个 case 上 GG 与 QQ 的均值，代表"两侧等强"的参照点。</dd>
<dt>配对 / paired</dt><dd>比较只在<b>同一个 case 内部</b>做，再跨 case 汇总。不同 case 的难度和金额尺度差异极大，直接平均会把效应稀释成噪声。</dd>
<dt>95% CI</dt><dd>按 <b>case 聚类</b>重抽样得到的区间。<b>区间不含 0（标 ✓）才算测到了效应</b>；含 0 就是"没测出来"，不等于"没有"。</dd>
<dt>成交 / 谈崩 / 超时未决</dt><dd>三种结局，由<b>盲态裁判</b>只看公开对话判定（它不知道哪个模型在说话）。谈崩=有一方明确终止；超时未决=打满回合仍无结论。三者分开统计，未成交不记作零价。</dd>
<dt>M1–M6</dt><dd>主评测的指标：M1 结构完整、M2 忠实表达、M3 不泄底线、M4 不越权、M5 成交结果、M6 deal 水准（0=floor 1=crude 2=sound 3=sharp 4=brilliant）。</dd>
<dt>买方剩余占比</dt><dd>成交价在"卖方底线↔买方上限"这段区间里的位置，用来跨 case 归一化"谁占了便宜"。需要 case 同时定义了底线和上限。</dd>
</dl>
<div class="note"><b>读这份报告的顺序</b>
先看「运行完整性」确认数据可用，再看「座位对比」和「两两臂对比」——那里才是能归因到模型的读数。
上方四张卡片和「现金价格分布」是<b>描述性</b>的：它们跨 case 混合了不同难度与不同金额尺度，
不能直接当作模型效应来读（见下方「现金效应稳健性」一节）。</div>
</section>
<div class="cards">{''.join(arm_cards)}</div>
<section><h2>运行完整性</h2><p class="gate">预期 {analysis.get('expected_episodes',0)} ·
写入 {analysis.get('written_episodes',0)} · 有效 {analysis.get('valid_episodes',0)} ·
完成率 {_fmt(analysis.get('completion_rate',0)*100,1)}% ·
arm invalid gap {_fmt(analysis.get('arm_invalid_rate_gap'),3)}</p><ul>{gate_rows}</ul></section>
<section><h2>M1–M6 验收指标</h2><div class="table"><table><thead>
<tr><th>Arm</th><th>M1</th><th>M2</th><th>M3</th><th>M4</th><th>M5</th><th>M6 均值</th></tr>
</thead><tbody>{''.join(quality_rows)}</tbody></table></div></section>
<section><h2>现金价格分布（仅成交且有明确现金价）</h2>
<p class="muted">跨 case 的原始金额尺度不同，本表仅描述分布；模型角色效应应优先读取下方相同 case 的聚类对比。</p>
<div class="table"><table><thead>
<tr><th>Arm</th><th>N</th><th>Min</th><th>P25</th><th>Median</th><th>P75</th><th>Max</th></tr>
</thead><tbody>{''.join(price_rows)}</tbody></table></div></section>
<section><h2>非现金条件分项（买方视角）</h2>
<p class="muted">分值 -2…2；只有 GLM 与 Qwen 对方向一致时才进入均值。分歧单列，不强行合并。</p>
<div class="table"><table><thead>
<tr><th>Arm</th><th>维度</th><th>一致样本均值</th><th>一致 N</th><th>方向分歧</th></tr>
</thead><tbody>{''.join(condition_rows)}</tbody></table></div></section>
<section><h2>过程、让步与成本</h2><div class="table"><table><thead>
<tr><th>Arm</th><th>有效/预期</th><th>成交/退出/轮次上限</th><th>平均轮数</th>
<th>买方现金让步次数</th><th>卖方现金让步次数</th><th>估算输入 token</th>
<th>估算输出 token</th><th>平均延迟</th></tr>
</thead><tbody>{''.join(efficiency_rows)}</tbody></table></div></section>
<section><h2>Case-level 对比（预注册的三个）</h2><div class="table"><table><thead>
<tr><th>指标</th><th>对比</th><th>效应</th><th>95% CI</th><th>Case 数</th></tr>
</thead><tbody>{''.join(contrast_rows)}</tbody></table></div>
<p class="muted">注意 <code>*_minus_equal</code> 是与 GG/QQ 均值比较：它平均了两条各自带噪的基线，
可能在两两直比都不显著时达到显著。两种读数都在下面列出。</p></section>
<section><h2>座位对比：把"哪个模型坐这里"和"哪一对在打"分开</h2>
<p class="muted">同一个 case 内，把共用该座位模型的两个臂合并，再取 Q 减 G。
这是四臂表看不出来的读数——它回答"换掉卖方的模型会怎样"，而不是"GQ 和 QG 谁强"。</p>
<div class="table"><table><thead>
<tr><th>座位</th><th>指标</th><th>Q − G</th><th>95% CI</th><th>Case 数</th></tr>
</thead><tbody>{''.join(seat_rows)}</tbody></table></div></section>
<section><h2>两两臂对比（全部六对）</h2>
<p class="muted">百分点单位；M6 为原始档位。CI 不含 0 的行标 ✓。</p>
<div class="table"><table><thead>
<tr><th>指标</th><th>对比</th><th>效应</th><th>95% CI</th><th>Case 数</th></tr>
</thead><tbody>{''.join(pairwise_rows)}</tbody></table></div></section>
<section><h2>诊断：M6 在测 deal，还是在测结局？</h2>
<div class="table"><table><thead>
<tr><th>结局</th><th>N</th><th>floor(0)</th><th>crude(1)</th><th>sound(2)</th><th>sharp(3)</th>
<th>brilliant(4)</th><th>M6 均值</th></tr>
</thead><tbody>{''.join(m6_terminal_rows)}</tbody></table></div>
<div class="flag"><b>已知测量缺陷</b>
谈崩局被判 0–1 分，但<b>超时未决局被判 2–3 分</b>——一场打满回合、什么都没谈成的对局，
评级可以高于一场谈崩的。于是臂级 M6 均值主要在反映<b>谁谈崩得多</b>，而不是 deal 好不好。
修法二选一：① 超时未决局不评 M6（记 n/a）；② 与谈崩一样封顶到 floor/crude。
<b>在修好之前，臂级 M6 均值不可用于结论</b>，请只读下表的成交局口径。</div>
<h3>只看成交局的 M6（去掉结局带来的机械差异）</h3>
<div class="table"><table><thead>
<tr><th>对比</th><th>全部局 M6 差</th><th>仅成交局 M6 差</th><th>95% CI</th><th>Case 数</th></tr>
</thead><tbody>{''.join(settled_m6_rows)}</tbody></table></div></section>
<section><h2>指标覆盖率：哪些结论其实只建立在几个 case 上</h2>
<p class="muted">case 级指标需要成交、且 case 提供了必要字段。覆盖率低的指标，其对比的 Case 数也低，
不能与覆盖率高的指标同等看待。</p>
<div class="table"><table><thead>
<tr><th>指标</th><th>可用局</th><th>覆盖率</th><th>可用 case 数</th><th>涉及 case</th></tr>
</thead><tbody>{''.join(coverage_rows)}</tbody></table></div></section>
<section><h2>现金效应稳健性：那个"有 Qwen 就价格不同"是真的吗？</h2>
<p>四臂的现金<b>中位数</b>看起来按卖方座位分成两组（GLM 卖方 ≈ 6k，Qwen 卖方 ≈ 62k，差约十倍）。
但这个差距经不起两项检验。</p>
<h3>检验一：留一法——效应是不是来自单个 case</h3>
<div class="table"><table><thead>
<tr><th>对比</th><th>全量效应</th><th>最关键的 case</th><th>去掉它之后</th><th>该 case 贡献占比</th></tr>
</thead><tbody>{''.join(loo_rows) or '<tr><td colspan="5" class="muted">无可用配对</td></tr>'}</tbody></table></div>
<h3>检验二：同 case 内归一化——四臂真的成交在不同价位吗</h3>
<p class="muted">每一臂的成交价除以该 case 四臂均值。比值都接近 1.00，说明四臂在同一个 case 上谈出的价格几乎一样。</p>
<div class="table"><table><thead>
<tr><th>Case</th><th>该 case 均价</th><th>GG</th><th>QG</th><th>GQ</th><th>QQ</th></tr>
</thead><tbody>{''.join(normalized_rows) or '<tr><td colspan="6" class="muted">无成交现金价</td></tr>'}</tbody></table></div>
<div class="flag"><b>结论：这是两层假象叠加，不是价格行为差异</b>
<b>① 尺度未归一化。</b>案例金额跨 ¥1,500 到 ¥1,700,000 三个数量级，"每 case 差值的均值"会被金额最大的那个 case 支配。
留一法显示效应几乎由单个 case 承担。<br>
<b>② 幸存者偏差。</b>Qwen 坐卖方时更容易谈崩，而它谈崩的恰好是便宜、难谈的那些 case
（如 R4P2 ≈ ¥2,000）。这些低价观测因此<b>从 Qwen 卖方臂的样本里消失了</b>，
剩下的自然偏贵——中位数被抬高的原因是"少了哪些局"，不是"谈出了什么价"。<br>
换句话说：<b>现金中位数的差异是谈崩率的影子。</b>要读价格效应，只能读上面的同 case 归一化表，
或等 case bank 补齐底线/上限后改用买方剩余占比。</div></section>
<section><h2>诊断：条件评分的双盲一致率</h2>
<p class="muted">条件分由 GLM 与 Qwen 各盲评一次，只有方向一致时才进入均值。
下表是它们连<b>符号</b>都能对上的比例——这决定了上面「非现金条件分项」能承载多少解释。</p>
<p class="gate">维度项一致率 <b>{_percent((analysis.get('condition_agreement') or {}).get('dimension_agreement'))}</b>
（{(analysis.get('condition_agreement') or {}).get('dimension_items', 0)} 项）·
买方总分方向一致率 <b>{_percent((analysis.get('condition_agreement') or {}).get('buyer_score_agreement'))}</b>
（{(analysis.get('condition_agreement') or {}).get('buyer_score_items', 0)} 项）</p>
<div class="table"><table><thead>
<tr><th>维度</th><th>可比项</th><th>方向一致率</th></tr>
</thead><tbody>{agreement_rows or '<tr><td colspan="3" class="muted">无双盲样本</td></tr>'}</tbody></table></div></section>
<section><h2>代表轨迹与异常审计（最多 12 条）</h2>
<p class="muted">先覆盖每个 case，再优先展示条件评分分歧、退出和 round-cap 轨迹。</p>
{''.join(transcript_rows) or '<p>暂无有效轨迹。</p>'}</section>
<section><h2>解释边界</h2><ul>
<li>settlement 与成交后价格分开；未成交不被编码为零价。</li>
<li>现金让步按同一角色后续报价向对方方向移动的次数计算，避免不同币值/量级直接相加。</li>
<li>token 为 char/4 估算值，因为 canonical provider 不向调用方暴露 usage。</li>
<li>Pilot 是方向性结果；只有 full 数据用于确认性结论。</li>
<li><b>臂级 M6 均值当前不可用于结论</b>——超时未决局被评为 2–3 分，该指标混入了结局差异。请读成交局口径。</li>
<li><b>臂级现金中位数不可用于结论</b>——它随各臂谈崩掉哪些 case 而变（幸存者偏差），且金额未跨 case 归一化。</li>
<li><b>条件优势排名不可用于结论</b>——两位盲审在维度符号上的一致率见上表；一致率不足时其均值仅描述少数样本。</li>
<li>本实验只操纵了模型，<b>没有</b>操纵 skill/harness、首发方或情报完整度；这些分别属于 A4/A1 与后续实验。</li>
</ul></section></main><footer class="wrap">run_id: {html.escape(run_id)}</footer></body></html>"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target
