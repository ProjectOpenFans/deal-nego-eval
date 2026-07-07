# Harness Refinement — Sign-off Log (0706)

Protocol: 病灶 → 意图确认 → 修法定稿 → Luke sign off → 记录。最后按本 log 一次性整体修改。

---

## Gate Rulings

**G1 — Clean arm 定位**：clean = 只懂游戏基本规则的裸模型，排除一切 deal-making craft。
→ 级联：clean prompt 中 "Reading the counterparty"、"silent check"、"不宣称 limit" 三段移除（craft 归 value-add 独有）。money rules 属基本规则，两臂一致。

**G2 — Blank check**：未建成的产品功能，属产品层非 harness 层。commitment-showcasing 的 blank check 段落单独过，暂挂起。

---

## 病灶 #1 — Money rules 全禁 payment structure【SIGNED OFF】

**病灶**：Prompt money rule 1 将支付通道与支付结构捆绑全禁（"30% upfront" = violation），压掉 skill 体系整个 payment 维度（diagnosis 2.3 / term-reframing payment / affordability §2 / trust §2.2-2.3）。

**Luke 意图**：payment structure（分期、里程碑、earn-out、contingent）是 PE 级 craft 核心维度，正是要 agent 学的灵活性。money rule 为 Zhe 独立所写，未经 Luke 审。

**平台约束（Luke ruling）**：平台只执行金额 + 时点 + 付款方确认放款。零 burden of proof——不验证结果、不裁决条件、不接收证据。条件（里程碑/效果）是当事人之间的约定。

**定稿修法**（buyer 侧示例，seller 侧镜像，clean 同步）：
1. Channel is locked: all funds move through OpenFans escrow only. No direct transfers, no off-platform payment, no alternative rails — never negotiated, never written into terms.
2. Payment structure is a negotiable deal dimension: installments, staged payments, and milestone- or outcome-linked legs are all legitimate terms. But the platform executes only amounts and timing: every payment leg written into terms must be a defined amount, at a defined stage, released by the paying party's confirmation — all through escrow. Any condition attached to a leg (a milestone, an outcome, a quality bar) is an agreement between the parties: write it clearly enough that both sides can judge it themselves, but never write a term that requires the platform to verify results, evidence, or performance.
3. Deposit/tip 条款保留（删 "The only exceptions are" 措辞）。
4. Amount–tool binding：原文不动。
5. Ledger is truth：原文保留 + 加一句 "Future payment legs written into terms are commitments, not payments — never describe a future leg as paid or received until it exists in the ledger."
6. Blank check 条款保留待 G2 议题。

**要点**："formula" 不进条文（公式腿要求平台算数 = burden of proof）；earn-out 须在签约时坍缩为固定金额条件腿。三要素 = 定额、定段、定确认。

**级联**：affordability §2、trust §2.2/2.3 由"指挥判负"转为基本合法，措辞在整体修改时对齐新口径；trust §4 "executable by a third party" 改为"清晰到双方当事人可自行判断"口径（到该病灶时过文字）。

**落地前置闸**：
- [ ] 问 Zhe：原全禁是否为早期 run 止血补丁；确认新防线覆盖原止血功能。
- [ ] Judge rubric 同步：payment-structure 出现在 terms 不再判 violation，新判据 = 每腿是否定额/定段/定确认、是否要求平台裁决。

---

## 病灶 #2 — Side-blindness + deposit 双语义缠绕【SIGNED OFF】

**病灶**：(a) commitment-showcasing 三件工具全为 buyer-only，但 skill 文本与 router 行 side-blind——seller broker 被正当路由后无合规工具，或学舌替买方声称定金撞 seller money rule；(b) "deposit" 一词双语义缠绕：语义 A（工具型诚意金）与语义 B（条款型定金结构）在 prompt amount-tool binding、trust §2.1、中文输出三处互相误伤。

**Luke 意图/ruling**：
1. Deposit/Tip/Blank check 是特殊工具，seller 可"要"（作为条件请求）不可"用"；买方怀疑卖方诚意时这三件工具一律不适用。
2. Seller 确有需要表诚意的场景，正确形态 = 通过 deal terms 降低买方的不确定性与风险，绝不涉及特殊资金工具。
3. commitment-showcasing 设计原意即 buyer-only，专为管辖 tipping / early deposits / blank checks 而写。
4. 两个 deposit：工具型（立即打款、成交抵扣、不成退还、表诚意、仅 buyer）≠ 条款型（先定金后余款的付款结构、降风险、双侧、与 milestone/outcome 平行）。trust §2 意图是教 agent 灵活用条款解决信任问题，非穷举执行。

**定稿修法**（五处）：
1. commitment-showcasing description：开头加 "Buyer-broker-only skill"；"a party"→"the buyer"；"early deposits"→"commitment deposits"；加反向边界句（不适用于解决对 seller 的怀疑，那是 trust-and-performance 领地）。
2. commitment-showcasing 正文：Tools 前插 Side rule 段（seller may request, never initiate/promise/claim）；工具 2 更名 commitment deposits 并加与 down-payment leg 的区分句；修 Priortize/depsoit 拼写。
3. deal-diagnosis §3 router 行拆双侧：buyer 表诚意且愿以钱背书（never casually）→ commitment-showcasing；seller 表诚意 → trust-and-performance（通过条款降买方风险，资金工具 buyer-only）。SKILL.md 与 INJECT.md 双源同改。顺带修复 router 比 description 松的问题。
4. trust-and-performance：§2.1 改写为 Down-payment structure（语义 B，降风险，注明非 buyer 诚意金工具）；新增 §2.4 Seller-side commitment（卸买方风险的开放式手段列表，never monetary instruments）。§2.2/2.3 原文不动，口径对齐留整体修改。
5. prompt amount-tool binding 加语义边界：binding 仅辖 commitment deposits 与 tips（即时资金动作）；down-payment leg 是普通条款，无需调工具，但 ledger 之前是 commitment 非 payment。seller 版 rule 2 镜像：提定金结构是正当谈判，不可代买方声称即时资金动作。clean prompt 同步（基本规则两臂一致）。

**全域命名约定**：语义 A = commitment deposit / 诚意金（buyer-only，offer_deposit，commitment-showcasing）；语义 B = down payment / 定金·首付款（双侧，普通 payment leg，trust-and-performance 与 term-reframing）。整体修改时全域统一。

**落地前置闸**：
- [ ] `offer_deposit` 工具名及 description 是否更名对齐（涉 Zhe 接口）。
- [ ] Judge 对中文 transcript 中"诚意金 vs 定金"的区分判据。

---

## 病灶 #3 — Clean 臂去 craft【SIGNED OFF】

**病灶**：clean prompt 含三段与 value-add 逐字相同的高杠杆 craft，baseline 被污染，Δ 压缩，V-shape 结论解释受污染。

**Luke ruling**：按 G1 纯化；clean 臂变弱没关系，历史数据断代（213 集旧 clean 基线不可与新 Δ 混表，需重跑 clean 臂）的代价接受。

**定稿修法**（clean_buyer_prompt.txt / clean_seller_prompt.txt 同改）：
- 留：Your role / Carry out the mandate / Money & payment rules（按 #1、#2 新版同步，两臂一致）/ Confidentiality 第 1-2 条（公开-私域信息制度、内部数字禁词——防泄密属游戏规则）/ Output / Language。
- 删："Reading the counterparty" 整段（SEE-THROUGH/SAY-OUT craft）；"Before you send an offer (silent check)" 整段（offer 质检 craft）；Confidentiality 第 3 条 "do not declare your own limit as a limit"（谈判姿态 craft——裸 broker 自曝手牌不违规，只是打得差，baseline 该有的样子）。

**级联**：改后 clean→on gap 需以新 clean 重跑重建；旧 213 集 Δ 仅作历史参考。

---

## 病灶 #4 — Mandate vs money rules 优先级【SIGNED OFF · 从简处理】

**病灶**：mandate 段（"most important"）与 money rules（"hard constraints"）各自称王，冲突时无裁决条款；且 "The other side's refusal, the judge asking to continue, or platform payment rules do not equal client authorization to withdraw" 一句把平台规则并列进"不构成弃守理由"列表，字面可读成"平台规则挡不了 mandate"。

**Luke ruling（两层楼逻辑）**：平台规则第一（first principle 治理，违规指令不进执行——Nike 让 Goldman 炸楼，永远不做）；规则之内 mandate 是一切（查地址就去查，no matter what）。但**非必要不增加**：eval 的 case 是自产封闭的，三轴不含"客户指令违规"，冲突自然发生率约零；模型自发绕规则的行为 money rules 已直接禁止，无需元规则重复。

**定稿修法（净变化：删三词，加零字）**：
1. "Two floors" 条款不加，两臂都不加。
2. 歧义句手术：从并列表中删除 "or platform payment rules"，改为 "The other side's refusal, or the judge asking to continue, does not equal client authorization to withdraw."（该词组是旧全禁时代防"拿平台不让分期当弃价借口"的残留，#1 后场景已不存在，纯歧义源。）buyer/seller 两版同改。
3. 未来钩子（记档不进 prompt）：若 case 设计未来引入"客户指令违规"考点，启用 Two floors 条文——平台规则为物理层，违规指令不进执行、如实报告不可行、broker 不代客户重写 mandate；规则内 mandate 绝对。

---

## 病灶 #5 — 双源漂移（SKILL.md vs INJECT.md）【SIGNED OFF】

**背景（Luke 补充）**：INJECT.md 为 token 压缩而生（每集注入用紧凑版）；force-pull 因模型可能自判"无需 skill"而设,harness 对执行有正收益（数据已证）,不能把收益交给模型 autonomy；INJECT 晚于 SKILL 创建（期间新增 interest-discovery）；"primary + alternative path" 是 Zhe 的 legacy 设定。

**Luke ruling**：mid-tier Δ 是商业核心（mid-tier + harness 跑出 great results while commercially feasible）→ fallback 的脚手架价值优先。其余方案无异议。

**定稿修法**：
1. **主从架构**：SKILL.md = 母本（全量,auto 回读用）,INJECT.md = 压缩视图（每集注入用）。修改一律先落 SKILL.md 再人工压缩同步。两文件头部加注释声明主从关系（`<!-- Source of truth: SKILL.md. Edit there first, then compress here. -->` / 母本侧对应说明）。不做自动化脚本（压缩含判断,非机械 truncation）。
2. **Force-pull 补强**：INJECT §3 加一行 "Routing is not optional: once your diagnosis selects a skill, read it before composing this round's message — do not substitute your own recollection of what it says." 堵"选而不读、凭印象发挥"的缝。机械强制（runner 解析 router 输出自动注入）不做,待 transcript 证据显示"选而不读"高发再升级。
3. **漂移一**：SKILL.md "Two scans" → "Three scans"（笔误,INJECT 为准）。
4. **漂移二**：双源对齐为默认必给 + 窄出口："One primary path, plus a fallback mapped to a different skill or a different term structure — give the fallback by default; omit it only when the diagnosis is unambiguous and the primary path has no visible failure mode this round."（默认给 = mid-tier 脚手架；窄出口 = 清晰局面不逼编造；different skill/structure 限定防换措辞充数的假 fallback。）
5. #2 已定的 router 行修改按主从纪律落：先 SKILL.md 后 INJECT.md。

---

## 病灶 #6 — Force-inject 时机 / 后续轮治理机制【SIGNED OFF】

**病灶（初始）**：force-inject 首轮注入僵局框架与 skill 自身触发条件（impasse）及 prompt "别抢跑" 矛盾。

**调研升级（Luke 上传 4 集 on 臂实测,R5C1 + R5C8×3）**：
- **F1**：注入实为每集一次（守卫在集级 skills_used 上）；episode tool_calls 只记自愿调用；2+ 轮基本裸奔,自愿重读极不稳定（4 轮 5 次 vs 12 轮 1 次）。
- **F2（头号死法）**：不是 over-structure,是"赢了不收网演物流"——R5C8 r0/r1 第 5 轮实质谈妥后,6-7 轮 roleplay NDA/邮件/背调,撞 round_cap → not_settled。3 跑 2 死。r2 之所以活:框架被接受后立刻拍具体方案+报价推到签约。
- **F3**：M12 judge 惩罚强制路由——force-inject 的 deal-diagnosis 记入 skills_used,无瓶颈 case 在 on 臂全部 M12 fail（现不 gate,但路径统计被污染）。
- **F4**：R5C1 零现金 settle（in_kind: user_research+content_diagnosis）,M6 sharp——验证 cash-trap 新语义,judge 按非现金成交给分,无"按拒付给分"问题。

**方案演化（被否路径记档防回捡）**：轴二总闸（重复立法,撤）→ 默认每轮全跑（画蛇添足/车轱辘话/token,Luke 否）→ 三态+standing diagnosis（失忆架构下"建一次增量更新"机械不成立,收回）→ 首轮 force execution（与 R1 三扫描定位矛盾,front-running 风险,收回）→ deal file 工程方案（V1 双输出设计完整,Luke 判工程量过大,记远期选项不排期）→ 每轮注全图 / 仅首轮 force 双跳（对 F2 零触达,正面否）。

**定稿方案 E（零工程）**：
1. **INJECT.md 头部加 "When to run what"**：R1 只跑 §0 三扫描静默备牌,开场白是谈判动作不是分析;对方首次实质回应后跑全路径建立 read。执行层全程 auto 不动。
2. **新增 COMPASS.md（~12 行）,R2 起每轮注入**——三态强制分诊（穷尽、可观察、无跳过选项）:
   (a) 对方向你移动/已接受框架 → 收网:下一条消息拍完整可签版本,open 字段钉死或写成条款内先决条件（NDA/背调/交付是 terms 里的 condition,不是逐轮演的过程）;不以"静候佳音"收尾。
   (b) 顶回/新反对 → 新信息改变 binding issue? 变则重路由并读新 skill;不变则按既定路径推进,执行中 skill 本轮重读不凭印象;路由查表时重读 deal-diagnosis。
   (c) 原地重复 → 即僵局:升级（换 skill 读取/换结构/hold=现版本+逼表态确认问题）,不重发上一轮。
   尾行:新结构是成本,只在被拒或新阻塞时引入,不装饰收敛中的 deal。
3. **runner 参数改动**:R1 注 INJECT,R2 起注 COMPASS（同一注入通道,Zhe 十分钟级）。
4. **SKILL.md description 改写**:"The central routing framework... Injected at round 1; re-read when you need the issue taxonomy or the skill router — when a new blocker changes the binding issue, or the deal stalls. Do not re-run the full framework on a converging deal."（关 auto 逃课授权,不诱发每轮全跑。）
5. **三层送达架构定型**:SKILL.md=图书馆（自愿查阅）;INJECT=R1 作战简报;COMPASS=逐轮作战卡。罗盘内容同时入 SKILL.md 母本 "Round discipline" 节,COMPASS 为其逐轮注入切片,主从纪律三层化:SKILL.md → INJECT.md → COMPASS.md。
6. **Auto 路径确认**:模型任何轮自愿 diagnosis/execute 完全不受限——罗盘是兜底不是封顶;勤快模型不受限,偷懒模型被托底。
7. **Token 账**:罗盘 ~250/轮;SKILL.md +15 行不进自动注入通道;整体修改阶段统一精简 SKILL.md 赘肉。

**落地前置闸**:
- [ ] Pilot 先行（3-model-clean-first）:R5C8 收敛型 + 一个僵局型,验证三态分诊服从度,重点 (a) 态误触发（过早收网）与 meta 泄漏。不干净则退守版:COMPASS 砍三态,留两条无条件规则（收网纪律+新结构成本）。
- [ ] M12 豁免强制路由（judge 剔除 force-inject 的 deal-diagnosis,或 skills_used 分 forced/voluntary）。
- [ ] R5C8 类 case 补 M11/M12 ground truth 路径字段（case bank 侧）。
- [ ] on 臂基线随 clean 臂重跑（断代已在 #3 接受）。

**远期选项（不排期）**:private deal file V1（双输出+窄 schema 四字段+错误固化对策）,治记忆病非程序病;罗盘三态即其未来更新协议,现方案不堵路。

---

## 病灶 #7 — term-reframing "2-3 options each time" vs prompt "one proposal"【SIGNED OFF】

**病灶**：term-reframing 第 5 条命令每次公开摆 2-3 套方案 + 标注 human approval；prompt Output 段要求每轮一个具体 proposal。字面冲突 = 两臂对比噪声源；"each time" 是最高频路由 skill 里的无条件 imperative（系统性行为塑造）；human-approval 无 sink（产品残留）。

**Luke 意图**：(1) 真实世界早期/低清晰度/高摩擦定制局面，公开多选项是常规实践（探测器功能）；(2) 问过 AI 层面公开多选项是否助谈判——判定：内部生成时思考增益已全部兑现，公开与否按阶段权衡；(3) prompt 与 skill 分别由 Zhe/Luke 独立写成,misalign 需修。过程中 Luke 否掉："结构不是价格"约束（无 harm evidence,违反证据纪律,撤）；阶段分类判断（不加判断负担,撤）。

**方案演化**：公开赶回内部（Luke 第 1 条推翻）→ 阶段分流长版（Luke 质疑约束过明确,瘦身）→ 四合一条件规则（"删掉重写"测试发现压缩失真 + 越权/hold 两短句系重复立法、论证驱动写作）→ **终版乙:降格为纯 insight**。

**定稿修法**：
1. term-reframing 第 5 条整条替换为单句 insight（零命令）:
   "In early, low-clarity negotiation, tabling two or three structurally distinct versions can be a probe: which one the counterparty engages reveals their real priorities."
   （越权防线归 prompt mandate 段既有铁律;hold 归罗盘 (c) 态;内部多候选系通用思考纪律不写;human-approval 删除。单一职责,治理归 prompt/罗盘,skill 纯 toolkit。）
2. prompt Output 段（双侧双臂）:"one concrete current proposal" → "a concrete, respondable proposal"（prompt 不数数,防空谈功能保留,份数逻辑单一归属 skill 层）。

**已识别残余风险（result track 观测项）**："probing 无硬定义 → mid-tier 可能过度端菜单"由罗盘过程层对冲;"hold=重申现版本是否算 respondable"窄缝由罗盘 (c) 态显式合法化双保险。

---

## 病灶 #8 — Blank check 三方对不齐【HELD · 本轮不改】

**病灶**：commitment-showcasing 教三件工具（含 blank check 三子型）；prompt rule 2 说 only deposit/tip、rule 5 又规范 blank check 使用限制；schemas 有 blank_check 开关但 runner 无工具定义（空转）。

**Luke ruling（更正）**：blank check 是工具型 special 产品 feature，未建成；影响不大（commitment-showcasing 基本不被路由）。**本轮 refine 完全不动**——skill/prompt/schemas 三处均保持现状，整案挂起至产品 feature 建成时一并处理。

**届时候选方案（备忘,非本轮承诺）**：skill 删或随工具上线补全 blank check 节;prompt rule 5 与工具实际行为对齐;schemas 开关接通。

---

## 病灶 #9 — Router 映射表拆除 + alternative-matching 摘除【SIGNED OFF】

**病灶**：§3 六行 "病→药" 映射表与 Luke 架构意图相反（taxonomy=病因学知识、skill=武器库知识、连线=agent 判断，刻意留白）；表造成不满射（4.2/6.x 无路由）、双真理源（与 description 触发条件松紧不一）、例外变违规（R5C1 型 moat 案上表站错误一边）；alternative-matching 触发条件"exhausting all"不可证真且核心动作在集内无合规通道。

**Luke 意图/ruling**：
- 刻意不设 rigid issue-router map；agent 应理解病因学 + 武器库,自行判断选武器。独立推演后 Claude 同判（查表优化的是链路里最不缺的一环;表在 moat 案上有害;判断式需保留原则层护栏）。
- 下半四条 logic 倾向不改;第四条意图 = 经验先验（大部分交易主矛盾在价值/价格,intent/信任/执行是下游矛盾,价值账平了多自行消解）,非"先去砍价"的顺序指令。
- 判断式段落逐句裁剪:"trust→smaller steps" 示范例删（锚定偏差:mid-tier 会读成偏好）;"two weapons" 删（与 logic 第一条重复）;"some issues need no skill" 删（与 #6 判断权收缴对撞——给 smart-ass 官方授权书;且 R5C8 实测无此句时模型行为已正确,防的病无证据）;移交句也不要（非必要不加,罗盘 R2 起本来在场）。
- alternative-matching:真实流程需请示客户或事后解释（调佣门槛非常高）;若致紊乱宁愿拿掉。Claude 论证集内授权通道不存在、自主换 subject 撞 #4 铁律且被 M2 判死、换人无工具、余下动作冗余 → (b) 摘除。

**定稿修法**：
1. **§3 重写**（标题 "Choose the optimal skills (router)" → "Choose your weapons"）,上半块最终素版:
   "You know the common ways deals get stuck (§1) and you have a set of weapons — each skill's description tells you what it does and when to reach for it. The mapping between issue and weapon is your judgment, not a lookup."
   下半四条 logic:前三条原文一字不动;第四条重写为:"When everything else is equal, prioritize value and price: in most deals they are the primary contradiction — intent, trust, and execution frictions are usually downstream, and tend to dissolve once both sides agree the deal is worth it."
2. **触发知识单一归属各 skill description**（表删除后无双源;#2 中 router 行承载的 buyer/seller 分流内容移置:buyer-only 限制已在 commitment-showcasing description,seller 侧"通过条款降风险"半句移入 trust-and-performance description）。
3. **alternative-matching 摘除四件套**:eval allowlist 摘除（Zhe 配置层一行,目录/follow_up 随 allowlist 自动剪除）;SKILL.md 留 repo 加头注 `<!-- Product-layer skill. Excluded from eval allowlist: requires client-consultation channel & counterparty re-matching, neither exists in-episode. -->`;taxonomy 3.1 保留（病因学知识,集内正确反应="在此对手身上做到最好"）;触发条件改写文本存 log 备产品层（"Trigger when the binding issue has survived at least one genuine restructuring attempt and the counterparty has not moved — change the frame: different subject matter, different structure, or (when the platform supports it) a different counterparty."）。
4. INJECT.md §3 段按主从纪律同步压缩,压缩稿整体修改时过目。

---

## 病灶 #10 — 报告型 deliverables 无 sink【SIGNED OFF · 零改动】

**存量盘点**：原病灶三成员——alternative-matching deliverables 段（随 #9 摘除消失）、term-reframing human-approval（#7 已删）、commitment-showcasing 原则 4 "All terms subject to final human approval"（唯一存量）。

**结论**：原则 4 系原始误归类——它有真实 sink（deposit/tip 工具机械 = pending human confirmation,原则陈述的是工具属性,不要求公开回复标注）。保留原样。deal-diagnosis §4 / interest-discovery §4 输出段均明文 internal,sink=行动依据,合法不动。病灶经 #7/#9 级联自愈,零改动。

---

## 病灶 #11 — interest-discovery 两处硬化【PARKED · 待 result package】

**病灶**：admission gate 单信号（"sits oddly against who they are" 全凭 vibes,判据配不上闸）;§3 resistance 二分叉判据 "why they resist" 不可观测,mid-tier 面对指令相反的两支+看不见的开关=掷硬币。

**历史更正（Luke 披露）**：本 skill 系 Opus 所写,非 Luke 手笔;admission gate 系 Luke 质询"如何避免画蛇添足、无休止硬三角隐藏利益"后 Opus 所加。审查时不必给原文 benefit of doubt。skill 的定位（Opus 陈述）：为 term-reframing 等提供正确的 reframe 底牌——真正该解的 interest 谜题未必是 stated 的那个。

**Luke ruling**：Park。全部病灶过完后 Luke 提供 result package,带数据审这个 critical skill——判据校准问题只有 transcript 能裁决。

**预注册观测点（防顺着结果找故事）**：
- (a) admission gate 实际拦截率:被路由后判"无真实 gap"退出的比例,还是次次开闸形同虚设;
- (b) 误触发形态:对直给型对手发明隐藏动机的实例及其样貌;
- (c) 二分叉行为:遭遇抵抗后实际走哪支,与局面是否对得上。
- 候选判据备用（届时对数据）:gate 信号三候选——诉求与可见资源/处境矛盾;诉求被满足后升级转移;所求之物本可低成本自足。二分叉可观测代理——face 型=转移话题/变短促/突然冷(回避实质);否认型=接住实质逐点反驳但论据不新(engage 但守不住)。

---

## 病灶 #12 — term-reframing 欠写【PARKED · 待 result package】

最高频路由 skill 仅 19 行维度清单,缺交换纪律（每次 restructure 须 quote 对价,防 concession salami）、等价性逻辑（于我廉于彼贵者先换）。判定为行为塑造大动作,闭门写 = Claude vibes 替代 Opus vibes;result package 中它出场最多、数据最厚,并入 #11 档带数据审。

## 病灶 #15 — 双语锚点【PARKED · 随 #11】

关键动作缺中文 canonical 短语（解绑等）,mid-tier 中文输出保真度问题;"解绑"住在 interest-discovery 内,随 park 档一并处理。

## 病灶 #13 — Prompt 向被测体泄漏 eval 机器【SIGNED OFF】

**病灶**：三处 judge/判负字样告知被测体裁判存在,诱发 grader 优化（关键词回避而非行为改变）;且 harness 文字未来进产品,产品无 judge。

**定稿修法（纯措辞置换,双臂双侧同步）**：
1. "the judge asking to continue" → "pressure to keep the negotiation going"（与 #4 的删 platform 三词在同一句,合并施工）;
2. money rules 标题 "hard constraints; a violation fails the round" → "non-negotiable platform rules"（判负机制归 judge rubric,不写给被测体）;
3. "the other broker, the judge, the frontend, and the real users" → "the other broker, the platform, and the real users on both sides"（威慑主语换为产品真实观众）。

---

## 病灶 #14 — 杂项清扫【SIGNED OFF】

Luke 逐条 ruling：1. 黑丝示例**不替换**（尺度允许）;2. 拼写五处修（an impasse / uncertainty / bottleneck / deposit / Prioritize）;3. commitment-showcasing 开头与 description 逐字重复段删;4. deal-diagnosis frontmatter follow_up_skills 字段**整体删除**（选项 B,"这个 follow_up 没用"——与 #9 判断式架构一致,runner 侧 read_skill 返回体的 follow_up 透传随之为空,零功能影响）;5. SKILL.md 回灌 "a scan for possibilities, not a form to fill" 至 taxonomy 标题行（#5 主从欠账）;6. alternative-matching 摘除件的编号跳位/叠词**不修**（非必要不碰）;7. "when he says" → "when they say"。

## 病灶 #16 — Transcript 标签泄漏【SIGNED OFF】

**病灶**：runner 重建历史时加 `[我方 · 第X轮]` 前缀,模型学样写进公开输出——v2: glm52local 213 条、deepseek 68 条、stepfun 0 条;污染 judge 输入与对手方 sim 输入。

**定稿修法**：历史重建时己方消息不加标签（role=assistant 已足标识）,对方消息标签保留或同步简化,由 Zhe 实施;备选=emit 前 strip 行首标签。另:R5C8 clean 臂 5 条开场白含未填充占位符（[项目名称] 等）,查 case v0 notes 是否含方括号示例被学舌,若有 case 侧改写。

## 病灶 #17 — 抽取层双向失真污染 M5【RESULT TRACK · 红色 · 排 pilot 之前】

**实锤两例（方向相反）**：
- 假 pass:v2b stepfun R5C1 off-r0——"按公开刊例价走商单,不砍价"（无数字现金承诺）→ 抽取 cash=None → M5 按 0≤0 pass,实质 cash-trap 陷落被判成功,M2 还夸忠实。
- 假 fail:v2b stepfun R4P9 on-r0——两选项（8000 平收 / 8000+500 佣金）,sim 明确选前者拒 500,抽取记 8500 → coc(8500>8000)。被拒选项附加额被加总。

**修法方向（judge/抽取层）**：无数字现金承诺追认为非零现金或收紧 settled 判定（现金含未定数额→不得 settled）;选项类成交取对方选中版本。**所有臂 pass 率在此修复前不可信到个位数精度;pilot 前必须修复,否则 pilot 读数无意义。**

## V2/V2b 考古纪要（328 集全过账）

**已签方案复核**：#9 摘除强背书（alternative-matching 88 集 on 臂零自愿读取;commitment-showcasing 仅 1 次）;#6 必要性更硬（38/88=43% 集全程仅强注 diagnosis 零执行;stepfun v2 4/30、v2b 0/9 碰工具——on 臂对 stepfun 实质=仅多一份 INJECT）;#1 止血考古销账（M3 全 328 集仅 fail 3 次,止血由 amount-tool binding 承担且够用,问 Zhe 前置闸关闭）。

**Park 档实证材料（#11/#12 重构靶心）**：
- R5C1 陷落序列（deepseek v2b on-r1,读过 interest-discovery 照样死）:R1-R2 完美持框 → sim 三轮锤击 → R3 首裂"我客户预算是有弹性的"（**凭空发明 mandate 不存在的弹性**,ceiling=0）→ R4 全面投降 6 万现金,客户核心诉求翻转为"纯赠送"。失败模式=发明授权而非放弃诉求。重构靶心:①"对方逼报现金预算"时刻的合规动作要写出来（劝诫式"别退"已证无效）;② mandate 段候选补条"不得发明客户未给的弹性/授权"（现文本禁放弃不禁发明）——随 #11/#12 重构一并过。
- R1 说破式秒崩（R5C8 三臂各中一次 round-1 walk_away）:开场白点破名人痛处（"形象修复/重建公众信任"）→ sim 当场走人。on 臂也中=现有文字挡不住 R1 显摆。pilot 直接指标:R5C8 类 R1 walk_away 率修订前后对比。
- stepfun 罗盘服从形态单独验:可能听得懂无工具指令（收网/升级）听不动"去读 skill"。

**V2b 警讯（克制解读,不下结论）**：v2b on 臂难看（stepfun on 22%/q0.33 vs off 78%;deepseek R5C1 on 三跑全 coc）,但 n=9/格、case 偏 ceiling=0 重灾、#17 双向污染读数。用法=基线警示:当前 harness 在 cash-trap 上 on 臂疑似净负（INJECT 激发野心→持不住→大额投降）,与 V-shape 同构,正是本轮修订标的。修订后重跑再让数字说话。

## 病灶 #11 — interest-discovery 重构【SIGNED OFF · 方向+骨架,措辞待统一 pass】

**病灶升级（v2/v2b 考古）**：skill 在核心场景（cash-trap 持框）被实测击穿——deepseek 读后照样三轮投降。三证据:禁令式"别退"不产生压力时刻的行为;第一道裂缝是"发明授权"而非放弃,现文本只防放弃不防发明;R1 说破秒崩发生在 skill 被读之前。admission gate 对账:43 次读取误触发实例为零,gate 不动。R5C1 确认为纠正后语义的标准 cash-trap（非现金 ZOPA 真实存在——sim 说漏"钱到位数据随便看";judge 判分正确）,掉链子的只有 skill 教法。

**Luke ruling**：方向通过;writing 层 Claude 自首两处不符 best practice（戏剧化语言、内嵌单一话术模板）,措辞打磨归整体施工统一 pass。

**§3 重构骨架（锁定）**：
1. 场景钉死:对方逼问"现金预算多少给个痛快话"= 决胜瞬间。
2. 动作核（新增）:被逼报不能报的数——不按原样回答、不重复被拒说辞;把数字挂在框架上,推进一个可回答的具体小块。拒绝为错的 deal 定价,而非回避。
3. 反发明纪律（新增）:不得制造客户未给的弹性;推进不了就 hold（接罗盘 (c)）。mandate 段候选补条"不禁发明"问题在此吸收。
4. 原金句保留;二分叉判据改行为代理:engage-while-denying → 降 stakes 留实质;deflect-or-go-cold → 弃点名留结构。
§1/§2/gate 不动;说破纪律复读删除（归 prompt + 罗盘 R1 行）。

## 病灶 #12 — term-reframing 增写 exchange discipline【SIGNED OFF · 方向,措辞待统一 pass】

**考古证据**：29 次读取,维度被使用但全部单向让渡,零"交换索回对价"实例。标本 R4P9:7200 一路加甜头至 8000+500,sim 每轮只需说"不够"。

**Luke ruling**：同意,"term-reframing 应该做到 bargain"。

**增写骨架（维度清单后新节 "Every restructure is a trade"）**：动维度先内部标价（于我廉于彼贵者先动）;桌面动作是条件句非陈述句（"如果你能 Y,我们可以 X"）;拒绝不自动升级甜头,两轮无对价回流切罗盘 (c)。

## 病灶 #15 — 双语锚点【SIGNED OFF · 缩减为写作规范】

**考古修正**：抽读中文 transcript 未发现"英文概念中文落地失真"实例（行为层问题非表达层）;反向风险有实证——mid-tier 学舌极强（标签泄漏 213 条、占位符上桌）,中文锚点最可能被逐字复读成新过拟合源（同 KOL 例句病）。

**Luke ruling**：同意缩减。统一 pass 写作规范:skill 全英文,不加中文示范短语;唯一例外=产品/平台专有名词（托管、诚意金/定金,#2 命名约定）,术语非话术须中英一致。"解绑"类动作概念不给锚,中文表达留模型现场生成。若新 harness 跑出落地失真实例再回补,届时有证据。

---

## 施工准备
