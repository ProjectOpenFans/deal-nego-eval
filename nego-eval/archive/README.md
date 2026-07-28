# Historical artifacts

This directory is versioned and read-only from the evaluator's point of view.
It preserves:

- `logs/`: console logs from earlier experiments.
- `results-v1/`: pre-refactor evaluation outputs.
- `source-backups/`: manual source snapshots that previously sat beside live
  Python modules.

New runs must write to `results/`, never to `archive/`.
