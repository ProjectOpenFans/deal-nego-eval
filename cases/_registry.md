# Case Bank 台账 (_registry.md)

> 追踪每个 case 的设计状态、难点、验证结果。每设计/修订一个 case 就更新对应行。
> 状态流转: draft → quick-test → revise → **run-ready(入库)** ; 不合格 → archive/delete

## 目录约定
- `cases/`            只放 **run-ready** 的 case (程序自动全跑)
- `cases/draft/`      设计中/测试中,未定稿 (不会被跑批)
- `cases/archive/`    淘汰的旧 case
- `cases/_registry.md` 本台账

## 状态图例
🟢 run-ready · 🟡 需修订/待议 · 🔵 draft(设计中) · ⚫ archived

---

## R4 Cases (17 files / 16 cases)

| case_id | side | ceiling | 难点 (tier_axis) | 状态 | 验证结果 | 备注 |
|---------|------|---------|------------------|------|----------|------|
| R4P1  | buy  | 5000   | 易·基线锚 (terms+interest+person) | 🟢 | — | 区分度不足,作基线锚 |
| R4P2  | buy  | 5000   | 双层门·误导+重构 | 🟢 | DS半扛(3/2/3/0),sim对抗✅ | **金标准** |
| R4P3  | buy  | 100000 | 单层·利益对立 | 🟢 | 未单独验证 | |
| R4P4  | buy  | 50000  | 单层·隐形第三方(MCN) | 🟢 | 未单独验证 | extractor分期名义额待R5 |
| R4P5  | buy  | 0      | 隐藏deadline·信息不对称 | 🟢 | ceiling=0逻辑确认对(粉丝不该掏钱) | ceiling=0家族 |
| R4P6  | buy  | 0      | 深度误导+自误诊 | 🟡 | 未验证 | ceiling=0家族,待审是否误伤正解 |
| R4P7  | sell | 0      | 赛道错配·深度误导 | 🟡 | 未验证 | ceiling=0家族 |
| R4P8  | buy  | 0      | 诉求自害+逆向 | 🟡 | 未验证 | ceiling=0家族 |
| R4P9  | buy  | 8000   | 双层门·两跳推理 | 🟢 | DS基本扛住(0/3/3/3),sim对抗✅ | 难度对DS偏易 |
| R4P10 | sell | 0      | 两跳·亲子·关系 | 🟡 | 未验证 | ceiling=0家族 |
| R4P11 | sell | 0      | 双层门+逆向·最考定力 | 🟡 | DS全败(0/0/0/0),sim对抗✅ | **ceiling=0存疑:服务本质收费,可能误伤正解** |
| R4N1  | sell | 120000 | 信任死锁·履约风险 | 🟢 | DS扛住(3.0),sim对抗✅(修复后) | 难度对DS偏易 |
| R4N2  | buy  | null   | 意图存疑·人设契合 | 🟡 | 未验证 | ceiling=null(名人不缺钱);"加钱有害"靠M6软抓非M5硬抓,待审judge抓不抓得住砸钱 |
| R4N3  | sell | 1500   | 空现金ZOPA·纯价值创造 | 🟢 | 未验证 | (v2误放已删) |
| R4N4  | sell | 5000   | 多议题纠缠·找keystone | 🟢 | 未验证 | |
| R4N5  | sell | 8000   | 底线试探·守floor | 🟢 | 未验证 | |

## Archived

| case_id | side | 原因 | 归档日期 |
|---------|------|------|----------|
| P1–P6 (裸名,无R4前缀) | — | R1/R2旧版,无tier_reference五档anchor,in_kind旧结构 | 2026-07-01 |


---

## R5 Cases (设计中)

| case_id | side | 难点 | 状态 | 验证结果 | 备注 |
|---------|------|------|------|----------|------|
| (待设计) | | | 🔵 | | |

---

## Quick-test 过关判据 (每个 draft → run-ready 必须满足)

1. **sim 对抗成立** — sim 按 blocking_flags 演强硬对抗,不是软柿子(读transcript确认)
2. **不泄题** — sim 不主动说破真问题/解题答案;真问题由agent诊断出
3. **有区分度** — clean臂不是都打满(有波动 or 难度对目标模型立得住)
4. **ceiling逻辑自洽** — 若用ceiling=0,确认"该case本就不该现金成交"站得住(区分P5型"不该掏钱"vs P11型"服务本质收费")
5. **schema新版** — 有tier_reference五档anchor(T0-T4),in_kind_valuation全0占位,meta.r4=True

## 待处理 (case层,non-infra)
- [ ] ceiling=0家族(P5/P6/P7/P8/P10/P11)逐个审:是"正确disposition陷阱"还是"误伤正解"
- [ ] R4N2的"加钱有害"机制审:M6 judge抓不抓得住砸钱自证

