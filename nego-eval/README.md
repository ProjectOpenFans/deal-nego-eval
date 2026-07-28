# nego-eval

Negotiation-agent benchmark. It drives a buyer or seller negotiator against a
counterparty simulator and grades the result with metrics **M1–M12** per
`../case_spec.md`. The current evaluation bank is `../cases/*.jsonc`; frozen
P1-P6 regression fixtures live in `../cases/archive/`.

The benchmark is self-contained: it does not import or require
`../openfans-agents`.

## Layout
```
negoeval/
  schemas.py  cases.py    # our Deal/EpisodeInput/Turn/EpisodeOutput/result + jsonc loader
  broker/                 # local broker schemas, runner, skill registry/tools
  llm/                    # provider protocol + offline stub + OpenAI-compatible live provider
  agent/                  # AgentUnderTest + EpisodeInput adapter
  sim/                    # counterparty sim (system prompt + accept/counter/walk)
  extract/                # free-text turn -> structured Deal (offer extractor)
  orchestrator.py         # the turn loop -> EpisodeOutput
  grade/                  # M1-M12 graders + EvaluationResult assembler
  results/                # write results + aggregate CaseReport
  batch.py  cli.py
skills/                   # local negotiation skill markdown files
tests/                    # stub e2e, grader GoldRuns, sim fidelity
configs/                  # canonical v2 YAML plus legacy v1 configs
docs/                     # architecture and refactor notes
archive/                  # versioned historical logs/results/source snapshots
```

## Setup
```bash
cd nego-eval
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Run (stub mode — no LLM endpoint needed)
```bash
python -m negoeval.cli --provider stub --skills both --case all --out results
```
- `--skills on|off|both` — local skills vs none.
- `--profile par|cave|leak` — stub agent behavior (par settles; cave walks; leak reveals the floor).
- `--case P1[,P3] | all`, `--runs N`, `--provider stub|live`.

Each run writes one `EvaluationResult` JSON (`<case>__skills-<on|off>__<run>.json`) and prints a CaseReport table.

## YAML refactor

The canonical configuration is
`configs/eval.clean.glm52-qwen36.yaml`. It defines the experiment and routes
buyer negotiator, seller negotiator, both counterparties, offer extraction,
and judges independently.

Phase 1 freezes that contract. Direct execution with:

```bash
python -m negoeval.cli --config configs/eval.clean.glm52-qwen36.yaml
```

is implemented in Phase 2. Until then, the legacy CLI below remains the
executable path.

## Legacy live mode

Uses the official `openai` SDK against OpenAI-compatible endpoints. Per-provider
presets live in `negoeval/llm/liveconfig.py`.

1. Put keys in `nego-eval/.env` (copy `.env.example`):
   ```
   STEP_API_KEY=...
   QWEN_API_KEY=...
   ZHIPU_API_KEY=...
   DEEPSEEK_API_KEY=...
   ```
2. For the pre-refactor runner, copy
   `configs/legacy/eval.config.example.yaml` to `eval.config.yaml`. Its `agent`
   slot is the model-under-test and `aux` is shared by sim, judge, and extractor:
   ```yaml
   agent: { provider: deepseek_flash }   # stepfun | qwen | glm | deepseek_flash | deepseek_pro
   aux:   { provider: glm }
   ```
3. Run:
   ```bash
   python -m negoeval.cli --provider live --skills both --case all --out results
   ```

- These `agent` / `aux` configs are retained only for backwards compatibility
  during the refactor.
- The agent runs through `negoeval.broker.runner.LocalBrokerRunner`; all LLM calls go
  through the OpenAI SDK provider.
- To benchmark *agent vs baseline*: swap only `agent.provider`, keep `aux` fixed, diff the CaseReports.
- No seed → set low temperature (presets use 0.3) and use `--runs N` to average variance.

## Test
```bash
python -m pytest tests/ -q
```
