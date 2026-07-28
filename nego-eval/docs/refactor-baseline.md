# Refactor baseline — Phase 1

Date: 2026-07-28

## Goal

Replace the implicit `agent` / `aux` split with a single YAML-driven
experiment contract. Buyer negotiator, seller negotiator, both counterparty
roles, offer extraction, and each LLM judge must be independently routable.

The first live experiment is the `clean` arm, using only GLM-5.2 and Qwen3.6,
while keeping every assignment configurable.

## Pre-refactor behavior

The live path exposed only two model slots:

| Old slot | Consumers |
| --- | --- |
| `agent` | Agent-under-test, regardless of buyer/seller side |
| `aux` | Counterparty simulator, offer extractor, M2/M6 judge |

This made it impossible to audit or independently calibrate the individual
roles. CLI experiment settings also lived in flags rather than in the same
YAML as model routing.

## Data boundary

| Location | Meaning |
| --- | --- |
| `../cases/*.jsonc` | Current active evaluation bank |
| `../cases/archive/P1.jsonc` … `P6.jsonc` | Frozen regression fixtures |
| `../cases/archive/r4p-package-snapshot/` | Older package-local R4P copies |

Unit tests that assert historical P1-P6 behavior must explicitly use the
legacy bank. The default loader continues to select the active bank.

## Baseline test result

Before cleanup, `pytest -q` produced **5 passed / 23 failed**. The dominant
cause was data drift: historical tests requested `cases/P1.jsonc` and
`cases/P3.jsonc`, which had moved to `cases/archive/`; the batch test then
silently ran the 24 active cases against a stub written for the legacy schema.

Phase 1 separates those datasets and restores regression-test intent without
changing evaluator scoring behavior.

After cleanup, the offline suite produces **29 passed / 0 failed**. The two
additional corrections freeze already-current behavior: simulator prompts
withhold both creation-door descriptions and route-out triggers, and batch
summaries use timestamped filenames.

## Canonical v2 roles

| Role | Selection |
| --- | --- |
| `buyer_negotiator` | Used as AUT when `case.meta.side == buy` |
| `seller_negotiator` | Used as AUT when `case.meta.side == sell` |
| `buyer_counterparty` | Opposes the seller AUT |
| `seller_counterparty` | Opposes the buyer AUT |
| `offer_extractor` | Structures offers and final deals |
| `judges.default` | Fallback for every LLM-graded metric |
| `judges.metrics.<Mx>` | Optional per-metric model and repeat override |

The v2 contract is defined in
`configs/eval.clean.glm52-qwen36.yaml`. It is intentionally not routed into the
runtime until Phase 2, so Phase 1 cannot accidentally launch a live run.

## Non-destructive cleanup map

| Previous location | New location |
| --- | --- |
| `eval.*.yaml` | `configs/legacy/` |
| `log_*.txt` | `archive/logs/` |
| `results 2/` | `archive/results-v1/` |
| `*.pre_*` source copies | `archive/source-backups/` |
| `nego-eval/cases/*.jsonc` | `../cases/archive/r4p-package-snapshot/` |

No historical evaluation output was deleted.
