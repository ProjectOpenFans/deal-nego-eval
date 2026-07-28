# Evaluation configuration

`eval.clean.glm52-qwen36.yaml` is the canonical v2 contract. It keeps the
experiment, named model connections, role routing, and judge repetition policy
in one file.

Status by refactor phase:

- Phase 1: schema and directory contract are frozen.
- Phase 2: the CLI will execute this file directly with
  `python -m negoeval.cli --config configs/eval.clean.glm52-qwen36.yaml`.
- Phase 3: strict validation, provenance capture, and repeat aggregation are
  added before live runs.

All paths are relative to the YAML file. API keys must be named with
`api_key_env`; secrets must not be stored in YAML.

`legacy/` contains the old two-slot `agent` / `aux` configurations. They are
kept for auditability but are not the target interface.
