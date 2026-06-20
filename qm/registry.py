"""The registry: the shelf of every skill on disk and its lifecycle state.

State is *derived* from the skill's own frontmatter flags so that the registry
is always a faithful read of the filesystem — there is no separate database
that can drift out of sync. Quartermaster configures existing Claude Code
primitives; it does not invent a parallel source of truth.

State mapping (see README state table):

    active   : model can auto-load + user can invoke
    demoted  : disable-model-invocation: true        (manual-only)
    hidden   : + user-invocable: false               (out of context entirely)
    deleted  : not on disk (only ever reached via an approved deletion)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import frontmatter

ACTIVE = "active"
DEMOTED = "demoted"
HIDDEN = "hidden"

STATES = (ACTIVE, DEMOTED, HIDDEN)

# Standard locations Claude Code loads skills from. Project scope first so a
# project's own skills win in listings. These are scanned when no explicit
# skills directory is configured.
DEFAULT_SKILL_ROOTS = (
    Path(".claude/skills"),
    Path.home() / ".claude" / "skills",
)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), the standard heuristic.

    We count only what progressive disclosure actually loads up front: the
    skill's name + description. The body is not loaded until the skill fires,
    so it does not contribute to the standing context cost.
    """
    return max(1, round(len(text) / 4))


@dataclass
class Skill:
    name: str
    path: Path  # path to the SKILL.md file
    description: str
    state: str
    last_used: Optional[float] = None  # epoch seconds, None if never recorded

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def indexed(self) -> bool:
        """Whether this skill's description sits in the context window."""
        return self.state in (ACTIVE, DEMOTED)

    @property
    def auto_loadable(self) -> bool:
        return self.state == ACTIVE

    @property
    def index_tokens(self) -> int:
        """Token cost this skill imposes on context when indexed."""
        return _estimate_tokens(f"{self.name}: {self.description}")


def derive_state(fm: frontmatter.Frontmatter) -> str:
    disabled = fm.get_bool("disable-model-invocation", False)
    user_invocable = fm.get_bool("user-invocable", True)
    if disabled and not user_invocable:
        return HIDDEN
    if disabled:
        return DEMOTED
    return ACTIVE


def _resolve_roots(skills_dir: Optional[os.PathLike] = None) -> List[Path]:
    if skills_dir is not None:
        return [Path(skills_dir)]
    env = os.environ.get("QM_SKILLS_DIR")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p]
    return [p for p in DEFAULT_SKILL_ROOTS]


class Registry:
    """An index of skills discovered under one or more roots."""

    def __init__(self, skills: List[Skill]):
        self._skills = sorted(skills, key=lambda s: s.name.lower())
        self._by_name: Dict[str, Skill] = {}
        for s in self._skills:
            # First writer wins (roots are scanned in priority order).
            self._by_name.setdefault(s.name, s)

    @classmethod
    def load(
        cls,
        skills_dir: Optional[os.PathLike] = None,
        last_used: Optional[Dict[str, float]] = None,
    ) -> "Registry":
        last_used = last_used or {}
        skills: List[Skill] = []
        for root in _resolve_roots(skills_dir):
            if not root.exists():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                fm = frontmatter.parse(skill_md.read_text(encoding="utf-8"))
                name = fm.get("name") or skill_md.parent.name
                skills.append(
                    Skill(
                        name=name,
                        path=skill_md,
                        description=fm.get("description", "") or "",
                        state=derive_state(fm),
                        last_used=last_used.get(name),
                    )
                )
        return cls(skills)

    def __iter__(self):
        return iter(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def get(self, name: str) -> Optional[Skill]:
        return self._by_name.get(name)

    def by_state(self, state: str) -> List[Skill]:
        return [s for s in self._skills if s.state == state]

    @property
    def all(self) -> List[Skill]:
        return list(self._skills)
