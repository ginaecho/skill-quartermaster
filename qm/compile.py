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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from . import conflicts, metadata, store
from .registry import Registry, Skill

# Common words that carry no selection signal.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "i", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "use", "using", "want", "with", "you", "your", "we", "my",
    "project", "skill", "skills", "code", "build", "make", "need", "work",
}

DEFAULT_CAP = 30
LAYER_ORDER = (
    metadata.GUARDRAIL,
    metadata.STYLE,
    metadata.PLANNING,
    metadata.DOMAIN,
    metadata.ACTION,
    metadata.TOOL,
)
LAYER_WEIGHTS = {
    metadata.GUARDRAIL: 30,
    metadata.STYLE: 20,
    metadata.PLANNING: 12,
    metadata.DOMAIN: 8,
    metadata.ACTION: 6,
    metadata.TOOL: 6,
}
DEFAULT_LAYER_CAPS = {
    metadata.GUARDRAIL: 5,
    metadata.STYLE: 3,
}

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS]


@dataclass
class Scored:
    skill: Skill
    score: int
    matched: List[str]
    priority: int = 0
    reasons: List[str] = field(default_factory=list)

    @property
    def layer(self) -> str:
        return self.skill.metadata.layer


@dataclass
class CompilePlan:
    keep: List[Scored]       # -> active
    drop: List[Scored]       # -> demoted
    cap: int
    by_layer: Dict[str, List[Scored]] = field(default_factory=dict)
    dropped_due_cap: List[Scored] = field(default_factory=list)
    added_guardrails: List[Scored] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)

    @property
    def scored(self) -> List[Scored]:
        return self.keep + self.drop


def score_skills(registry: Registry, intent: str) -> List[Scored]:
    intent_terms: Set[str] = set(_tokens(intent))
    history = store.read_skill_history()
    scored: List[Scored] = []
    for skill in registry:
        meta_terms = " ".join(
            skill.metadata.tags
            + skill.metadata.risk
            + skill.metadata.provides
            + skill.metadata.requires
        )
        haystack = set(_tokens(f"{skill.name} {skill.description} {meta_terms}"))
        matched = sorted(intent_terms & haystack)
        hist = history.get(skill.name, {})
        usage_bonus = min(int(hist.get("usage_count") or 0), 5)
        selected_bonus = min(int(hist.get("selected_count") or 0), 5)
        layer_weight = LAYER_WEIGHTS.get(skill.metadata.layer, 0)
        priority = (
            len(matched) * 10
            + skill.metadata.priority
            + layer_weight
            + usage_bonus
            + selected_bonus
        )
        reasons = []
        if matched:
            reasons.append("intent:" + ",".join(matched))
        if skill.metadata.priority:
            reasons.append(f"metadata-priority:{skill.metadata.priority}")
        if layer_weight:
            reasons.append(f"layer:{skill.metadata.layer}")
        if usage_bonus:
            reasons.append(f"usage:{usage_bonus}")
        if selected_bonus:
            reasons.append(f"selected:{selected_bonus}")
        scored.append(Scored(skill, len(matched), matched, priority, reasons))
    # Highest score first; stable tiebreak by name.
    scored.sort(key=lambda s: (-s.priority, -s.score, s.skill.name.lower()))
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
    dropped_due_cap: List[Scored] = []
    added_guardrails: List[Scored] = []

    selected = set()

    def eligible(s: Scored) -> bool:
        if keep_unmatched:
            return True
        if s.score > 0:
            return True
        if s.layer in (metadata.GUARDRAIL, metadata.STYLE) and s.skill.metadata.priority > 0:
            return True
        return False

    def add(s: Scored, *, guardrail: bool = False) -> None:
        keep.append(s)
        selected.add(s.skill.name)
        if guardrail:
            added_guardrails.append(s)

    # Reserve room for high-priority guardrails/style before domain/action/tool
    # skills compete for the rest of the cap.
    for layer in (metadata.GUARDRAIL, metadata.STYLE):
        layer_cap = DEFAULT_LAYER_CAPS.get(layer, cap)
        chosen = 0
        for s in scored:
            if s.skill.name in selected or s.layer != layer or not eligible(s):
                continue
            if len(keep) >= cap or chosen >= layer_cap:
                break
            add(s, guardrail=(layer == metadata.GUARDRAIL and s.score == 0))
            chosen += 1

    for s in scored:
        if s.skill.name in selected:
            continue
        if eligible(s) and len(keep) < cap:
            add(s)
        elif eligible(s):
            drop.append(s)
            dropped_due_cap.append(s)
        else:
            drop.append(s)
    blocked = _resolve_guardrails(keep, drop, scored, cap, added_guardrails)
    blocked.extend(_resolve_conflicts(keep, drop))
    by_layer: Dict[str, List[Scored]] = {layer: [] for layer in LAYER_ORDER}
    for s in keep:
        by_layer.setdefault(s.layer, []).append(s)
    return CompilePlan(
        keep=keep,
        drop=drop,
        cap=cap,
        by_layer=by_layer,
        dropped_due_cap=dropped_due_cap,
        added_guardrails=added_guardrails,
        blocked=blocked,
    )


def _resolve_guardrails(
    keep: List[Scored],
    drop: List[Scored],
    scored: List[Scored],
    cap: int,
    added_guardrails: List[Scored],
) -> List[str]:
    blocked: List[str] = []
    selected = {s.skill.name for s in keep}
    guardrails = [s for s in scored if s.layer == metadata.GUARDRAIL]

    for s in list(keep):
        required = _required_guardrails(s)
        if not required:
            continue
        available = _matching_guardrails(required, guardrails)
        if not available:
            keep.remove(s)
            drop.append(s)
            selected.discard(s.skill.name)
            blocked.append(
                f"{s.skill.name}: missing guardrail for {', '.join(required)}"
            )
            continue
        for guard in available:
            if guard.skill.name in selected:
                continue
            if len(keep) >= cap:
                victim = _lowest_non_guardrail(keep, protected={s.skill.name})
                if victim is None:
                    blocked.append(
                        f"{s.skill.name}: no room to add guardrail {guard.skill.name}"
                    )
                    continue
                keep.remove(victim)
                drop.append(victim)
                selected.discard(victim.skill.name)
            keep.append(guard)
            selected.add(guard.skill.name)
            if guard not in added_guardrails:
                added_guardrails.append(guard)
            if guard not in drop:
                continue
            drop.remove(guard)

    return blocked


def _required_guardrails(s: Scored) -> List[str]:
    if s.layer not in (metadata.ACTION, metadata.TOOL):
        return []
    explicit = list(s.skill.metadata.requires_guardrails)
    if explicit:
        return explicit
    return list(s.skill.metadata.risk)


def _matching_guardrails(required: List[str], guardrails: List[Scored]) -> List[Scored]:
    req = set(required)
    out: List[Scored] = []
    for g in guardrails:
        signals = {
            g.skill.name,
            *g.skill.metadata.tags,
            *g.skill.metadata.risk,
            *g.skill.metadata.provides,
        }
        if req & signals:
            out.append(g)
    return out[:2]


def _lowest_non_guardrail(keep: List[Scored], *, protected: Optional[Set[str]] = None) -> Optional[Scored]:
    protected = protected or set()
    candidates = [
        s for s in keep
        if s.layer != metadata.GUARDRAIL and s.skill.name not in protected
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda s: (s.priority, s.score, s.skill.name.lower()))[0]


def _resolve_conflicts(keep: List[Scored], drop: List[Scored]) -> List[str]:
    blocked: List[str] = []
    by_name = {s.skill.name: s for s in keep}
    for conflict in conflicts.find_conflicts([s.skill for s in list(keep)]):
        left = by_name.get(conflict.left)
        right = by_name.get(conflict.right)
        if left is None or right is None:
            continue
        if left.layer == metadata.GUARDRAIL and right.layer == metadata.GUARDRAIL:
            for item in (left, right):
                if item in keep:
                    keep.remove(item)
                    drop.append(item)
            blocked.append(
                f"{left.skill.name} conflicts with {right.skill.name}: {conflict.reason}; guardrail conflict needs user decision"
            )
            by_name.pop(left.skill.name, None)
            by_name.pop(right.skill.name, None)
            continue
        if left.layer == metadata.GUARDRAIL:
            loser = right
        elif right.layer == metadata.GUARDRAIL:
            loser = left
        else:
            loser = sorted(
                (left, right),
                key=lambda s: (s.priority, s.score, s.skill.name.lower()),
            )[0]
        if loser in keep:
            keep.remove(loser)
            drop.append(loser)
            by_name.pop(loser.skill.name, None)
            blocked.append(
                f"{loser.skill.name} dropped due to conflict: {conflict.reason}"
            )
    return blocked
