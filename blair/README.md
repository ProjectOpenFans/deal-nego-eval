# Negotiation Eval — Review Package for Blair

**Purpose:** review of our negotiation evaluation framework — specifically the **eval metric design** and the **grading methodology**, plus the **case-bank construction logic** and representative samples.

**What this eval answers:** Does our agent *harness* (skill layer) make an LLM a materially better dealmaker on hard, judgment-intensive, non-standard deals — the kind Dealhouse serves? We run the same cases with the harness **off (clean)** and **on**, and measure the lift.

---

## 1. How the eval is designed

### 1.1 The unit of evaluation: a full negotiation episode

Each **case** encodes one negotiation scenario as a `v0` object (the deal configuration): two parties (our **agent** representing side A, and a **counterparty simulator** playing side B), each with public profiles and private constraints (reservation, deal-breakers, real interests, controllable resources), plus an authored **ground-truth ZOPA structure** and a five-tier **quality anchor**.

An **episode** = the agent and the counterparty-sim negotiate turn-by-turn (up to `round_cap = 12` rounds) until the sim **accepts (settled)**, **walks away**, or the round cap is hit.

### 1.2 Two arms, measure the lift

Every case is run in two arms:
- **clean** — bare model, no harness
- **on** — model + our skill harness (deal-diagnosis, interest-discovery, term-reframing, etc.)

**The signal is the gap: `quality(on) − quality(clean)`.** A case is *meaningful* only if **clean is non-trivial (the bare model does not already ace it) AND on lifts it**. If both arms max out (case too easy) or both collapse (case unsolvable), the case has no discriminating power and is dropped.

### 1.3 The counterparty simulator

Side B is played by an LLM sim reading B's private profile. Critically — **difficulty lives in the case's `v0`, not in the sim.** The sim only *executes* the authored constraints (plays the reservation, holds the deal-breakers, keeps the real need hidden). It does not invent difficulty. Diagnostic test we apply to every case: *"soften the sim — is the difficulty still there?"* If not, the difficulty was wrongly resting on sim theatrics and the case is reworked.

### 1.4 Models under test

Judge model (grader): **Qwen 3.7-max** (temperature 0). Agents under test: **DeepSeek-v4-pro, GLM-5.2 (local), StepFun**. Frontier models (Claude / GPT) are reserved for a later round once the case bank and harness are frozen.

---

## 2. The metrics (M1–M12) and how each is graded

Grading is a **layered, gate-then-optimize** design: hard pass/fail gates first (is the deal even legitimate?), then a scored quality tier (how good is it?). Quality never acts as a gate; gates never score.

| # | Metric | Layer | Grading | Method | What it checks |
|---|--------|-------|---------|--------|----------------|
| **M1** | Structure Completeness | Gate | P/F | Deterministic | The settled deal object is well-formed (required fields present w/ valid provenance). |
| **M2** | Representation Fidelity | Gate | P/F | LLM judge | Agent faithfully represented the principal's v0 intent — no hallucinated scope, no fabricated commitments. |
| **M3** | No Bottom-line Leakage | Gate | P/F | Deterministic | Agent never leaked the principal's walk-away. *(De-prioritized in the current R4/R5 hard-case rounds — see §4.)* |
| **M4** | No Unauthorized Obligation | Gate | P/F | Deterministic | Every obligation the agent made maps to a resource the principal actually controls. |
| **M5** | Deal Outcome | Outcome | P/F | Deterministic | Deal settled **and** cash within the buyer's authored ceiling. This is the "did a legitimate deal actually stand" check. |
| **M6** | Value Creation (Quality) | Quality | 0–4 tier | Hybrid (gate + LLM judge) | The headline quality score. Five tiers: **floor(0) / crude(1) / sound(2) / sharp(3) / brilliant(4)**, judged against the case's authored anchors. |
| **M11** | Bottleneck Diagnosis | Process (harness-only) | P/F | LLM judge | Did the agent correctly name the real bottleneck (round-1 read)? |
| **M12** | Routes & Applications | Process (harness-only) | Full/Partial/Fail | LLM judge | Did the agent pick a defensible "weapon" (skill/route) with sound rationale? |

*(M7–M10 are effectiveness logs — rounds-to-deal, concession count, settlement price — recorded but not gated.)*

### 2.1 The core grading rule (verdict assembly)

This is the heart of the grading and the piece most worth scrutinizing:

```
gates_pass  = M1 ∧ M2 ∧ M3 ∧ M4        # process is clean
outcome     = M5                         # a legitimate deal stood (settled + within cash cap)
quality     = M6 tier (0–4), gated as below
```

**Quality (M6) zeroing rule (current version, "V3"):**
```
if NOT gates_pass:                 quality = 0   # leaked / over-committed / ill-formed → doesn't count, however pretty
elif M5 failed on cash_over_cap:   quality = 0   # cash-trap breach (agent paid/took cash it shouldn't) → hard zero
else:                              quality = M6  # keep the judge's tier
```

**Why this rule matters (the subtle part):** M5 can fail two ways, and they must be treated differently:
- **`cash_over_cap`** (agent broke the cash ceiling — e.g. paid to "win" on a case where the correct solve is non-cash): this is a *bad settled deal*. We **hard-zero it deterministically** — we do NOT trust the judge to catch it, because the judge can be fooled by slick maneuvering into scoring a cash-trap breach highly.
- **`not_settled`** (round cap hit while the negotiation was still *constructively progressing* — common for correct long-path solutions like "prove value first, then deep-commit"): we **do NOT zero on this**. We let the judge's tier stand. Real deadlock/no-maneuver gets *floor* from the judge anyway; a genuinely strong-but-unsigned negotiation keeps its earned tier.

This rule was introduced to fix a **harness-inversion artifact**: the correct solutions on hard cases are often long-path (diagnose → build trust → lock next step, unsigned within the round cap), and a naive "must-be-settled" gate was crushing those to 0 — making the harness look *worse* than the bare model that sloppily closed a bad deal. **M5 (settle rate) is still recorded separately** as its own metric; it just no longer zeroes quality.

### 2.2 How M6 (the quality judge) is anchored

Quality is not a free-floating LLM opinion. Each case authors a **five-tier reference (T0–T4)** describing *what floor / crude / sound / sharp / brilliant look like in this specific case*. The judge places the settled deal against these authored anchors. Stage 1 is a deterministic floor check (did the agent do *any* non-linear maneuver at all? no → floor); Stage 2 is the judge placing it among the higher tiers against the anchors. Cash-trap cases additionally pin "paid/took cash → floor" into their T0 anchor so the judge has explicit grounds to punish a breach.

---

## 3. Case-bank logic

### 3.1 What makes a case hard (the design theory)

A case is not hard because the sim is rude. It is hard because the **ZOPA is abstract and hard to locate, and the bargaining resource set is hard to maneuver** — a real solution has to be *engineered*, not found. (Contrast: a clean MBA-style case where both sides' bargaining sets are explicit and a compromise is easy to locate — an agent handles that trivially.)

We construct difficulty on **three orthogonal axes, all authored into `v0`:**

- **terms-hard** — the ZOPA sits in a non-obvious dimension; the simple structure has no ZOPA (e.g. a straight cash buyout yields an empty shell); the solve must reconstruct the *nature/direction* of the deal. *(Authored in: resource set, cash/creation ZOPA, conventional-deal-fails-why, creation-door.)*
- **interest-hard** — the real interest is buried under a wrong reference class; the stated ask and the true need are *opposed*; the agent must reconstruct the counterparty's frame before any deal is possible. *(Authored in: private intent = misleading stated ask; real need marked hidden / self-misdiagnosed.)*
- **person-hard** — the counterparty is intrinsically hard to deal with: unwilling, low-interest, or a hard asymmetry (a "you can't even get a meeting" tier) requiring limit-pushing. *(Authored in: profile / BATNA / reservation / deal-breakers.)*

**Rule of thumb:** a meaningful hard case pushes **at least two axes to "strong."** One-axis cases collapse (the model just solves them). Pushing **person-hard to the frontier** (a counterparty who genuinely cannot be moved) is the one axis that reliably challenges even strong models — pure reasoning/reconstruction difficulty, strong models tend to solve.

### 3.2 Two hard-won authoring rules

1. **Hide the solution.** The committed party's *solution resource* and the *real problem* must live in `private` (or be inferable only from context) — never spelled out in the public profile. If the agent can just read the answer, there is no diagnosis to do and difficulty collapses.
2. **`ceiling = 0` is only for true cash-traps.** Setting the buyer cash ceiling to 0 (any cash = fail) is correct only when the committed party *genuinely should not pay* (paying destroys their leverage). For acquisition/transaction cases where the buyer *should* pay and the difficulty is "clean buyout vs. structured deal," a 0 ceiling wrongly kills the correct solution — use a real ceiling and let the M6 judge catch the bad structure.

### 3.3 Coverage

The bank is spanned by **logic (the difficulty axes above) × skin (scenario family)**. Skin families span celebrity access, creator monetization, unique personal supply, bespoke experience sourcing, specific-person deals, hybrid, standard goods (calibration only), social. Core weight sits on creator / personal-supply / bespoke-experience. We fill *representative* cells (every key logic×skin crossing gets a case; heavier weight where it matters) rather than a fixed count — target on the order of ~40 meaningful cases, tuned by experimental feedback.

### 3.4 The construction pipeline

`draft → quick-test → judge against 6 criteria → enter bank / rework / archive`, with a coverage tracker and a registry updated at each step. Quick-test is fast: **3 models × clean arm × 1 run** first (does the bare model already ace it? → drop or harden), then the on arm to confirm a gap. The 6 entry criteria: sim resistance holds · no answer-leak · clean stands non-trivially · clean→on gap exists · ceiling logic sound · schema current.

---

## 4. Notes / open items worth Blair's eye

- **M3 (leakage) is largely inert in the current rounds** — deliberately. R4/R5 were built to probe the *difficulty frontier* for mid-tier models, where leakage is not the binding constraint. M3 will need real teeth if/when we want it as a live gate.
- **The V3 quality-zeroing rule (§2.1)** is the most consequential recent change and the piece most worth a second opinion — specifically the decision to trust the judge for `not_settled` but *not* for `cash_over_cap`.
- **Judge reliance.** M2, M6, M11, M12 are LLM-judged (temp 0). We've spot-checked stability; the judge's anchor-bound M6 scoring has been reliable in review, but it is the main place model-judge error could enter at scale.
- **Difficulty must live in v0, not the sim** (§1.3 / §3.1) — a governing principle; a case that a softened sim would trivialize is considered broken.

---

## Files in this package

- `01_framework/` — this document + the difficulty framework + the metric/verdict source files
- `02_sample_cases/` — representative authored cases (see that folder's README for what each illustrates)
- `03_sample_results/` — representative graded runs (clean vs on) with commentary
