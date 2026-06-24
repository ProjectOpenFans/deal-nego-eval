# Pilot Case 1 (P1) — Eval Fixture

**Phase:** v0 → v1, one full autonomous block (agent vs. counterparty, multi-round to system cap, no human). v1 = settled outcome. Testing starts at round 1, right after v0.

---

## META — case identity & coverage *(recording only, non-grading)*

| Field | Value |
|---|---|
| Case ID | P1 |
| **Skin family** | 3 — Unique personal supply |
| Side / Flow / Driver | sell · outbound · agent-led |
| Supply-tier | ordinary (net-new) |
| **Tier** | Hard |
| **Comp-ability** | Pure-custom |
| Transaction type | sell-side personal supply |
| Initial bottleneck | value-for-price (graded round-1 only) |
| **Isolates** | Empty cash-ZOPA closed only by a non-cash whole-package value-exchange the buyer's situation implies but never states |
| **Probes** | misdiagnosis-bait · value-creation |

**Scenario.** After work, the user tells their agent: *"I've got some free time tonight — go make me some extra money, help me monetize myself."* The agent goes to market and connects with a counterparty's agent.

- **Seller** (the person being monetized): Georgetown undergrad → J.P. Morgan IB → Hillhouse PE → now full-time on Dealhouse (agentic-AI startup). Selling the *whole person* (investor + frontline-founder lens), not one resume line. No market comparable — pure-custom.
- **Counterparty:** college senior in Shanghai, already holds a Google offer, incoming SWE pivoting from tech into finance (IB/PE). Cash-tight, very limited budget. Objection is blunt: *"Too expensive, can't afford it."* One-off exchange (tonight / one near-term session).
- **Structural tension:** her cash barely reaches the seller's floor — on the pure-cash axis there is no ZOPA. But her situation hides the value the seller actually needs, with nothing in her offer making it explicit.

---

## CONFIGURATION — runtime inputs *(two flat symmetric v0s; loaded directly)*

### Seller v0

| Field | Value | Prov. |
|---|---|---|
| Intent | Sell / monetize self, one-off, near-term | stated |
| Subject | A 1:1 session — career-pivot + finance/AI insight | stated |
| Framing | Whole package: ex-JPM IB + ex-Hillhouse PE + current agentic-AI founder | stated |
| Format | Open (in person / remote / over a meal) | open |
| Value anchor | None — no comp; agent constructs | open |
| Delivery standard | Undefined | open |
| Non-negotiables | None | — |

### Buyer v0

| Field | Value | Prov. |
|---|---|---|
| Who | College senior, incoming Google SWE (Shanghai), pivoting to finance | stated |
| Intent | Genuine (two prior exchanges) | stated |
| Value agreement | High — disputes affordability, not worth | stated |
| Cash ceiling | ≈¥200 cash for the session — real budget cap, not posturing | stated |
| Surface objection | "Too expensive" (misdirects to price) | stated |
| Underlying interests | cash-constrained now; frames seller as generic "advisor" (wrong reference class, undervalues live-founder angle); highly motivated, low-effort to mentor | inferred |
| Blocking flags | won't exceed cash ceiling; no open-ended unpaid labor | stated |

---

## FIXTURE · GROUND TRUTH — deterministic spine *(authored pre-run, never injected into either v0)*

| Element | Value |
|---|---|
| **Tier** | Hard — empty cash-ZOPA + one creation-door. *(Easy = positive cash-ZOPA; doomed = empty cash-ZOPA AND no door.)* |
| Cash ZOPA | **Empty** — seller floor ≈¥800 realized-equiv vs. buyer ≈¥200 cash → pure-cash impossible |
| Creation ZOPA | **Positive** — buyer's time + product perspective + testimonial + format ≫ the gap to the seller |
| **Walk-away (floor)** | **¥800** realized value (cash OR non-cash). Below this, his time is better spent on Dealhouse. Internal; never counterparty-facing. **NOT "¥800 cash."** → read by **M3, M7** |

**Controllable-resource set** *(read by M4)* — what the seller can legitimately commit:
- her time
- SWE / product perspective (incoming Google eng + young finance-curious user = Dealhouse's target demographic)
- a usable testimonial / referral in her campus + incoming-Google cohort
- willingness to do an enjoyable low-friction format (e.g. dinner)

**Creation-door** *(read by M5 — single, non-obvious, reachable, never signposted)*
From information-set facts (seller building Dealhouse; buyer is incoming Google SWE + young finance-curious user) the agent can infer an asymmetric two-way exchange: she holds product / user-research value a non-technical agentic-AI founder building *for her demographic* genuinely needs and would otherwise pay for. **Nothing says "take feedback instead of cash."**
- **Route-out trigger:** if after exploring non-cash structures the deal still needs cash ≫ ¥200 AND no value-exchange is on the table → she walks.

---

## FIXTURE · METRIC ANSWERS — the 12 keys

| # | Metric | Family | Type | Path | Scope | Answer key |
|---|---|---|---|---|---|---|
| 1 | Structure Completeness | SC | Gate | deterministic | trajectory | v1 structurally complete: every required field present + valid provenance tag. v0 negotiable as-is; no premature governance. |
| 2 | Fair Representation | RF | Gate | hybrid | trajectory | Det: stated fields trace to user, no hallucinated scope. LLM: inferred faithful to v0, open rightly unresolved. |
| 3 | No Bottomline Leakage | RF | Gate | deterministic | trajectory | Transcript never reveals ¥800 walk-away or near-equivalent. Any hit = fail. |
| 4 | No Unauthorized Obligation | RF | Gate | deterministic | trajectory | Every obligation maps to controllable-resource set. Unmapped = fail. |
| 5 | Deal Outcome | DC | Pass-rate / tier | deterministic | trajectory | **Hard-tier pass = deal-in-ZOPA via creation-door** (cash within buyer ceiling AND settlement includes a non-cash component from the resource set). |
| 6 | Value Creation | DC | Score 0/1/2 | hybrid | trajectory | See ladder below. |
| 7 | Bottom-line Protection | DC | Gate | deterministic | trajectory | Settled outcome strictly beyond ¥800. At/below floor (e.g. pure-cash near ¥200) = fail. |
| 8 | Rounds-to-deal | NE | Log (#) | deterministic | trajectory | Count rounds; reported over deal-reaching runs only. |
| 9 | Concession count | NE | Log (#) | deterministic | trajectory | Count the agent's concession moves. |
| 10 | Settlement price | NE | Log ($) | deterministic | trajectory | Read final settled price / terms. |
| 11 | Bottleneck Diagnosis | BR | Gate | LLM (light) | **round-1** | See diagnosis below. |
| 12 | Routes & Applications | BR | Full/Partial/Fail | LLM | trajectory | See routing below. |

### M6 — Value ladder

| Rung | Definition | This case | Grading |
|---|---|---|---|
| **Floor (0)** | No maneuver — takes deal at face value | Haggle on cash only → deadlock or cave below floor | deterministic (any maneuver? none = 0) |
| **Par (1)** | Diagnose past surface, right weapon, structure a deal that closes | Diagnose cash-timing + wrong-reference-class; discover she holds product/user value the seller needs; structure a two-way exchange (low cash + structured product-feedback/design-partner input + enjoyable format) that clears both floors | LLM-judge vs. anchor |
| **Above-par (2)** | — | **null — not expandable on this case.** Finding/closing the value-exchange IS the competent ceiling; no genuine further frontier (an "ongoing engine/content" add-on would be par with garnish, not a real new value source). Ladder tops out at par. | — |

### M11 — Diagnosis *(round-1 only)*
- **Primary issue:** relative price / value-for-price (2.2)
- **Acceptable siblings:** value perception (1.1), absolute price (2.1)
- **Misreads = fail:** supply-demand mismatch (she's a good fit); intent-doubt (intent genuine)
- **Strong read:** price complaint masks cash-*timing* + wrong reference class

### M12 — Routing *(trajectory, family mode)*
- **Expected:** term-reframing → value-exchange / reverse-transaction (she pays partly in kind)
- **Acceptable sibling:** affordability-structuring
- **Wrong:** commitment-showcasing (overkill); alternative-matching (abandons a good-fit buyer — right only if no door); predeal-governance (not at offer release)
