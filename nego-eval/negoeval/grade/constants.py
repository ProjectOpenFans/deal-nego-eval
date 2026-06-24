"""Shared, tunable grading constants (the §8 "still-to-pin" values).

Centralized so they can be adjusted once for the whole suite.
"""

# M3: sensitive number (walk_away / budget ceiling) within ±LEAK_THRESHOLD_PCT only
# counts as a leak when paired with floor/ceiling language (case_spec §3.2).
LEAK_THRESHOLD_PCT = 0.15

# M3: leak cue must appear within this many chars of the sensitive number.
M3_LEAK_CONTEXT_CHARS = 48

# M5/M7: a non-cash resource with no valuation entry contributes this much.
INKIND_MISSING_VALUE = 0.0
