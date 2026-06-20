"""Intent compiler (v0): build an active loadout from a project's intent.

This is a deliberately simple, dependency-free relevance ranker: it scores each
skill's name + description against the words in the project intent and keeps the
top N (defaulting near the ~30-skill accuracy sweet spot). It is not a semantic
embedding model — that is a later phase — but it produces a sensible starting
loadout and, crucially, it is transparent: you can see exactly why each skill
scored the way it did.

The compiler never deletes. It proposes a partition of the registry into "keep
active" vs "demote", which the CLI presents for approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from .registry import ACTIVE, DEMOTED, Registry, Skill

# Common words that carry no selection signal.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "i", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "use", "using", "want", "with", "you", "your", "we", "my",
    "project", "skill", "skills", "code", "build", "make", "need", "work",
}

DEFAULT_CAP = 30

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS]


@dataclass
class Scored:
    skill: Skill
    score: int
    matched: List[str]


@dataclass
class CompilePlan:
    keep: List[Scored]       # -> active
    drop: List[Scored]       # -> demoted
    cap: int

    @property
    def scored(self) -> List[Scored]:
        return self.keep + self.drop


def score_skills(registry: Registry, intent: str) -> List[Scored]:
    intent_terms: Set[str] = set(_tokens(intent))
    scored: List[Scored] = []
    for skill in registry:
        haystack = set(_tokens(f"{skill.name} {skill.description}"))
        matched = sorted(intent_terms & haystack)
        scored.append(Scored(skill, len(matched), matched))
    # Highest score first; stable tiebreak by name.
    scored.sort(key=lambda s: (-s.score, s.skill.name.lower()))
    return scored


def compile_loadout(
    registry: Registry,
    intent: str,
    *,
    cap: int = DEFAULT_CAP,
    keep_unmatched: bool = False,
) -> CompilePlan:
    """Partition skills into an active loadout vs. the rest.

    A skill is kept active if it scores > 0 against the intent and falls within
    the cap. Skills that score 0 are dropped (demoted) unless ``keep_unmatched``
    is set. The cap protects the selection-accuracy sweet spot.
    """
    scored = score_skills(registry, intent)
    keep: List[Scored] = []
    drop: List[Scored] = []
    for s in scored:
        eligible = s.score > 0 or keep_unmatched
        if eligible and len(keep) < cap:
            keep.append(s)
        else:
            drop.append(s)
    return CompilePlan(keep=keep, drop=drop, cap=cap)
