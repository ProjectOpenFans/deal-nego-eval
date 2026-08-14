"""Tolerant JSON extraction from LLM text.

A judge that answers correctly but phrases the wrapper slightly differently must
not be recorded as a failure: a discarded grading gets silently replaced by a
fail-safe value, which corrupts the distribution far worse than a lenient parser
ever could. Everything here exists to avoid throwing away a real answer.

Handled: code fences and surrounding prose; truncation at max_tokens (close the
open strings/brackets and retry); trailing commas; ``//`` and ``#`` comments;
smart/full-width quotes; Python literals (``True``/``False``/``None``); and
single-quoted strings.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, Optional

_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9_-]*\n?")
_FENCE_CLOSE = re.compile(r"\n?```\s*$")
_FENCED_BLOCK = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.S)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_LINE_COMMENT = re.compile(r"(?m)(?<![:\"'])\s+(?://|#)[^\n]*$")
_SMART_QUOTES = str.maketrans({
    "“": '"', "”": '"', "「": '"', "」": '"',
    "＂": '"', "‘": "'", "’": "'",
})


def _as_dict(chunk: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(chunk)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _candidates(chunk: str) -> Iterator[str]:
    """Progressively relax common malformations, cheapest repair first."""
    yield chunk
    no_comma = _TRAILING_COMMA.sub(r"\1", chunk)
    yield no_comma
    decommented = _TRAILING_COMMA.sub(r"\1", _LINE_COMMENT.sub("", chunk))
    yield decommented
    unsmart = decommented.translate(_SMART_QUOTES)
    yield unsmart
    pythonish = re.sub(r"\bTrue\b", "true", unsmart)
    pythonish = re.sub(r"\bFalse\b", "false", pythonish)
    pythonish = re.sub(r"\bNone\b", "null", pythonish)
    yield pythonish
    if '"' not in pythonish and "'" in pythonish:
        yield pythonish.replace("'", '"')


def _repair(chunk: str) -> Optional[Dict[str, Any]]:
    for candidate in _candidates(chunk):
        obj = _as_dict(candidate)
        if obj is not None:
            return obj
    return None


def _close_truncated(s: str) -> Optional[str]:
    """Rebuild an object cut off mid-flight by a token limit.

    Tracks string/escape state and bracket depth, drops a dangling partial
    member, then appends the closers still owed. Returns None when the text is
    already balanced (not a truncation case).
    """
    start = s.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    stack: list[str] = []
    last_comma: Optional[int] = None
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            stack.append(c)
            depth += 1
        elif c in "}]":
            if stack:
                stack.pop()
            depth -= 1
            if depth == 0:
                return None
        elif c == "," and depth > 0:
            last_comma = i
    if depth <= 0:
        return None
    if in_str:
        head = s[start:] + '"'
    elif last_comma is not None:
        head = s[start:last_comma]
    else:
        head = s[start:]
    head = _TRAILING_COMMA.sub(r"\1", head.rstrip().rstrip(","))
    for opener in reversed(stack):
        head += "}" if opener == "{" else "]"
    return head


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", s)).strip()
    elif "```" in s:
        fenced = _FENCED_BLOCK.search(s)
        if fenced:
            obj = _repair(fenced.group(1).strip())
            if obj is not None:
                return obj

    obj = _repair(s)
    if obj is not None:
        return obj

    # Scan for a balanced {...}. Unlike the previous version this keeps looking
    # past a chunk that fails to parse, and runs the repair ladder on each.
    start = s.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            c = s[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    obj = _repair(s[start : i + 1])
                    if obj is not None:
                        return obj
                    break
        start = s.find("{", start + 1)

    repaired = _close_truncated(s)
    if repaired:
        return _repair(repaired)
    return None
