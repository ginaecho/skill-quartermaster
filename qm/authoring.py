"""The authoring arm (v0.4): turn recurring capability gaps into new skills.

The loop:

    record gaps  →  cluster them  →  when a cluster recurs and nothing on the
    shelf covers it, propose authoring  →  scaffold a probationary SKILL.md and
    hand a brief to `skill-creator` to fill in  →  admit the skill as
    `active, probationary` (on trial).

This module does the gap reasoning and the scaffold. It deliberately does NOT
write the skill's *content* — that is `skill-creator`'s job. We emit a brief and
a stub; Claude (driving the meta-skill) invokes skill-creator to flesh it out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import store
from .compile import _tokens
from .registry import Registry

# A gap must recur at least this many times before authoring is proposed.
GAP_THRESHOLD = 2
# How long a newly authored skill stays on probation before it must prove out.
PROBATION_DAYS = 14
# Token-set overlap (Jaccard) needed to treat two gaps / a gap+skill as related.
_SIM = 0.3

_SLUG = re.compile(r"[^a-z0-9]+")

# Gap descriptions are natural-language complaints ("I needed X but nothing
# matched"), so they carry more filler than a terse intent string. Strip it so
# the content tokens dominate the similarity score.
_GAP_FILLER = {
    "needed", "need", "want", "wanted", "would", "could", "couldnt", "cant",
    "cannot", "find", "found", "match", "matched", "matching", "looking",
    "look", "tried", "try", "trying", "get", "got", "doesnt", "didnt", "into",
    "no", "not", "but", "when", "while", "because", "instead", "anything",
    "something", "way", "support", "really", "just", "able", "kept", "keep",
    "again", "still", "nothing", "none", "one", "task", "tasks",
}


def _gap_tokens(text: str) -> List[str]:
    return [w for w in _tokens(text) if w not in _GAP_FILLER]


def slugify(text: str, *, max_words: int = 4) -> str:
    words = [w for w in _tokens(text)][:max_words]
    slug = "-".join(words) if words else "new-skill"
    slug = _SLUG.sub("-", slug).strip("-")
    return slug or "new-skill"


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class GapCluster:
    key: str                       # human label (top shared tokens)
    tokens: set = field(default_factory=set)
    samples: List[str] = field(default_factory=list)
    matched_skill: Optional[str] = None  # existing skill that already covers it

    @property
    def count(self) -> int:
        return len(self.samples)


def cluster_gaps(gaps: List[Dict], registry: Optional[Registry] = None) -> List[GapCluster]:
    """Greedily group recorded gaps by token-set similarity.

    If ``registry`` is given, each cluster is annotated with an existing skill
    that already covers it (so we never propose a duplicate).
    """
    clusters: List[GapCluster] = []
    for gap in gaps:
        text = gap.get("text", "")
        toks = set(_gap_tokens(text))
        if not toks:
            continue
        placed = False
        for c in clusters:
            if _jaccard(toks, c.tokens) >= _SIM:
                c.tokens |= toks
                c.samples.append(text)
                placed = True
                break
        if not placed:
            clusters.append(GapCluster(key="", tokens=set(toks), samples=[text]))

    for c in clusters:
        # Label: the tokens shared by the most samples, up to 3.
        c.key = " / ".join(_top_tokens(c.samples, 3)) or next(iter(c.tokens))
        if registry is not None:
            c.matched_skill = _matching_skill(c.tokens, registry)

    clusters.sort(key=lambda c: (-c.count, c.key))
    return clusters


def _top_tokens(samples: List[str], n: int) -> List[str]:
    counts: Dict[str, int] = {}
    for s in samples:
        for t in set(_gap_tokens(s)):
            counts[t] = counts.get(t, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in ordered[:n]]


def _matching_skill(tokens: set, registry: Registry) -> Optional[str]:
    best: Optional[str] = None
    best_sim = 0.0
    for skill in registry:
        s_toks = set(_tokens(f"{skill.name} {skill.description}"))
        sim = _jaccard(tokens, s_toks)
        if sim > best_sim:
            best_sim, best = sim, skill.name
    return best if best_sim >= _SIM else None


@dataclass
class AuthoringProposal:
    suggested_name: str
    description: str
    cluster: GapCluster

    @property
    def brief(self) -> str:
        bullets = "\n".join(f"  - {s}" for s in self.cluster.samples)
        return (
            f"Capability gap observed {self.cluster.count} time(s): "
            f"{self.cluster.key}\n"
            f"Recorded needs:\n{bullets}"
        )


def propose_authoring(
    registry: Registry,
    gaps: Optional[List[Dict]] = None,
    *,
    threshold: int = GAP_THRESHOLD,
) -> List[AuthoringProposal]:
    """Propose new skills for recurring, uncovered gaps."""
    gaps = gaps if gaps is not None else store.read_gaps()
    out: List[AuthoringProposal] = []
    for c in cluster_gaps(gaps, registry):
        if c.count < threshold or c.matched_skill is not None:
            continue
        name = slugify(c.key)
        # Avoid colliding with an existing skill directory name.
        if registry.get(name) is not None:
            name = f"{name}-skill"
        desc = f"Handles {c.key} tasks (drafted by Quartermaster from {c.count} observed gaps)."
        out.append(AuthoringProposal(suggested_name=name, description=desc, cluster=c))
    return out


_STUB_BODY = """# {title}

> **Probationary skill** drafted by Quartermaster's authoring arm.
> Run `skill-creator` to flesh out the instructions below, then
> `qm graduate {name}` once it has proven useful.

## Why this exists

{brief}

## Instructions

TODO: replace this section with concrete, step-by-step guidance.
`skill-creator` can generate it from the brief above.
"""


def scaffold(
    skills_dir: Path,
    name: str,
    description: str,
    *,
    brief: str = "",
    state_overlay: bool = True,
) -> Path:
    """Write a probationary SKILL.md stub and admit the skill on probation.

    Returns the path to the new SKILL.md. The skill is created `active` (no
    invocation flags) so it is usable immediately, and marked probationary in
    the local overlay. The transition is logged to the audit trail.
    """
    skills_dir = Path(skills_dir)
    target = skills_dir / name
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    target.mkdir(parents=True)

    title = name.replace("-", " ").title()
    fm = f"---\nname: {name}\ndescription: {description}\n---\n\n"
    body = _STUB_BODY.format(title=title, name=name, brief=brief or "(no brief provided)")
    path = target / "SKILL.md"
    path.write_text(fm + body, encoding="utf-8")

    if state_overlay:
        store.set_probation(name, brief=brief)
    store.record_transition(
        name, "(absent)", "probationary", path=path, actor="authoring",
        reason="drafted from capability gap",
    )
    return path


def graduate(skill_name: str) -> bool:
    """End a skill's probation (it has proven useful). Logged, reversible."""
    if store.clear_probation(skill_name):
        store.record_transition(
            skill_name, "probationary", "active", actor="qm",
            reason="graduated from probation",
        )
        return True
    return False
