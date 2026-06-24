"""Load ``cases/P*.jsonc`` and split into meta / input / fixture.

The case files are JSONC (JSON + ``//`` and ``/* */`` comments). We strip
comments with a small string-aware scanner (so ``//`` inside a string value is
preserved), then ``json.loads``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .schemas import EpisodeInput

# nego-eval/negoeval/cases.py -> parents: [0]=negoeval [1]=nego-eval [2]=deal-rec
DEFAULT_CASES_DIR = Path(__file__).resolve().parents[2] / "cases"


def strip_jsonc(text: str) -> str:
    """Remove ``//`` line comments and ``/* */`` blocks outside of strings."""
    out: List[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:  # keep escaped char verbatim
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


class CaseFile(BaseModel):
    """One loaded case: typed ``input`` + raw ``meta``/``fixture`` dicts."""

    meta: Dict[str, Any] = Field(default_factory=dict)
    input: EpisodeInput
    fixture: Dict[str, Any] = Field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return str(self.meta.get("case_id") or self.input.episode_id)

    @property
    def side(self) -> str:
        """``sell`` or ``buy`` — drives the buy-side (P3) semantic inversion."""
        return str(self.meta.get("side") or "sell")


def load_case(path: str | Path) -> CaseFile:
    path = Path(path)
    raw = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    return CaseFile.model_validate(raw)


def discover_cases(cases_dir: str | Path | None = None) -> List[Path]:
    base = Path(cases_dir) if cases_dir else DEFAULT_CASES_DIR
    return sorted(base.glob("*.jsonc"))


def load_all(cases_dir: str | Path | None = None) -> List[CaseFile]:
    return [load_case(p) for p in discover_cases(cases_dir)]
