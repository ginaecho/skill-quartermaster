"""Apply lifecycle state transitions by configuring skill frontmatter flags.

Every transition is non-destructive (the SKILL.md stays on disk), logged to
the audit trail, and reversible. The only destructive operation, deletion, is
deliberately *not* in this module — it is gated behind explicit human approval
and handled separately.
"""

from __future__ import annotations

from typing import Optional

from . import frontmatter, store
from .registry import ACTIVE, DEMOTED, HIDDEN, Skill, derive_state

# Desired frontmatter flag configuration for each target state.
# None means "remove the key entirely".
_FLAGS = {
    ACTIVE: {"disable-model-invocation": None, "user-invocable": None},
    DEMOTED: {"disable-model-invocation": "true", "user-invocable": None},
    HIDDEN: {"disable-model-invocation": "true", "user-invocable": "false"},
}


class TransitionError(Exception):
    pass


def set_state(skill: Skill, target: str, *, reason: str = "", actor: str = "qm") -> str:
    """Move ``skill`` to ``target`` state, editing its file and logging it.

    Returns the previous state. A no-op (already in ``target``) still returns
    the state but writes nothing.
    """
    if target not in _FLAGS:
        raise TransitionError(f"unknown target state: {target!r}")

    text = skill.path.read_text(encoding="utf-8")
    fm = frontmatter.parse(text)
    if not fm.has_fence:
        raise TransitionError(
            f"{skill.path} has no frontmatter block to configure"
        )

    previous = derive_state(fm)
    if previous == target:
        return previous

    for key, value in _FLAGS[target].items():
        if value is None:
            fm.remove(key)
        else:
            fm.set(key, value)

    skill.path.write_text(fm.render(), encoding="utf-8")
    skill.state = target
    # A probationary skill that leaves active is no longer on trial — it either
    # failed probation (demoted/hidden) and should read as a plain skill.
    if target != ACTIVE and skill.probation:
        store.clear_probation(skill.name)
        skill.probation_since = None
    store.record_transition(
        skill.name, previous, target, path=skill.path, actor=actor, reason=reason
    )
    return previous


def demote(skill: Skill, **kw) -> str:
    return set_state(skill, DEMOTED, **kw)


def hide(skill: Skill, **kw) -> str:
    return set_state(skill, HIDDEN, **kw)


def activate(skill: Skill, **kw) -> str:
    return set_state(skill, ACTIVE, **kw)


def restore(skill: Skill, **kw) -> str:
    """Bring a skill all the way back to active (reverses demote/hide)."""
    return set_state(skill, ACTIVE, **kw)
