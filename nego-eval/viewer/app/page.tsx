"use client";

import { useEffect, useMemo, useState } from "react";

type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

type StatusConnection = {
  id: string;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  status: string;
  detail: string;
};

type TranscriptTurn = {
  round: number;
  speaker: "A" | "B";
  message: string;
  offer?: {
    subject?: string;
    price?: { cash?: { amount?: number | null; currency?: string } };
    status?: string;
  } | null;
};

type EvalRun = {
  id: string;
  source: string;
  case_id: string;
  arm: string;
  run_id: string;
  case: {
    side: string;
    tier?: string;
    isolates?: string;
    probes?: string[];
    agent_label: string;
    counterparty_label: string;
    meta: Record<string, JsonValue>;
    input: Record<string, JsonValue>;
    fixture: Record<string, JsonValue>;
  };
  config: Record<string, JsonValue>;
  metrics: Record<string, Record<string, JsonValue>>;
  verdict: {
    gates_pass?: boolean;
    outcome_pass?: boolean;
    case_pass?: boolean;
    quality?: number;
  };
  episode: {
    final_deal: Record<string, JsonValue>;
    transcript: TranscriptTurn[];
    rounds: number;
    terminal_reason: string;
    process: Record<string, JsonValue>;
  };
};

type ReportData = {
  meta: {
    generated_at: string;
    dataset_label: string;
    disclaimer: string;
    canonical_result_dir: string;
  };
  summary: {
    runs: number;
    cases: number;
    pass_rate: number;
    settled: number;
    quality_mean: number;
    rerun_cases: number;
    stable_cases: number;
    stability_rate: number;
    unstable_case_ids: string[];
    judge_agreement_mean: number;
    judge_parse_rate_mean: number;
  };
  filters: { sources: string[]; cases: string[]; arms: string[] };
  endpoint_status: {
    checked_at?: string;
    connections?: StatusConnection[];
  };
  runs: EvalRun[];
};

type InspectorTab = "input" | "metrics" | "deal" | "params";

const FIELD_NAMES: Record<string, string> = {
  episode_id: "任务 ID",
  initial_deal: "初始方案",
  parties: "参与方",
  config: "回合配置",
  subject: "交易标的",
  price: "价格",
  cash: "现金",
  amount: "金额",
  currency: "币种",
  in_kind: "非现金资源",
  terms: "交易条款",
  timing: "时间安排",
  when: "执行时间",
  deadline: "截止时间",
  duration: "持续时间",
  format: "交付形式",
  deliverables: "交付物",
  delivery_standard: "交付标准",
  obligations: "双方义务",
  status: "状态",
  provenance: "字段来源",
  seat: "席位",
  public_profile: "公开资料",
  private: "私有目标",
  intent: "意图",
  interests: "利益诉求",
  value_perception: "价值认知",
  constraints: "约束",
  reservation: "保留条件",
  must_haves: "必须满足",
  deal_breakers: "不可接受",
  blocking_flags: "阻塞项",
  round_cap: "最大轮数",
  agent_seat: "代理席位",
  display_name: "显示名称",
  current_focus: "当前重点",
  location: "地点",
  education: "教育背景",
  career: "职业经历",
  hobbies: "兴趣爱好",
  credentials: "资历",
  case_id: "Case ID",
  side: "代理方向",
  tier: "难度",
  isolates: "核心考点",
  probes: "探针",
  models: "模型连接",
  roles: "角色路由",
  judges: "评分器",
  repeats: "重复评分次数",
  base_url: "Base URL",
  model: "Model ID",
  temperature: "温度",
  max_tokens: "最大 Token",
  trust_env: "读取系统代理",
  timeout_seconds: "单请求超时（秒）",
  max_retries: "SDK 内部重试次数",
  credential: "凭据状态",
  workers: "并发数",
  runs_per_case: "每 Case 重跑次数",
  output_dir: "结果目录",
  keep_trace: "保存完整 Trace",
  resume: "断点续跑",
  include: "包含 Case",
  exclude: "排除 Case",
  kind: "指标类型",
  pass: "是否通过",
  verdict: "判定",
  value: "指标值",
  reason: "原因",
  hits: "命中项",
  unmapped: "未映射项",
  judge_parse_ok: "评分解析成功",
  judge_notes: "评分说明",
  judge_distribution: "评分分布",
  judge_repeat_count: "实际重复评分次数",
  judge_agreement: "评分一致率",
  judge_parse_rate: "评分解析率",
  judge_samples: "逐次评分样本",
  gates_pass: "门槛指标通过",
  outcome_pass: "结果指标通过",
  case_pass: "Case 最终通过",
  quality: "质量分",
  mode: "运行模式",
  arms: "实验组",
  experiment: "实验参数",
  name: "名称",
  directory: "目录",
  cases: "Case 选择",
  sha256: "配置 SHA-256",
  source: "来源",
  adapter: "适配器",
  default: "默认评分器",
  metrics: "指标评分器",
  buyer_negotiator: "买方谈判代理",
  seller_negotiator: "卖方谈判代理",
  buyer_counterparty: "买方对手模型",
  seller_counterparty: "卖方对手模型",
  offer_extractor: "报价提取器",
  agent_profile: "代理配置",
  skills: "技能实验组",
  skills_used: "实际使用技能",
  skills_forced: "强制技能",
  agent_side: "代理方",
  sim_side: "对手方",
  extract_fallbacks: "提取回退次数",
  extract_warnings: "提取警告",
  checked_at: "端点核验时间",
  connections: "模型连接",
  provider: "服务类型",
  detail: "核验详情",
  extra: "额外请求参数",
  extra_body: "额外请求体",
  chat_template_kwargs: "Chat Template 参数",
  enable_thinking: "启用思考模式",
  force_temperature: "强制使用配置温度",
  omit_temperature: "省略温度参数",
  default_headers: "默认请求头",
  file: "Case 文件",
  path: "配置路径",
  schema_version: "结构版本",
};

function fieldName(key: string) {
  return FIELD_NAMES[key] || key;
}

const SCALAR_NAMES: Record<string, string> = {
  live: "真实模型（live）",
  stub: "模拟模型（stub）",
  gate: "门槛指标（gate）",
  outcome: "结果指标（outcome）",
  record: "记录指标（record）",
  full: "完整（full）",
  partial: "部分（partial）",
  fail: "失败（fail）",
  floor: "地板级（floor）",
  crude: "粗糙级（crude）",
  sound: "稳健级（sound）",
  sharp: "敏锐级（sharp）",
  brilliant: "卓越级（brilliant）",
  easy: "简单（easy）",
  medium: "中等（medium）",
  hard: "困难（hard）",
  settled: "已成交（settled）",
  walked_away: "已退出（walked_away）",
  round_cap: "达到轮数上限（round_cap）",
  draft: "草案（draft）",
  proposed: "已提议（proposed）",
  accepted: "已接受（accepted）",
  buy: "买方（buy）",
  sell: "卖方（sell）",
  configured: "已配置",
  missing: "未配置",
  verified: "已核验",
  openai_compatible: "OpenAI 兼容接口",
};

function scalar(value: JsonValue) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" && SCALAR_NAMES[value]) return SCALAR_NAMES[value];
  return String(value);
}

function StructuredData({
  value,
  depth = 0,
}: {
  value: JsonValue;
  depth?: number;
}) {
  if (value === null || typeof value !== "object") {
    return <span className="data-value">{scalar(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className="data-empty">空数组</span>;
    return (
      <div className="data-children">
        {value.map((item, index) => (
          <div className="array-item" key={index}>
            <span className="array-index">{index + 1}</span>
            <StructuredData value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  const entries = Object.entries(value);
  if (!entries.length) return <span className="data-empty">空对象</span>;
  return (
    <div className="data-children">
      {entries.map(([key, item]) => {
        const nested = item !== null && typeof item === "object";
        if (nested) {
          return (
            <details className="data-group" open={depth < 1} key={key}>
              <summary>
                <span>{fieldName(key)}</span>
                <code>{key}</code>
              </summary>
              <StructuredData value={item} depth={depth + 1} />
            </details>
          );
        }
        return (
          <div className="data-row" key={key}>
            <div>
              <span>{fieldName(key)}</span>
              {fieldName(key) !== key && <code>{key}</code>}
            </div>
            <span className="data-value">{scalar(item)}</span>
          </div>
        );
      })}
    </div>
  );
}

function metricLabel(metric: Record<string, JsonValue>) {
  if (typeof metric.pass === "boolean") return metric.pass ? "通过" : "失败";
  if (typeof metric.verdict === "string") {
    return { full: "完整", partial: "部分", fail: "失败", "n/a": "不适用" }[
      metric.verdict
    ] || metric.verdict;
  }
  if (typeof metric.tier === "string") return metric.tier;
  if (typeof metric.value === "number") return String(metric.value);
  return "记录";
}

function metricTone(metric: Record<string, JsonValue>) {
  const label = metricLabel(metric).toLowerCase();
  if (["通过", "完整", "goldman", "sharp", "brilliant"].includes(label)) return "good";
  if (["失败", "floor"].includes(label)) return "bad";
  return "neutral";
}

function rerunNumber(runId: string) {
  const match = runId.match(/r(\d+)$/);
  return match ? Number(match[1]) + 1 : runId;
}

function armName(arm: string) {
  return { clean: "基线", on: "Compass 开启", off: "Compass 关闭" }[arm] || arm;
}

function terminalName(reason: string) {
  return {
    settled: "已成交",
    walk_away: "已退出",
    round_cap: "达到轮数上限",
  }[reason] || reason;
}

function offerSummary(turn: TranscriptTurn) {
  const amount = turn.offer?.price?.cash?.amount;
  const pieces = [];
  if (turn.offer?.subject) pieces.push(turn.offer.subject);
  if (typeof amount === "number") {
    pieces.push(`${turn.offer?.price?.cash?.currency || "CNY"} ${amount.toLocaleString()}`);
  }
  return pieces.join(" · ");
}

export default function Home() {
  const [data, setData] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [caseId, setCaseId] = useState("all");
  const [arm, setArm] = useState("all");
  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState<InspectorTab>("input");

  useEffect(() => {
    fetch("/data/report.json")
      .then((response) => {
        if (!response.ok) throw new Error(`报告加载失败：${response.status}`);
        return response.json();
      })
      .then((payload: ReportData) => {
        setData(payload);
        setSelectedId(payload.runs[0]?.id || "");
      })
      .catch((reason) => setError(String(reason)));
  }, []);

  const filteredRuns = useMemo(() => {
    if (!data) return [];
    return data.runs.filter(
      (run) =>
        (caseId === "all" || run.case_id === caseId) &&
        (arm === "all" || run.arm === arm),
    );
  }, [data, caseId, arm]);

  const run = filteredRuns.find((item) => item.id === selectedId) || filteredRuns[0];

  if (error) {
    return (
      <main className="state-page">
        <p className="eyebrow">评测报告 / 加载失败</p>
        <h1>无法读取评测结果。</h1>
        <pre>{error}</pre>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="state-page" aria-busy="true">
        <p className="eyebrow">谈判评测控制台</p>
        <h1>正在加载完整证据链…</h1>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">谈</span>
          <div>
            <strong>谈判评测控制台</strong>
            <small>{data.meta.dataset_label}</small>
          </div>
        </div>
        <div className="model-route">
          {(data.endpoint_status.connections || []).map((connection) => (
            <details className="model-chip" key={connection.id}>
              <summary>
                <span className={connection.status === "verified" ? "online" : "offline"} />
                <b>{connection.label}</b>
                <code>{connection.model}</code>
              </summary>
              <div>
                <p><b>服务商：</b>{connection.provider}</p>
                <p><b>Base URL：</b><code>{connection.base_url}</code></p>
                <p>{connection.detail}</p>
              </div>
            </details>
          ))}
        </div>
        <div className="top-stats">
          <span><b>{data.summary.runs}</b> 次运行</span>
          <span><b>{data.summary.cases}</b> 个 Case</span>
          <span><b>{Math.round(data.summary.pass_rate * 100)}%</b> 通过</span>
          <span><b>{Math.round(data.summary.stability_rate * 100)}%</b> 重跑稳定</span>
          <span><b>{Math.round(data.summary.judge_agreement_mean * 100)}%</b> Judge 一致</span>
        </div>
      </header>

      <div className="notice">
        <b>TL;DR：</b>
        通过率 {Math.round(data.summary.pass_rate * 100)}%，
        成交 {data.summary.settled}/{data.summary.runs}，
        平均质量 {data.summary.quality_mean.toFixed(2)}；
        {data.summary.rerun_cases} 个已有复跑的 Case 中 {data.summary.stable_cases} 个结论稳定，
        Judge 平均一致率 {Math.round(data.summary.judge_agreement_mean * 100)}%、
        解析率 {Math.round(data.summary.judge_parse_rate_mean * 100)}%。
        {data.summary.unstable_case_ids.length > 0 && (
          <span> 需复核：{data.summary.unstable_case_ids.join("、")}。</span>
        )}
        <span> 本页只含当前 GLM/Qwen 结果。</span>
        <code>{data.meta.canonical_result_dir}</code>
      </div>

      <section className="codex-layout">
        <aside className="history-sidebar">
          <div className="sidebar-title">
            <div>
              <p className="eyebrow">运行记录</p>
              <h2>谈判历史</h2>
            </div>
            <span>{filteredRuns.length}</span>
          </div>
          <div className="filters">
            <label>
              Case
              <select value={caseId} onChange={(event) => setCaseId(event.target.value)}>
                <option value="all">全部 Case</option>
                {data.filters.cases.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label>
              实验组
              <select value={arm} onChange={(event) => setArm(event.target.value)}>
                <option value="all">全部实验组</option>
                {data.filters.arms.map((item) => (
                  <option key={item} value={item}>{armName(item)}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="run-list">
            {filteredRuns.map((item) => (
              <button
                className={item.id === run?.id ? "run-item active" : "run-item"}
                key={item.id}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="run-icon">{item.case_id.slice(-2)}</span>
                <span className="run-copy">
                  <b>{item.case_id} · 第 {rerunNumber(item.run_id)} 次</b>
                  <small>
                    {armName(item.arm)} · {item.episode.rounds} 轮 ·{" "}
                    {terminalName(item.episode.terminal_reason)}
                  </small>
                </span>
                <span className={item.verdict.case_pass ? "status-pass" : "status-fail"}>
                  {item.verdict.case_pass ? "通过" : "失败"}
                </span>
              </button>
            ))}
            {!filteredRuns.length && (
              <div className="waiting">
                <b>等待本次实验结果</b>
                <p>结果写入后，运行记录会自动出现在这里。</p>
              </div>
            )}
          </div>
        </aside>

        <section className="conversation-pane">
          {run ? (
            <>
              <header className="conversation-header">
                <div>
                  <p className="eyebrow">
                    {armName(run.arm)} · 第 {rerunNumber(run.run_id)} 次运行
                  </p>
                  <h1>{run.case_id} · {run.case.side === "buy" ? "买方代理" : "卖方代理"}</h1>
                  <p>{run.case.isolates || "未提供 Case 摘要"}</p>
                </div>
                <div className={run.verdict.case_pass ? "case-verdict passed" : "case-verdict failed"}>
                  <small>Case 结论</small>
                  <strong>{run.verdict.case_pass ? "通过" : "失败"}</strong>
                  <span>质量 {run.verdict.quality ?? 0}</span>
                </div>
              </header>
              <div className="conversation-stream">
                {run.episode.transcript.map((turn, index) => {
                  const isAgent = turn.speaker === "A";
                  return (
                    <article className={isAgent ? "message agent" : "message counterparty"} key={`${turn.round}-${turn.speaker}-${index}`}>
                      <div className="avatar">{turn.speaker}</div>
                      <div className="message-body">
                        <div className="message-meta">
                          <strong>{isAgent ? run.case.agent_label : run.case.counterparty_label}</strong>
                          <span>第 {turn.round} 轮</span>
                        </div>
                        <p>{turn.message || <em>模型返回了空内容</em>}</p>
                        {offerSummary(turn) && (
                          <details className="offer">
                            <summary>本轮结构化报价 · {offerSummary(turn)}</summary>
                            <StructuredData value={(turn.offer || {}) as JsonValue} />
                          </details>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="empty-conversation">
              <span>⌁</span>
              <h1>结果目录已清空</h1>
              <p>正在等待 Coolwei GLM / Qwen 的新谈判结果。</p>
            </div>
          )}
        </section>

        <aside className="inspector">
          <nav className="inspector-tabs" aria-label="运行详情">
            {([
              ["input", "初始输入"],
              ["metrics", "评分"],
              ["deal", "最终方案"],
              ["params", "全部参数"],
            ] as [InspectorTab, string][]).map(([value, label]) => (
              <button className={tab === value ? "active" : ""} key={value} onClick={() => setTab(value)}>
                {label}
              </button>
            ))}
          </nav>
          <div className="inspector-content">
            {run ? (
              <>
                {tab === "input" && (
                  <>
                    <InspectorSection title="初始 EpisodeInput" subtitle="传给谈判系统的完整结构化输入">
                      <StructuredData value={run.case.input as JsonValue} />
                    </InspectorSection>
                    <InspectorSection title="Case 元数据" subtitle="方向、难度、隔离变量与探针">
                      <StructuredData value={run.case.meta as JsonValue} />
                    </InspectorSection>
                    <InspectorSection title="评分基准 Fixture" subtitle="本 Case 的完整答案与判分锚点">
                      <StructuredData value={run.case.fixture as JsonValue} />
                    </InspectorSection>
                  </>
                )}
                {tab === "metrics" && (
                  <>
                    <div className="verdict-strip">
                      <span>门槛 {run.verdict.gates_pass ? "通过" : "失败"}</span>
                      <span>结果 {run.verdict.outcome_pass ? "通过" : "失败"}</span>
                      <span>质量 {run.verdict.quality ?? 0}</span>
                    </div>
                    {Object.entries(run.metrics)
                      .sort(([a], [b]) => Number(a.slice(1)) - Number(b.slice(1)))
                      .map(([name, metric]) => (
                        <details className="metric-card" open key={name}>
                          <summary>
                            <b>{name}</b>
                            <span className={metricTone(metric)}>{metricLabel(metric)}</span>
                          </summary>
                          <StructuredData value={metric as JsonValue} />
                        </details>
                      ))}
                  </>
                )}
                {tab === "deal" && (
                  <InspectorSection title="最终 Deal" subtitle={`终止原因：${terminalName(run.episode.terminal_reason)}`}>
                    <StructuredData value={run.episode.final_deal as JsonValue} />
                  </InspectorSection>
                )}
                {tab === "params" && (
                  <>
                    <InspectorSection title="运行配置" subtitle="包括模型路由、生成参数、重复评分和配置哈希">
                      <StructuredData value={run.config as JsonValue} />
                    </InspectorSection>
                    <InspectorSection title="执行过程参数" subtitle="本次 episode 实际记录的运行状态">
                      <StructuredData value={run.episode.process as JsonValue} />
                    </InspectorSection>
                    <InspectorSection title="端点核验" subtitle="当前配置使用的完整路径与 Model ID">
                      <StructuredData value={data.endpoint_status as unknown as JsonValue} />
                    </InspectorSection>
                  </>
                )}
              </>
            ) : (
              <InspectorSection title="当前运行参数" subtitle="结果生成前仍可核对模型端点">
                <StructuredData value={data.endpoint_status as unknown as JsonValue} />
              </InspectorSection>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

function InspectorSection({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="inspector-section">
      <header>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </header>
      {children}
    </section>
  );
}
