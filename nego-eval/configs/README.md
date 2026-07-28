# Evaluation configuration

`eval.clean.glm52-qwen36.yaml` is the canonical v2 contract. It keeps the
experiment, named model connections, role routing, and judge repetition policy
in one file.

Status by refactor phase:

- Phase 1: schema and directory contract are frozen.
- Phase 2: the CLI executes this file directly with
  `python -m negoeval.cli --config configs/eval.clean.glm52-qwen36.yaml`.
- Phase 3: strict validation, provenance capture, and repeat aggregation are
  added before live runs.

All paths are relative to the YAML file. API keys must be named with
`api_key_env`; secrets must not be stored in YAML.

Role-local `temperature`, `max_tokens`, `extra`, `default_headers`, and
`omit_temperature` values override the named model connection. Include/exclude
patterns match case IDs and use shell-style wildcards.

`--config` is authoritative. Legacy flags such as `--provider`, `--case`, and
`--runs` are used only when no v2 config is supplied.

Phase 2 resolves `judges.metrics.<Mx>` independently but runs each judge once.
Phase 3 will honor and aggregate the declared `repeats`.

`legacy/` contains the old two-slot `agent` / `aux` configurations. They are
kept for auditability but are not the target interface.
