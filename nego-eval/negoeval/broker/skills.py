"""Local skill registry and tool handlers for the benchmark broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str = ""
    follow_up_skills: List[str] = field(default_factory=list)
    path: Path = Path()


def _parse_markdown(path: Path) -> Tuple[Dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    return dict(meta), parts[2].lstrip()


def discover() -> List[SkillEntry]:
    entries: List[SkillEntry] = []
    if not SKILLS_ROOT.exists():
        return entries
    for path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        meta, _body = _parse_markdown(path)
        name = str(meta.get("name") or path.parent.name)
        follow = meta.get("follow_up_skills") or []
        if not isinstance(follow, list):
            follow = []
        entries.append(
            SkillEntry(
                name=name,
                description=str(meta.get("description") or ""),
                follow_up_skills=[str(item) for item in follow],
                path=path,
            )
        )
    return entries


def all_skill_names() -> Set[str]:
    return {entry.name for entry in discover()}


def _entry_map() -> Dict[str, SkillEntry]:
    return {entry.name: entry for entry in discover()}


def skill_catalog_block(allowlist: Optional[Set[str]]) -> str:
    entries = _entries_for(allowlist)
    if not entries:
        return "当前没有可用 skill。"
    return "\n".join(f"- {entry.name}: {entry.description}" for entry in entries)


def _entries_for(allowlist: Optional[Set[str]]) -> List[SkillEntry]:
    entries = discover()
    if allowlist is None:
        return entries
    return [entry for entry in entries if entry.name in allowlist]


def read_skill(name: str, allowlist: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    entries = _entry_map()
    entry = entries.get(name)
    allowed = {e.name for e in _entries_for(allowlist)}
    if entry is None or name not in allowed:
        return {"error": f"unknown or disabled skill '{name}'", "available": sorted(allowed)}, False
    _meta, body = _parse_markdown(entry.path)
    follow = [item for item in entry.follow_up_skills if item in allowed]
    return (
        {
            "name": entry.name,
            "description": entry.description,
            "follow_up_skills": follow,
            "instructions": body,
        },
        True,
    )


def run_skill_tool(name: str, arguments: dict, allowlist: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    if name == "list_skills":
        return {
            "skills": [{"name": entry.name, "description": entry.description} for entry in _entries_for(allowlist)]
        }, True
    if name == "read_skill":
        return read_skill(str((arguments or {}).get("name") or "").strip(), allowlist)
    return {"error": f"Unknown skill tool: {name}"}, False


def skill_tools() -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "List negotiation skills available in this run.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "Read a negotiation skill by name before applying it.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
    ]
