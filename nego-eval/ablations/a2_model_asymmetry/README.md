# A2 model asymmetry

Independent bilateral buyer-broker vs seller-broker ablation. It imports
canonical `negoeval` library surfaces but does not edit or branch inside the
canonical orchestrator, configuration, cases, or result directories.

```bash
cd nego-eval
python -m ablations.a2_model_asymmetry --stage preflight
python -m ablations.a2_model_asymmetry --stage pilot
python -m ablations.a2_model_asymmetry --stage full --run-id <approved-run-id>
python -m ablations.a2_model_asymmetry --report <run-id>
```

`pilot` performs preflight, smoke, then the 96-episode balanced pilot. It stops
after writing the Phase 2 report. `full` is only run after pilot approval.

