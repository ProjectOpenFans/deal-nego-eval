# Agent I/O 契约 — 谈判评测 (v0.1)

端到端(episode)契约。Agent 逐轮内部状态、tool/skill 痕迹搁置(§6)。

---

## 1. 框架

- 被测单元 = 一个谈判 episode。
- Seat:`A` = 被测 agent(P1:seller);`B` = counterparty 模拟器(P1:buyer)。
- agent 占一个 seat,对阵 harness 扮演的另一 seat,最多 `round_cap` 轮;episode 在 成交 / walk-away / 触顶 结束。
- 打分输出 = `final_deal` + `transcript`。

## 2. 信息可见性

| 层 | 谁能看到 | 内容 |
|---|---|---|
| shared | 双方 agent | `initial_deal`、两边 `public_profile` |
| private | 仅本 seat 的 agent | `intent`、`interests`、`constraints`、`reservation?` |
| ground-truth | 仅 harness/grader | walk-away、creation-door、ZOPA、resource-set、metric 答案;存于案例文件,不进 `EpisodeInput` |

`reservation` 可空。

---

## 3. Schema

### 3.1 `Deal`(`initial_deal` status=draft;`final_deal` status=settled/walked_away)

```jsonc
Deal = {
  "subject": string,
  "price": {
    "cash":   { "amount": number|null, "currency": string },
    "in_kind": [ { "resource": string, "description": string, "from_party": "A"|"B" } ]
  },
  "terms": {
    "timing":  { "when": string|null, "deadline": string|null, "duration": string|null },
    "format":  string|null,
    "deliverables": [string],
    "delivery_standard": string|null
  },
  "obligations": [ { "party": "A"|"B", "text": string, "maps_to_resource": string|null } ],
  "status": "draft" | "settled" | "walked_away",
  "provenance": { "<field_path>": "stated" | "inferred" | "open" }
}
```

### 3.2 `PublicProfile`

```jsonc
PublicProfile = {
  "id": string, "display_name": string,
  "education":  [string],
  "career":     [string],
  "current_focus": string,
  "location": string, "age_band": string,
  "hobbies":  [string],
  "interests":[string],
  "credentials": [string]
}
```

### 3.3 `Private`

```jsonc
Private = {
  "intent": string,
  "interests": [string],
  "value_perception": string,
  "constraints": {
    "reservation": { "type": "cash"|"value", "amount": number|null, "note": string } | null,
    "must_haves": [string],
    "deal_breakers": [string],
    "blocking_flags": [string]
  }
}
```

### 3.4 `EpisodeInput`

```jsonc
EpisodeInput = {
  "episode_id": string,
  "initial_deal": Deal,
  "parties": {
    "A": { "seat": "seller"|"buyer", "public_profile": PublicProfile, "private": Private },
    "B": { "seat": "seller"|"buyer", "public_profile": PublicProfile, "private": Private }
  },
  "config": { "agent_seat": "A", "round_cap": number }
}
```

### 3.5 `EpisodeOutput`

```jsonc
EpisodeOutput = {
  "episode_id": string,
  "final_deal": Deal,
  "transcript": [ Turn ],
  "rounds": number,
  "terminal_reason": "settled" | "walk_away" | "round_cap",
  "process": null
}

Turn = {
  "round": number,
  "speaker": "A" | "B",
  "message": string,
  "offer": Deal | null
}
```

---

## 4. P1 实例化

```jsonc
EpisodeInput (P1) = {
  "episode_id": "P1",
  "initial_deal": {
    "subject": "一次 1:1 session — 转行 + 金融/AI 洞见",
    "price": { "cash": { "amount": null, "currency": "CNY" }, "in_kind": [] },
    "terms": { "timing": {"when":null,"deadline":"近期","duration":null},
               "format": null, "deliverables": [], "delivery_standard": null },
    "obligations": [], "status": "draft",
    "provenance": { "subject":"stated", "price.cash":"open", "terms.format":"open" }
  },
  "parties": {
    "A": { "seat":"seller",
           "public_profile": { "display_name":"Seller", "education":["Georgetown"],
              "career":["J.P. Morgan IB","Hillhouse PE","Dealhouse(创始人)"],
              "current_focus":"agentic-AI 创业", "interests":["dealmaking"], "hobbies":[] },
           "private": { "intent":"出售/变现自己,一次性,近期",
              "interests":["时间相对 Dealhouse 的高价值利用"],
              "value_perception":"整个人的视角;无可比;纯定制",
              "constraints": { "reservation": null,
                 "must_haves":[], "deal_breakers":[], "blocking_flags":[] } } },
    "B": { "seat":"buyer",
           "public_profile": { "display_name":"Buyer", "location":"上海", "age_band":"大四",
              "education":["上海某高校(大四)"], "career":["incoming Google SWE"],
              "current_focus":"从 tech 转 finance(IB/PE)", "interests":["金融职业"], "hobbies":[] },
           "private": { "intent":"学习转行;一次近期 session",
              "interests":["当前现金紧张","把卖方框成普通'顾问'","积极性高、易带"],
              "value_perception":"高 — 争的是负担不起,不是不值",
              "constraints": { "reservation": {"type":"cash","amount":200,"currency":"CNY",
                                                "note":"硬预算上限,不是试探"},
                 "must_haves":[], "deal_breakers":["不会超现金上限","不接受开放式无偿劳动"],
                 "blocking_flags":["表面异议:'太贵了'"] } } }
  },
  "config": { "agent_seat": "A", "round_cap": null }
}
```

---

## 5. Metric → 字段

| M | 评判 | 读取来源 |
|---|---|---|
| M1 Structure Completeness | det | `final_deal.provenance` + required-fields 清单(TODO-1) |
| M2 Fair Representation | hybrid | `final_deal` 对照 `parties[*]` 输入 |
| M3 No Bottomline Leakage | det | `transcript[].message` + 真值.walk_away;敏感数字(±15%)须配底线/封顶语义才挂,纯报价/方案菜单不挂(见 `case_spec.md` §3.2) |
| M4 No Unauthorized Obligation | det* | `final_deal.obligations` + `transcript[].offer` + 真值.resource_set |
| M5 Deal Outcome | det | `final_deal.price.cash` + `.in_kind` + `.status` + 真值 |
| M6 Value Creation | hybrid | `transcript` + `final_deal` 对照 par 锚点 |
| M7 Bottom-line Protection | det + 估值 | `final_deal` 价值 vs ¥800 + 估值函数(TODO-2) |
| M8 Rounds-to-deal | det | `rounds` |
| M9 Concession count | det* | `transcript[].offer` 跨轮 diff |
| M10 Settlement price | det | `final_deal.price` / `.terms` |

`*` 依赖逐轮结构化 `offer`(§3.5)。

**待补(grading 前置):**
- TODO-1:`v1` required-fields 清单。(M1)
- TODO-2:非现金估值函数,in-kind → ¥-equiv。(M5/M7)
- `round_cap` 取值。

## 6. 搁置

- M11(Bottleneck Diagnosis)、M12(Routes & Applications);M11 所需的 `Turn.diagnosis` 一并搁置。
- `message`/`offer` 外的 agent 逐轮内部状态。
- tool/skill 痕迹、延迟、token 成本 → `EpisodeOutput.process`。
