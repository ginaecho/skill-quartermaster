"""Skill conflict detection and compile-time resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from . import metadata
from .registry import Registry, Skill


@dataclass(frozen=True)
class Conflict:
    left: str
    right: str
    reason: str
    severity: str = "conflict"


def find_conflicts(skills: Iterable[Skill]) -> List[Conflict]:
    items = list(skills)
    out: List[Conflict] = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            reason = _explicit_reason(left, right) or _inferred_reason(left, right)
            if reason:
                out.append(Conflict(left.name, right.name, reason))
    return out


def registry_conflicts(registry: Registry) -> List[Conflict]:
    return find_conflicts(registry.all)


def _explicit_reason(left: Skill, right: Skill) -> str:
    if right.name in left.metadata.conflicts_with:
        return f"{left.name} declares conflict with {right.name}"
    if left.name in right.metadata.conflicts_with:
        return f"{right.name} declares conflict with {left.name}"
    return ""


def _inferred_reason(left: Skill, right: Skill) -> str:
    shared = set(left.metadata.provides) & set(right.metadata.provides)
    if not shared:
        return ""
    conflict_layers = {metadata.ACTION, metadata.TOOL}
    if left.metadata.layer in conflict_layers and right.metadata.layer in conflict_layers:
        return f"both provide {', '.join(sorted(shared))}"
    return ""
