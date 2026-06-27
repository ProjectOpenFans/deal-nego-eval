# nego-eval

Negotiation-agent benchmark. Drives a local broker single-side turn as the
agent-under-test against our own counterparty sim, and grades the result with
metrics **M1–M12** per `../case_spec.md`. Runs `../cases/P*.jsonc`.

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

## Live mode
Uses the official `openai` SDK against OpenAI-compatible endpoints
(StepFun / Qwen / GLM / Kimi / DeepSeek). Per-provider presets live in
`negoeval/llm/liveconfig.py`.

1. Put keys in `nego-eval/.env` (copy `.env.example`):
   ```
   STEP_API_KEY=...
   QWEN_API_KEY=...
   ZAI_API_KEY=...
   ZHIPU_API_KEY=...
   KIMI_API_KEY=...
   MOONSHOT_API_KEY=...
   DEEPSEEK_API_KEY=...
   ```
2. Pick providers in `eval.config.yaml` (`agent` = model-under-test, `aux` = fixed neutral
   for sim + M2/M6 judges + offer-extractor):
   ```yaml
   agent: { provider: deepseek_flash }   # stepfun | qwen | glm | glm52 | kimi | deepseek_flash | deepseek_pro
   aux:   { provider: glm }
   ```
3. Run:
   ```bash
   python -m negoeval.cli --provider live --skills both --case all --out results
   ```

- Provider presets (base_url + model + `extra_create_kwargs`): `stepfun` (`step-3.7-flash`,
  `reasoning_effort: low`), `qwen` (`qwen3.7-max`), `glm` (`glm-5.1`, `thinking: enabled`),
  `glm52` (`glm-5.2`, `temperature: 1.0`, `thinking: enabled`, `reasoning_effort: medium`),
  `kimi` (`kimi-k2.6`, `thinking: enabled`, temperature omitted per official API),
  `deepseek` / `deepseek_flash` (`deepseek-v4-flash`, `thinking: enabled`), and
  `deepseek_pro` (`deepseek-v4-pro`, `thinking: enabled`). Use `deepseek_pro` only when
  you want the higher-cost Pro model.
  Override per block with `model:` / `temperature:` / `thinking:` / `reasoning_effort:`.
- The agent runs through `negoeval.broker.runner.LocalBrokerRunner`; all LLM calls go
  through the OpenAI SDK provider.
- To benchmark *agent vs baseline*: swap only `agent.provider`, keep `aux` fixed, diff the CaseReports.
- No seed → set low temperature where the provider accepts it (Kimi K2.6 omits temperature
  per official API) and use `--runs N` to average variance.

## Test
```bash
python -m pytest tests/ -q
```
