# A4 · v2 回归重跑 —— 修复说明与运行记录

Run: `results/a4-v2-regression-fixed/` · config `configs/eval.a4.glm52-qwen36.local.yaml`
前身：`results/clean-coolwei-glm52-qwen36/`（clean 72 + on 72，runs_per_case=3）

---

## 一、两个测量缺陷（都系统性地压低了 on 臂）

上一轮 clean/on 双臂读出 Δ≥sharp = **+6.94pp，CI [−6.94, +19.44]**（跨零）。
排查发现这个读数被两个 harness 缺陷污染，且两个都偏向压低 harness 的表现。

### 缺陷 1 — provenance 词表越界 → M1 假失败

**现象**：on 臂 M1 通过率 58.3%，clean 臂 83.3%，配对差 −25.0pp（CI [−38.9, −9.7]）。
读起来像"harness 破坏了结构完整性"。

**根因**：M1 只接受 `stated / inferred / open` 三个值，但抽取器 prompt **从未写出这个枚举**。
模型于是自创描述字段状态的词来标注跨轮沿用的字段：

```
inherited 50 · updated 22 · confirmed 13 · counter 2
stated_range / stated_approximate / stated_null / stated_amount / removed 各 1
                                              → 共 104 个越界值
```

`_ensure_provenance()` 原本只补**缺失**的键，键存在但值非法时直接放行 → M1 判负。
on 臂中招更多，因为它的报价跨轮沿用的字段更多（`subject` 18 次、`price.cash` 14 次、`terms.format` 10 次）。

**修法**（`negoeval/extract/offer_extractor.py`）：
1. `_ensure_provenance()` 改为既补缺失、也归一化越界值：`stated_*`/`inferred_*`/`open_*` 收敛到前缀，
   其余回落到该字段的默认值（等同于键缺失时的行为）；每次归一化写入 `provenance_coerced:<field>:<old>-><new>` warning 供审计。
2. 两处抽取 prompt 补上枚举约束，从源头减少越界。

**回放验证**（对已记录的 144 局重放）：M1 失败 **clean 12 → 0，on 30 → 0**。
即：上一轮那个 −25pp 的"臂效应" **100% 是 harness 假象**，与 agent 行为无关。

**运行时验证（重跑前 28 局）**：M1 通过率两臂均 **100%**。但要记一条：
**prompt 侧的枚举约束并没有挡住越界**——`inherited` 仍出现 33 次（19 次归一为 stated、14 次为 inferred），
真正起作用的是代码层的归一化。结论：这类"让模型遵守枚举"的约束不能只写进 prompt，
必须在消费端做归一化或在 schema 层强制。后续若要彻底根治，应在 `coerce_deal()` 里把
provenance 收敛进 `Literal["stated","inferred","open"]`，让 pydantic 直接拒绝。

### 缺陷 2 — 未成交局仍被判 sound/sharp → M6 反映的是结局而非 deal

**现象**：R4 rubric 明写 `0 Floor：没做成 deal`，但实际判分：

| 终局 | n | M6 分布 |
|---|---|---|
| settled | 96 | 0:11 1:2 2:25 3:51 4:7 |
| walk_away | 36 | 0:20 1:8 2:6 3:2 |
| **round_cap** | **12** | **0:2 1:1 2:2 3:7** |

`round_cap` 局仍带着一份草稿 `final_deal`，judge 就照着**桌面上的方案**评分，
于是"打满回合、什么都没谈成"可以拿到 sharp。A2 pilot 同一缺陷更明显（25 局 round_cap 全判 2–3）。

**这个泄漏不是中性的**：clean 臂未成交率 47.2%、on 臂 19.4%，
所以被错误加分的局绝大多数落在 **clean 臂**（未成交却判 ≥sound：clean 15 局 vs on 2 局）。

**修法**（`negoeval/grade/judge.py::_r4_no_deal_floor`）：
未成交 → 确定性判 floor，不调用 judge。唯一例外是 doomed case 正确退出（属判断力，仍交 judge）。
当前 case bank 无 doomed 案例，故本次回放不受该例外影响。

**回放验证**：

| | Δ≥sharp | 95% CI |
|---|---|---|
| 修复前 | +6.94pp | [−6.94, +19.44] 跨零 |
| **修复后** | **+16.67pp** | **[+1.39, +30.56] 不跨零** |

按 A4 计划预注册的判定规则，修复后落在 **`effect_confirmed`** 分支。

> ⚠️ 上表是**在旧 transcript 上重放判分**得到的，不是独立重跑。M6 修法是确定性的（未成交→floor，
> 不依赖 judge 重新调用），所以重放对 M6 是精确的；但抽取 prompt 也改了，会影响真实运行时的抽取结果。
> **本次重跑就是为了拿到独立读数。** 在重跑结果出来前，+16.67pp 应标注为"重放估计"。

---

## 二、GLM reasoning effort：实测被端点忽略

用户要求 `reasoning effort = high`。对 `http://192.168.55.233:8000/v1` 实测：

| 传参方式 | 结果 |
|---|---|
| 无 flag（基线） | 18.9s，2000 tok，`finish=length` |
| `reasoning_effort: high`（顶层） | 18.7s，2000 tok，`finish=length` —— **与基线无差异** |
| `chat_template_kwargs.enable_thinking: true` | 与基线无差异 |
| `chat_template_kwargs.enable_thinking: false` | 14.2s，1426 tok，`finish=stop` —— **有差异** |

结论：**GLM-5.2 在本端点思考默认开启，`reasoning_effort` 是 no-op**；能改变行为的只有关掉思考。
所以"reasoning effort = high"在本环境下的可执行含义 = **不要关思考**（保持默认）。
配置中仍显式写入 `extra_body.reasoning_effort: high`，以便端点日后支持时无需改配置。

另检查了截断风险：A 方发言中位 297–406 字、最长 894 字，`max_tokens: 2048` 下
**未观察到截断**（无句末标点收尾的比例 clean 0.0% / on 0.3%），故未调整 token 预算。

---

## 三、本次运行配置

相对上一轮的变化：

| 项 | 旧 | 新 | 理由 |
|---|---|---|---|
| `runs_per_case` | 3 | **5** | n=3 时单 case 内 M6 档位跨度可达 4，单元格方差大于待测效应量 |
| `workers` | 4 | **8** | 按要求提高并发 |
| `keep_trace` | false | **true** | A5（judge 脱钩）需复用本次 transcript，零对局成本 |
| `glm52.extra` | `{}` | `extra_body.reasoning_effort: high` | 见上（当前为声明性） |

未改动：case bank、模型路由、温度、round_cap、judge repeats。
两臂唯一差异仍是 prompt 变体与 skill 注入。

---

## 四、重跑结果（240 局，24 case × 2 臂 × 5 重复，零报错）

### 修复验证：两个缺陷都彻底清掉

| 检查项 | 结果 |
|---|---|
| M1 通过率 | **clean 100% / on 100%**（原 83.3% / 58.3%） |
| 未成交局仍被判 ≥sound | **0 局**（原 clean 15 / on 2） |
| provenance 归一化触发 | 301 次，全部是 `inherited`（151→stated，150→inferred） |

> 301 次 / 240 局 —— **prompt 侧枚举约束基本无效**，全靠代码层归一化。根治仍需在
> `coerce_deal()` 把 provenance 收成 `Literal`。

### 主表

| 指标 | clean | on | 配对 Δ（95% CI） | |
|---|---|---|---|---|
| **≥sharp** | 37.5% | 46.7% | **+9.17pp [−2.50, +19.17]** | 跨零 |
| ≥sound | — | — | +6.67pp [−3.33, +15.83] | 跨零 |
| **未成交率** | 38.3% | 25.0% | **−13.33pp [−22.50, −4.17]** | **✓ 不跨零** |
| ‥ 谈崩 | 25.8% | 20.0% | | |
| ‥ 超时未决 | 12.5% | 5.0% | | |
| case_pass | 32.5% | 36.7% | +4.17pp [−4.17, +12.50] | 跨零 |
| 超预算 | 20.0% | 26.7% | +6.67pp [−2.50, +15.83] | 跨零 |

### 关键分解：质量提升几乎全部来自「多谈成了」

| 口径 | Δ≥sharp | 95% CI |
|---|---|---|
| 全部局（未成交计 floor） | +9.17pp | [−2.50, +19.17] |
| **仅成交局**（去掉成交率通道） | **+2.78pp** | [−9.29, +15.16] |

成交局内：clean 60.8% ≥sharp vs on 62.2%。**一旦控制住"有没有谈成"，harness 对 deal 水准的
增量趋近于零。** 所以 harness 当前可测的价值是**把交易谈成**，不是把谈成的交易谈得更好。

### 判定（按 A4 预注册规则）

Δ≥sharp 点估计 +9.17pp ≥ +5pp 但 CI 跨零 → **`effect_weakened` 分支**：
先跑 A6（超预算 +6.67pp，方向已在三批数据上一致：+6.6 / +5.6 / +6.7），A6 后重测；
此期间 BP 不引用 ≥sharp 数字。可引用的是未成交率 −13.3pp（确定性、不经 judge、CI 不跨零）。

### 更正：此前 +16.67pp 的重放估计未被独立重跑复现

修复后在旧 transcript 上重放得到 +16.67pp [+1.39, +30.56]，独立重跑得到 **+9.17pp [−2.50, +19.17]**。
差异来源：重放只改判分、固定了 transcript；重跑同时改了抽取 prompt 并重新采样，且 clean 臂自身的
未成交率从 47.2% 降到 38.3%（新抽取器让 clean 也更容易被判成交），压缩了两臂差距。
**以重跑为准**；重放估计偏乐观，不应引用。

---

## 五、跑完后要做的

1. 用 `analysis/reanalyze_zip_v2.py` 的同一套配对 + case 聚类 bootstrap 口径出主表。
2. 核对 `provenance_coerced:*` warning 的出现率——若仍高，说明 prompt 侧约束不够，需要在 schema 层强制。
3. 确认 M1 通过率两臂均回到高位且无臂差；若仍有臂差，说明还有第二个来源。
4. 按预注册规则判定，并把 A4 计划文件从 `not-started/` 移到 `ongoing/` 或 `completed/`。
5. 立即接跑 A5（judge 脱钩）——同一批 transcript，避免与代码版本漂移。
