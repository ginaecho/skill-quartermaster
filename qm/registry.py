"""The registry: the shelf of every skill on disk and its lifecycle state.

State is *derived* from the selected runtime's frontmatter/config flags so that
the registry is always a faithful read of the filesystem — there is no separate
database that can drift out of sync. Quartermaster configures native runtime
primitives where possible; it does not invent a parallel source of truth.

State mapping (see README state table):

    active   : model can auto-load + user can invoke
    demoted  : disable-model-invocation: true        (manual-only)
    hidden   : + user-invocable: false               (out of context entirely)
    deleted  : not on disk (only ever reached via an approved deletion)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import adapters, frontmatter, metadata, store

ACTIVE = adapters.ACTIVE
DEMOTED = adapters.DEMOTED
HIDDEN = adapters.HIDDEN
ARCHIVED = "archived"

STATES = (ACTIVE, DEMOTED, HIDDEN, ARCHIVED)

# Backwards-compatible export for callers that referenced Claude defaults.
DEFAULT_SKILL_ROOTS = adapters.CLAUDE.default_roots


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
    probation_since: Optional[float] = None  # set if admitted on probation
    runtime: str = adapters.CLAUDE.name
    metadata: metadata.SkillMetadata = field(default_factory=metadata.SkillMetadata)

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def probation(self) -> bool:
        """A probationary skill is active but on trial (newly authored)."""
        return self.probation_since is not None

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
    """Backwards-compatible Claude state derivation helper."""
    return adapters.CLAUDE.derive_state(fm)


def _resolve_roots(skills_dir: Optional[Path] = None, runtime: Optional[str] = None) -> List[Path]:
    adapter = adapters.get(runtime)
    return adapters.resolve_roots(adapter=adapter, skills_dir=skills_dir)


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
        skills_dir: Optional[Path] = None,
        last_used: Optional[Dict[str, float]] = None,
        probation: Optional[Dict[str, Dict]] = None,
        runtime: Optional[str] = None,
        include_archived: bool = False,
    ) -> "Registry":
        last_used = last_used or {}
        probation = probation or {}
        adapter = adapters.get(runtime)
        skills: List[Skill] = []
        for root in adapters.resolve_roots(adapter=adapter, skills_dir=skills_dir):
            if not root.exists():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                fm = frontmatter.parse(skill_md.read_text(encoding="utf-8"))
                name = fm.get("name") or skill_md.parent.name
                description = fm.get("description", "") or ""
                prob = probation.get(name) or {}
                since = prob.get("admitted") if isinstance(prob, dict) else None
                state = adapter.derive_state(fm)
                meta = metadata.parse(fm, name=name, description=description)
                skills.append(
                    Skill(
                        name=name,
                        path=skill_md,
                        description=description,
                        state=state,
                        last_used=last_used.get(name),
                        probation_since=since if isinstance(since, (int, float)) else None,
                        runtime=adapter.name,
                        metadata=meta,
                    )
                )
                store.note_skill_seen(
                    name,
                    path=skill_md,
                    state=state,
                    runtime=adapter.name,
                    metadata=asdict(meta),
                )
        if include_archived:
            from . import archive

            for entry in archive.read_index().values():
                skill_md = Path(entry.get("archive_path", "")) / "SKILL.md"
                if not skill_md.exists():
                    continue
                fm = frontmatter.parse(skill_md.read_text(encoding="utf-8"))
                name = fm.get("name") or entry.get("name") or skill_md.parent.name
                description = fm.get("description", "") or ""
                meta = metadata.parse(fm, name=name, description=description)
                skills.append(
                    Skill(
                        name=name,
                        path=skill_md,
                        description=description,
                        state=ARCHIVED,
                        last_used=last_used.get(name),
                        probation_since=None,
                        runtime=entry.get("runtime") or adapter.name,
                        metadata=meta,
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
