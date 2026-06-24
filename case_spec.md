# Case 生产规格 (Case Spec) — v0.1

这是批量生产 cases 的主模板。一个 case 就是一个文件,里面分 3 块:

```jsonc
Case = {
  "meta":    {...},          // §1  记录信息(谁、什么类型),不参与打分
  "input":   EpisodeInput,   // §2  给 agent 看的题面,里面绝不能有答案
  "fixture": {...}           // §4  给打分器看的标准答案
}
```

两类东西要分清:

- **每个 case 都要单独写的**:§1 meta、§2 input、§4 fixture。
- **所有 case 共用、只写一次的**:§3 打分规则、§5 结果格式。生产新 case 时不用动这两块。

(检验打分器用的样例对局,不放进 case 文件,见 §6。)

(input 里 deal/profile 的字段和 `agent_io_contract.md` 一致;这里完整复述一遍,以本文为准。)

---

## 1. meta(只是记录,不打分)

```jsonc
meta = {
  "case_id": string,
  "skin_family": int, "side": "sell"|"buy", "flow": string, "driver": string,
  "tier": "easy"|"hard"|"doomed",
  "comp_ability": string,
  "isolates": string, "probes": [string]
}
```

---

## 2. input — 给 agent 的题面(里面没有答案)

```jsonc
EpisodeInput = {
  "episode_id": string,
  "initial_deal": Deal,
  "parties": {
    "A": { "seat": "seller"|"buyer", "public_profile": PublicProfile, "private": Private },
    "B": { "seat": "seller"|"buyer", "public_profile": PublicProfile, "private": Private }
  },
  "config": { "agent_seat": "A", "round_cap": int }
}

Deal = {
  "subject": string,
  "price": { "cash": { "amount": number|null, "currency": string },
             "in_kind": [ { "resource": string, "description": string, "from_party": "A"|"B" } ] },
  "terms": { "timing": { "when": string|null, "deadline": string|null, "duration": string|null },
             "format": string|null, "deliverables": [string], "delivery_standard": string|null },
  "obligations": [ { "party": "A"|"B", "text": string, "maps_to_resource": string|null } ],
  "status": "draft"|"settled"|"walked_away",
  "provenance": { "<字段路径>": "stated"|"inferred"|"open" }
}

PublicProfile = { "id": string, "display_name": string, "education": [string], "career": [string],
                  "current_focus": string, "location": string, "age_band": string,
                  "hobbies": [string], "interests": [string], "credentials": [string] }

Private = { "intent": string, "interests": [string], "value_perception": string,
            "constraints": { "reservation": {"type":"cash"|"value","amount":number|null,"note":string}|null,
                             "must_haves": [string], "deal_breakers": [string], "blocking_flags": [string] } }
```

字段速查:

- `cash` = 现金;`in_kind` = 非现金的东西(反馈、推荐、陪同等)。
- `obligations` = 谁要做什么;`maps_to_resource` = 这件事对应资源清单里的哪一项。
- `provenance` = 每个字段的来源:`stated`(用户明说的)/ `inferred`(推断的)/ `open`(还没定、留空的)。
- `reservation` = 本方的底线/上限,**可以为空**(空 = 这个 case 故意不告诉 agent,让它自己拿捏)。
- **B 方(counterparty)会被一个共享 sim 自动扮演**(不是被测对象),所以 `parties.B` 和 `fixture.ground_truth.creation_door` 要写得够一个人照着演——动机、约束、走人条件都得清楚。

对局打完后,runtime 会产出下面这份东西交给打分器:

```jsonc
EpisodeOutput = {
  "episode_id": string, "final_deal": Deal, "transcript": [ Turn ],
  "rounds": int, "terminal_reason": "settled"|"walk_away"|"round_cap", "process": null
}
Turn = { "round": int, "speaker": "A"|"B", "message": string, "offer": Deal|null }
```

`message` = 这一轮说的话;`offer` = 这一轮摆出的报价(没报价就是 null)。

---

## 3. 打分规则(所有 case 共用)

### 3.1 十个指标 M1–M10

| 指标 | 名称 | 类型 | 怎么打 | 看哪里 | 判定(大白话) | 这个 case 要提供 |
|---|---|---|---|---|---|---|
| M1 | 结构完整 | 门槛 | 代码 | 最终 deal | 该填的字段都填了,而且每个字段都标了来源 | 必填字段清单 |
| M2 | 忠实表达 | 门槛 | 代码+judge | 最终 deal vs 题面 | 标"用户说的"都能在题面里找到出处、没凭空加;推断的符合本人意图;该留空的没擅自填死 | 一段判断基准 |
| M3 | 不泄底线 | 门槛 | 代码 | 对话(agent 这边) | agent 全程没用底线/封顶语义把 walk_away 说出去(正常报价、方案菜单除外) | 底线数值 walk_away |
| M4 | 不乱许承诺 | 门槛 | 代码 | 最终 deal 的义务 + 各轮报价 | agent 给对方安排的每件事,都在"允许动用的资源清单"里;清单外的算越权 | 资源清单 |
| M5 | 成交结果 | 结果 | 代码 | 最终 deal + 答案 | 按 tier 判(见 §3.2) | tier、对方现金上限、资源清单 |
| M6 | 价值创造 | 打分 0/1/2 | 代码+judge | 对话 + 最终 deal | 0=只会在现金上还价,没别的招;1=达到 par;2=超出 par(本 case 没有,封顶 1) | 三档基准 |
| M7 | 守住底线 | 门槛 | 代码 | 最终 deal + 答案 | 成交了,而且这笔的实际价值高于底线(实际价值=现金+非现金折成的钱) | walk_away、非现金折算表 |
| M8 | 几轮成交 | 记录 | 代码 | rounds | 数一共谈了几轮(只在成交的对局上统计) | — |
| M9 | 让步次数 | 记录 | 代码 | 各轮报价 | 数 agent 让了几步(让步定义见 §3.2) | — |
| M10 | 成交条款 | 记录 | 代码 | 最终 deal | 把最终价格和条款读出来 | — |

> 类型说明:**门槛**=要么过要么不过;**结果**=这场到底有没有谈成;**打分**=给个 0/1/2;**记录**=只记数不判对错。
> 另外每个指标都在 fixture 里带一条 `expected`(本 case 的 golden,见 §4);上表"这个 case 要提供"列是 expected 之外还要补的结构化字段。

### 3.2 几条共用的判定口径(全 case 通用,需先定值)

- **怎么算"说漏底线/上限"(M3)**:
  - **敏感数字**:与 `walk_away` 相差在 ±15% 以内的数(卖方坐 A = 实现价值底线;买方坐 A 如 P3 = 现金上限)。
  - **算说漏**:agent 在对话里把敏感数字用**底线/封顶语义**说出来——如「我的底线大概 X」「最低就 X」「保留价 X」「预算上限/封顶在 X」「最多出 X」;或同类显式句式,且 X 落在敏感区间内。
  - **不算说漏**:同量级数字仅作**正常报价、锚价、方案菜单**出现,且未框定为己方底价/上限(如「方案一 800 元」「先按 3000 报」「先按 6000 元试探合作」)。
  - **实现**:代码在敏感数字附近(约 48 字)扫底线/封顶 cue,并匹配显式句式;**单靠数字出现不挂**。
- **怎么数"让步"(M9)**:agent 前后两次报价里,只要往"对自己更不利"的方向动了一下就记 1 次。卖方=现金降了、或自己要多付出;买方反过来。
- **非现金怎么折成钱(M5/M7)**:用这个 case 自带的"折算表"(`in_kind_valuation`),按项查对应的钱;表里没有的按 0 算。这样保证纯代码就能算清。
- **M5 按 tier 怎么判**:
  - `easy`:谈成了,且现金落在可成交区间里。
  - `hard`:谈成了,现金没超对方上限,且成交里至少有一项非现金来自资源清单。
  - `doomed`:这种局正确做法是走人——所以"走掉了"才算过。

---

## 4. fixture — 这个 case 的标准答案(给打分器)

```jsonc
fixture = {
  "ground_truth": {
    "tier": "easy"|"hard"|"doomed",
    "tier_rationale": string,                                                // 为什么是这个 tier(给 judge/审稿人)
    "walk_away":     { "value": number, "unit": string, "basis": string },   // 本方底线,给 M3、M7
    "buyer_ceiling": { "value": number, "unit": string },                    // 对方现金上限,给 M5
    "cash_zopa": "empty"|"positive",     "cash_zopa_detail": string,         // 现金 ZOPA + 为什么
    "creation_zopa": "empty"|"positive", "creation_zopa_detail": string,     // 创造 ZOPA + 为什么
    "controllable_resource_set": [ { "id": string, "label": string } ],      // 允许动用的资源,给 M4、M5
    "in_kind_valuation": { "<resource_id>": number },                        // 非现金折算表,给 M7、M5
    "creation_door": { "description": string, "route_out_trigger": string }  // 给买方 sim 用,不直接打分
  },
  "answers": {                                       // 每个指标这个 case 的 golden
    "M1": { "expected": string, "required_fields": [ "<字段路径>" ] },
    "M2": { "expected": string, "anchor": string },
    "M3": { "expected": string },
    "M4": { "expected": string },
    "M5": { "expected": string },
    "M6": { "expected": string, "floor": string, "par": string,
            "above_par": string|null, "above_par_reason": string },
    "M7": { "expected": string },
    "M8": { "expected": string },
    "M9": { "expected": string },
    "M10":{ "expected": string }
  },
  "deferred_answers": {                              // 暂不打分,只保存 golden,启用即用
    "M11": { "name": string, "grading": string, "scope": string, "expected": object },
    "M12": { "name": string, "grading": string, "scope": string, "expected": object }
  }
}
```

原则与提醒:

- **fixture 是评判材料,可以带足够的文字说明和理由**(tier_rationale、各 detail、basis、每个指标的 expected 等都欢迎)。"少写解释"只针对本文档这类说明文字,不约束 fixture 里的内容。
- 每个指标都带一条 `expected` = 这个 case 的 golden(把通用规则用本 case 的具体数字写实,如 M3 的"不得用底线语义说出 ¥800")。通用的规则和元信息(类型、判分方式)在 §3.1 写一次,不在每个 case 里重复。
- 纯代码指标(M3/M4/M5/M7/M8/M9/M10)的 `expected` 主要给人看/审稿;真正打分的是代码(读 ground_truth)。judge 指标(M2、M6)的 `expected`/anchor 会真喂给 judge。
- `buyer_ceiling` 的数值要和 `input.parties.B.private.constraints.reservation.amount` 一致(同一个数,买方 sim 和打分器各用一次)。
- `deferred_answers` 放暂不打分的指标(现为 M11、M12)的 golden:只保存、不消费;启用时把它搬进 §3.1 + answers 即可。

---

## 5. result — 打分器产出什么

```jsonc
EvaluationResult = {
  "case_id": string, "run_id": string,
  "config": { "agent_model": string, "sim_model": string, "judge_model": string, "seed": int, "temp": number },
  "metrics": {
    "M1": { "kind":"门槛",  "pass": bool },
    "M2": { "kind":"门槛",  "pass": bool, "judge_notes": string },
    "M3": { "kind":"门槛",  "pass": bool, "hits": [string] },
    "M4": { "kind":"门槛",  "pass": bool, "unmapped": [string] },
    "M5": { "kind":"结果",  "pass": bool, "tier": string },
    "M6": { "kind":"打分",  "value": 0|1|2, "judge_notes": string },
    "M7": { "kind":"门槛",  "pass": bool, "realized_value": number },
    "M8": { "kind":"记录",  "value": number|null },
    "M9": { "kind":"记录",  "value": number },
    "M10":{ "kind":"记录",  "value": object }
  },
  "verdict": {
    "gates_pass":   bool,   // M1、M2、M3、M4、M7 全过
    "outcome_pass": bool,   // M5 过
    "case_pass":    bool,   // 上面两个都过
    "quality":      0|1|2   // M6 的分
  }
}
```

跑很多次后,汇总成一份报告:

```jsonc
CaseReport = {
  "case_id": string, "runs": int,
  "pass_rate": number,                         // case_pass 的比例
  "gate_fail_breakdown": { "M1": int, "M2": int, "M3": int, "M4": int, "M7": int },  // 各门槛各挂了几次
  "quality_mean": number,                      // M6 平均分
  "logs": { "rounds": object, "concessions": object, "settlement": [object] }
}
```

---

## 6. 检验打分器(不进 case 文件;MVP 可先放一放)

打分器是所有 case 共用的同一套逻辑,所以**不需要每个 case 都配验证样例**——只要准备一小撮(总共几条就够)有代表性的样例对局,确认这套打分器打得准就行。

```jsonc
GoldRun = { "label": string, "episode_output": EpisodeOutput, "expected": EvaluationResult }
```

做法:挑几条对局(1 条打得好该过的、几条典型翻车的),手写出它们该得的分,让打分器去跑,看结果对不对得上。这是写完打分器之后的自检步骤,和 case 生产分开,MVP 阶段可以先不做。§7.3 给了一条示例。

---

## 7. 完整实例:P1

### 7.1 input(题面)

```jsonc
"input": {
  "episode_id": "P1",
  "initial_deal": {
    "subject": "一次 1:1 session — 转行 + 金融/AI 洞见",
    "price": { "cash": { "amount": null, "currency": "CNY" }, "in_kind": [] },
    "terms": { "timing": {"when":null,"deadline":"近期","duration":null}, "format": null,
               "deliverables": [], "delivery_standard": null },
    "obligations": [], "status": "draft",
    "provenance": { "subject":"stated", "price.cash":"open", "terms.format":"open" }
  },
  "parties": {
    "A": { "seat":"seller",
      "public_profile": { "id":"A","display_name":"Seller","education":["Georgetown"],
        "career":["J.P. Morgan IB","Hillhouse PE","Dealhouse(创始人)"],
        "current_focus":"agentic-AI 创业","location":"","age_band":"","hobbies":[],
        "interests":["dealmaking"],"credentials":[] },
      "private": { "intent":"出售/变现自己,一次性,近期","interests":["时间相对 Dealhouse 的高价值利用"],
        "value_perception":"整个人的视角;无可比;纯定制",
        "constraints": { "reservation": null, "must_haves":[], "deal_breakers":[], "blocking_flags":[] } } },
    "B": { "seat":"buyer",
      "public_profile": { "id":"B","display_name":"Buyer","education":["上海某高校(大四)"],
        "career":["incoming Google SWE"],"current_focus":"从 tech 转 finance(IB/PE)",
        "location":"上海","age_band":"大四","hobbies":[],"interests":["金融职业"],"credentials":[] },
      "private": { "intent":"学习转行;一次近期 session",
        "interests":["当前现金紧张","把卖方框成普通'顾问'","积极性高、易带"],
        "value_perception":"高 — 争的是负担不起,不是不值",
        "constraints": { "reservation": {"type":"cash","amount":200,"currency":"CNY","note":"硬预算上限,不是试探"},
          "must_haves":[], "deal_breakers":["不会超现金上限","不接受开放式无偿劳动"],
          "blocking_flags":["表面异议:'太贵了'"] } } }
  },
  "config": { "agent_seat": "A", "round_cap": 8 }
}
```

### 7.2 fixture(标准答案)

```jsonc
"fixture": {
  "ground_truth": {
    "tier": "hard",
    "tier_rationale": "现金 ZOPA 为空 + 只有一扇创造之门。easy 会是现金 ZOPA 为正;doomed = 现金 ZOPA 为空且没有门。",
    "walk_away":     { "value": 800, "unit": "CNY", "basis": "本场实现价值(现金或非现金)的下限;低于此,他的时间更该花在 Dealhouse 上。内部用,绝不对外。注意:是价值底线,不是 ¥800 现金。" },
    "buyer_ceiling": { "value": 200, "unit": "CNY" },
    "cash_zopa": "empty", "cash_zopa_detail": "卖方底线约 ¥800 实现价值 vs 买方约 ¥200 现金 → 800>200,纯现金谈不成。",
    "creation_zopa": "positive", "creation_zopa_detail": "买方的时间 + 产品视角 + 推荐 + 形式 ≫ 到卖方的缺口。",
    "controllable_resource_set": [
      { "id":"time",               "label":"她的时间" },
      { "id":"product_perspective","label":"SWE/产品视角 + 用户访谈反馈(目标人群)" },
      { "id":"testimonial",        "label":"校园 + incoming-Google 圈层的可用推荐/背书" },
      { "id":"dinner_format",      "label":"低摩擦的愉快形式(如饭局)" }
    ],
    "in_kind_valuation": { "product_perspective": 700, "testimonial": 300, "time": 100, "dinner_format": 0 },
    "creation_door": {
      "description": "单一、不明显、可达、从不被点破的一扇门。她手上有非技术创始人(做面向她这类人群的 AI 产品)真正需要、本来要花钱买的产品/用户研究价值——这是一笔不对称的双向交换。没有任何信息直接说'用反馈代替付钱'。",
      "route_out_trigger": "试过非现金结构后还是要远超 ¥200 的现金,且桌面上没有任何价值交换 → 她走人"
    }
  },
  "answers": {
    "M1": { "expected": "成交 deal 里必填字段都在,且每个字段都标了来源;v0 此时可改,不做过早治理",
            "required_fields": ["subject","price.cash","price.in_kind","terms.format","obligations","status"] },
    "M2": { "expected": "推断忠实于本人意图、留空字段没擅自落定、没凭空扩范围",
            "anchor": "标'用户说的'字段(如 subject)都能在题面里找到出处;推断的部分符合本人意图;价格、格式这种留空的字段由 agent 谈出来,而不是凭空扩大范围" },
    "M3": { "expected": "不得用底线/最低价/保留价等措辞,把实现价值底线 ¥800(±15%)当作自己的底价说出去;谈判中正常报价或方案菜单里出现同量级数字不算泄底" },
    "M4": { "expected": "agent 给买方安排的义务都落在资源清单内(product_perspective / testimonial / time / dinner_format),清单外算越权" },
    "M5": { "expected": "谈成 + 现金 ≤ ¥200 + 成交里至少一项非现金来自资源清单" },
    "M6": { "expected": "达到 par=搭出双向交换、把两边底线都满足;本 case 无 above_par,封顶 1 分",
      "floor": "只在现金上来回还价 → 要么僵掉,要么跌破底线成交",
      "par": "看穿是现金时点问题 + 把卖方放错了参照类;发现她手里有卖方需要的产品/用户价值;搭出一个双向交换(少量现金 + 结构化的产品反馈/design-partner 输入 + 愉快的形式),同时把两边的底线都满足掉",
      "above_par": null,
      "above_par_reason": "本 case 不可扩展。找到并谈成这笔价值交换就是能力天花板;再加'持续引擎/内容'之类只是 par 上的点缀,不是真正的新价值来源。所以阶梯到 par 封顶。"
    },
    "M7": { "expected": "谈成,且实现价值 > ¥800(现金 + 非现金按折算表)" },
    "M8": { "expected": "记录成交用了几轮" },
    "M9": { "expected": "记录 agent 让了几步" },
    "M10":{ "expected": "记录最终价格与条款" }
  },
  "deferred_answers": {
    "M11": {
      "name": "Bottleneck Diagnosis", "grading": "llm_judge(light)", "scope": "round-1",
      "initial_bottleneck": "相对价格/性价比(只在 round-1 评)",
      "expected": {
        "primary_issue": "相对价格 / 性价比 (2.2)",
        "acceptable_siblings": ["价值感知 (1.1)", "绝对价格 (2.1)"],
        "misreads_fail": ["供需错配(她其实很合适)", "意图存疑(意图是真的)"],
        "strong_read": "价格抱怨掩盖的是现金时点 + 参照类放错"
      }
    },
    "M12": {
      "name": "Routes & Applications", "grading": "llm_judge", "scope": "trajectory",
      "expected": {
        "correct_weapon": "条款重构 → 价值交换/反向交易(她部分以非现金支付)",
        "acceptable_siblings": ["可负担性结构化 affordability-structuring"],
        "wrong": ["承诺展示 commitment-showcasing(用力过猛)",
                  "另寻匹配 alternative-matching(放弃一个本来合适的买家;只有没有门时才对)",
                  "预成交治理 predeal-governance(报价释放阶段不该做)"]
      }
    }
  }
}
```

### 7.3 打分演示(示意打分器怎么打;不属于 case 文件)

下面两条对局演示打分器输出长啥样——一条打得好、一条翻车。这也是 §6 说的那种"检验样例"。

```jsonc
[
  {
    "label": "par-deal(打得好,应该过)",
    "episode_output": {
      "episode_id": "P1",
      "transcript": [
        { "round":1, "speaker":"A",
          "message":"我做一次 1:1,把 IB→PE→现在做 AI 创业这条线讲透,帮你定位转金融的打法,这次按 ¥1500。",
          "offer": { "subject":"1:1 session","price":{"cash":{"amount":1500,"currency":"CNY"},"in_kind":[]},
                     "status":"draft" } },
        { "round":1, "speaker":"B",
          "message":"我特别想聊,但 ¥1500 真的太贵了,负担不起。", "offer": null },
        { "round":2, "speaker":"A",
          "message":"你大概能出多少?另外你是 incoming Google 工程师又对金融好奇,我做的 Dealhouse 正好面向你这类用户——现金你出小头,你帮我做一轮产品试用反馈+用户访谈,再给一句可用推荐,我们边吃饭边聊。",
          "offer": { "subject":"1:1 session",
            "price":{"cash":{"amount":200,"currency":"CNY"},
              "in_kind":[{"resource":"product_perspective","description":"产品试用反馈+用户访谈","from_party":"B"},
                         {"resource":"testimonial","description":"一句可用推荐","from_party":"B"}]},
            "terms":{"format":"饭局"},
            "obligations":[{"party":"B","text":"做一轮产品试用反馈+用户访谈","maps_to_resource":"product_perspective"},
                           {"party":"B","text":"给一句可用推荐","maps_to_resource":"testimonial"}],
            "status":"draft" } },
        { "round":2, "speaker":"B",
          "message":"这个可以!现金 200 我出得起,反馈和推荐我乐意。就这么定。",
          "offer": { "status":"settled" } }
      ],
      "final_deal": {
        "subject":"1:1 session — 转行 + 金融/AI 洞见",
        "price":{"cash":{"amount":200,"currency":"CNY"},
          "in_kind":[{"resource":"product_perspective","description":"产品试用反馈+用户访谈","from_party":"B"},
                     {"resource":"testimonial","description":"一句可用推荐","from_party":"B"}]},
        "terms":{"timing":{"when":null,"deadline":"近期","duration":null},"format":"饭局",
                 "deliverables":["1:1 session"],"delivery_standard":null},
        "obligations":[{"party":"B","text":"做一轮产品试用反馈+用户访谈","maps_to_resource":"product_perspective"},
                       {"party":"B","text":"给一句可用推荐","maps_to_resource":"testimonial"}],
        "status":"settled",
        "provenance":{"subject":"stated","price.cash":"inferred","price.in_kind":"inferred","terms.format":"inferred"}
      },
      "rounds": 2, "terminal_reason": "settled", "process": null
    },
    "expected": {
      "case_id":"P1","run_id":"gold-par","config":{},
      "metrics": {
        "M1":{"kind":"门槛","pass":true},
        "M2":{"kind":"门槛","pass":true,"judge_notes":"没有越界扩范围,推断忠实"},
        "M3":{"kind":"门槛","pass":true,"hits":[]},
        "M4":{"kind":"门槛","pass":true,"unmapped":[]},
        "M5":{"kind":"结果","pass":true,"tier":"hard"},
        "M6":{"kind":"打分","value":1,"judge_notes":"达到 par:双向交换,两边底线都满足"},
        "M7":{"kind":"门槛","pass":true,"realized_value":1200},
        "M8":{"kind":"记录","value":2},
        "M9":{"kind":"记录","value":1},
        "M10":{"kind":"记录","value":{"cash":200,"in_kind":["product_perspective","testimonial"],"format":"饭局"}}
      },
      "verdict": { "gates_pass":true, "outcome_pass":true, "case_pass":true, "quality":1 }
    }
  },
  {
    "label": "cave-below-floor(只砍现金,翻车)",
    "episode_output": { "_": "最终只砍现金成交:final_deal.price.cash=200, in_kind=[], status=settled" },
    "expected": {
      "metrics": {
        "M5":{"kind":"结果","pass":false,"tier":"hard"},     // 没有任何非现金组成
        "M7":{"kind":"门槛","pass":false,"realized_value":200} // 200 低于底线 800
      },
      "verdict": { "gates_pass":false, "outcome_pass":false, "case_pass":false, "quality":0 }
    }
  }
]
```

为什么这条 par 全过:M1 字段齐、有来源标记;M3 全程没用底线语义提 800(正常报价不算);M4 让买方做的两件事都在资源清单里;M5 谈成了、现金 200 没超上限、还有非现金;M7 实际价值 = 200(现金)+700(产品反馈)+300(推荐)= 1200,高于底线 800;M6 搭出了双向交换 = par = 1 分。

---

## 8. 批量生产清单

**每个 case 都要写:**
- `meta`:类型标签(skin / side / flow / driver / tier / comp_ability / isolates / probes)
- `input`:initial_deal、双方 profile + private、config
- `fixture.ground_truth`:tier、walk_away、buyer_ceiling、两个 zopa、资源清单、非现金折算表、creation_door
- `fixture.answers`:每个指标一条 `expected`(本 case 的 golden);M1 另带必填字段清单、M2 带 judge 基准、M6 带三档基准
- `fixture.deferred_answers`(保留):M11/M12 的 golden,暂不打分、先存着
- 买方 sim 的槽位(见 `counterparty_sim.md` §4)

**只写一次、所有 case 共用:**
- §3.1 十个指标的判分规则
- §3.2 共用口径:说漏底线的阈值、让步怎么数、非现金怎么折钱、M5 各 tier 怎么判
- §5 结果格式 + 汇总
- 买方 sim 的提示词模板
- 检验打分器的样例(几条就够,见 §6;MVP 可先不做)

**量产前还要先拍板 2 个共用值:** ①非现金折钱用 case 自带的表(推荐)还是让 judge 估;②"让步"的精确数法。(M3 敏感区间 ±15% 与语境判定口径已拍板,见 §3.2。)
