# Case banks

- Top-level `*.jsonc` files are the active evaluation bank used by the default
  loader.
- `archive/P1.jsonc` through `archive/P6.jsonc` are frozen regression fixtures
  for the original evaluator and offline stub.
- `archive/r4p-package-snapshot/` preserves the five older R4P copies that used
  to live inside `nego-eval/cases/`.
- `draft/` is excluded from default discovery.

Runners and tests must select a bank explicitly when they do not mean the
active top-level set. Case discovery is intentionally non-recursive.
