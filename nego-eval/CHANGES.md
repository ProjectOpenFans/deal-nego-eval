# CHANGES v2 — 0706 全案最终交付（文本 + 工程）

**替换方式**：包内路径与 repo 完全一致，按路径整体覆盖；`skills/deal-diagnosis/COMPASS.md` 为新增文件。
**覆盖范围**：施工清单 41 项 + writing 精修 19 处 + 工程 Z1-Z5 全部实现。全部通过语法编译、断言验证、helper 冒烟测试。

---

## 一、文本层（10 个文件）

### negoeval/broker/ — prompts.py / clean_buyer_prompt.txt / clean_seller_prompt.txt
清单 C1-C8、P1-P6、#13 全部落实（对照 v1 CHANGES 不变），本轮无新增改动。

### skills/deal-diagnosis/（SKILL.md 母本 103 行 / INJECT.md / COMPASS.md 新建）
清单 D1-D10、I1-I3 落实 + writing 精修：
- W1：SKILL "When to run what" 第三条改为指向 Round discipline 的指针（消文件内复读）。
- W2：INJECT §4 引言压缩为一句（与 prompt "keep your read to yourself" 同窗冗余，每集付费）。
- W5：COMPASS 溯源注释缩短；**runner 注入时统一 strip HTML 注释**（见工程 Z2），文件内注释仅供维护者。
- Tier1：Provide the following outputs / art of deal making / judgment 拼写统一（3 处）。

### skills/interest-discovery/SKILL.md
N1-N2 落实 + W4（§4 输出 1 括注改指针 "voice it only per §1"）+ judgment 统一。

### skills/term-reframing/SKILL.md
R1-R3、#12 落实 + W3（原第 2 条与 intro 近逐字重复，删除并重编号：3.x→2.x, 4→3, 5→4）+ Tier2（原第 4 条空洞劝勉前半句删除）+ i.e.→e.g.（2.1/2.2 系举例非定义；2.3 保留 i.e.）。

### skills/trust-and-performance / commitment-showcasing / affordability-structuring / alternative-matching
T1-T6、S1-S6、A1-A2 落实 + Tier1 精修：commitment（"Adopt the tools below"、"whether to use"、冗余引语删除）；affordability（too-large-to-handle typo、主谓一致 ×2）。

---

## 二、工程层（7 个 python 文件）

### negoeval/broker/runner.py【Z2 + Z3 + Z4】
1. **注入机制**：R1 强注 INJECT.md（前导语更新为 #6 签署版）；**R2 起每轮注入 COMPASS.md**（`_run_tools` 增加 `round_number` 参数）。注入前 strip HTML 注释（省 token、去 meta）。
2. **forced/voluntary 分账**：强制注入改记 `skills_forced`，不再进 `skills_used`——skills_used 从此只含自愿 read_skill（M12 的路径信号）。强注守卫从"集级 skills_used 查重"改为 `round_number <= 1`。trace 事件从伪 `tool_call` 改为 `forced_inject` / `compass_inject`。
3. **标签泄漏双保险**：历史重建时己方消息不加 "[我方·第X轮]" 前缀（role=assistant 已足标识，对方标签保留）；输出侧 `_strip_round_labels` 剥离行首泄漏标签。

### negoeval/agent/runner.py + negoeval/orchestrator.py【Z4 管道】
`skills_forced` 贯通至 `process["skills_forced"]`。**注意语义变化**：`process["skills_used"]` 从此为自愿路径，任何统计 skill 使用率的报表脚本读数会变（这正是签署意图）。

### negoeval/broker/skills.py【Z5】
`PRODUCT_LAYER_SKILLS = {"alternative-matching"}`，`all_skill_names()` 剔除之——on 臂 allowlist、目录块、read_skill 全部自动失去该 skill；repo 内文件保留。补 None/set() 契约 docstring。

### negoeval/extract/offer_extractor.py【Z1a】
1. **无数字现金承诺哨兵**：per-turn 与 accepted 两个抽取 prompt 均新增规则——承诺现金但无数字（"按刊例价走"）→ `cash.amount = -1`；`extract_final` 归一化为 None 并写 `undefined_cash_commitment` warning。carry-forward 防哨兵降级真实数字。
2. **反加总规则**：两个 prompt 均明令不得把并列方案金额相加、未选中方案的佣金/返点不计入 cash（R4P9 假 fail 的直接修法）。

### negoeval/grade/deterministic.py【Z1b】
M5 三个分支（r4 / sell / buy）新增判据：settled 且带 `undefined_cash_commitment` → fail，reason=`cash_committed_undefined`（堵 R5C1 假 pass）。

### negoeval/grade/judge.py【Z4 + F3】
1. M12 的 routes 取自愿路径（对无 `skills_forced` 字段的历史结果做兼容过滤，剔除 deal-diagnosis）。
2. M12 增加与 M11 对称的 n/a 门控：expected 全空 → n/a 不评（消灭"无瓶颈 case 在 on 臂永久 M12 fail"的系统性 artifact）。
3. M12 prompt 注明强制注入不作评判。

### 工程判断披露（3 处）
1. **Z6 是空账**：judge/deterministic 层经查从未有 payment-structure 判罚（旧禁令的"fails the round"只有 prompt 修辞、无判分牙齿），无需删除。新口径（定额/定段/定确认/零平台裁决）目前**没有机器判分**——是否新增判据属新评分逻辑，超出本轮签署范围，留给你和 Zhe 决定。
2. **哨兵实现方式**（-1 sentinel + warning + M5 门）是签署方向"现金含未定数额→不得 settled"的具体化；抽取器对"无数字承诺"的识别依赖 aux 模型执行 prompt 规则，命中率需在 pilot 中用 R5C1 off 臂旧样本回归验证。
3. **残余风险**：sim 侧若直接回传结构化 offer（`sim_turn.offer is not None` 路径），accepted 再抽取被跳过——R4P9 类加总若发生在 sim 抽取侧，本轮修法够不着；sim/prompt.py 未在签署范围内，未动。记 pilot 观测点。

---

## 三、未动清单
黑丝示例 / blank check 三处（#8 HELD）/ alternative-matching 正文（#14.6）/ interest-discovery gate（#11 判据部分，等新数据）/ affordability 买家团条目（无 ruling）/ sim/prompt.py / cli.py / eval yaml（无需改动——allowlist 由 skills.py 源头剔除）。

## 四、Pilot 前 checklist（全部已在包内，无遗留前置）
- [x] Z1 抽取修复 → 建议先拿 v2b 的 R5C1 off-r0 / R4P9 on-r0 两个旧 episode 重跑判分回归验证
- [x] Z2 罗盘注入 / Z3 标签 / Z4 M12 / Z5 allowlist
- [ ] Pilot 观测点（见 SIGNOFF_LOG）：三态服从度、R5C8 R1 walk_away 率、stepfun 罗盘形态、(a) 态误触发、哨兵命中率
