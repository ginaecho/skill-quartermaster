"""The lifecycle policy engine: it *proposes*, it never executes.

Proposals are returned as plain data so the CLI can batch them into a single
human-approval surface. No file is touched here — that only happens once the
human says yes and the CLI calls into :mod:`qm.transitions`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from .registry import ACTIVE, DEMOTED, HIDDEN, Registry, Skill

# "probationary" is an overlay label (see qm.authoring), not a registry state.
PROBATION = "probationary"

DAY = 86400.0

# Defaults; the CLI exposes overrides.
DEMOTE_AFTER_DAYS = 14
HIDE_AFTER_DAYS = 30
PROBATION_DAYS = 14


@dataclass
class Proposal:
    skill: str
    action: str  # "demote" | "hide" | "promote"
    from_state: str
    to_state: str
    reason: str


def _age_days(skill: Skill, now: float) -> Optional[float]:
    if skill.last_used is None:
        return None
    return (now - skill.last_used) / DAY


def _probation_age_days(skill: Skill, now: float) -> Optional[float]:
    if skill.probation_since is None:
        return None
    return (now - skill.probation_since) / DAY


def propose(
    registry: Registry,
    *,
    demote_after_days: int = DEMOTE_AFTER_DAYS,
    hide_after_days: int = HIDE_AFTER_DAYS,
    probation_days: int = PROBATION_DAYS,
    now: Optional[float] = None,
) -> List[Proposal]:
    """Return the batch of transitions the engine would recommend.

    Rules (all reversible, none destructive):
      * graduate-if-used : probationary skill used since admission -> active
      * demote-if-expired: probationary skill unused past probation_days
      * demote-if-unused : active skill unused for >= demote_after_days
      * hide-if-unused   : demoted skill unused for >= hide_after_days
      * promote-if-used  : demoted skill used since being demoted -> active
    """
    now = now if now is not None else time.time()
    out: List[Proposal] = []

    for skill in registry:
        age = _age_days(skill, now)

        if skill.probation:
            # Probationary skills are on trial; judge them on their own window
            # before the generic active rules apply.
            used_since_admit = (
                skill.last_used is not None
                and skill.probation_since is not None
                and skill.last_used >= skill.probation_since
            )
            if used_since_admit:
                out.append(
                    Proposal(
                        skill.name, "graduate", PROBATION, ACTIVE,
                        "used during probation — proven useful",
                    )
                )
            elif (_probation_age_days(skill, now) or 0) >= probation_days:
                out.append(
                    Proposal(
                        skill.name, "demote", PROBATION, DEMOTED,
                        f"probation expired unused (>= {probation_days}d)",
                    )
                )
            continue

        if skill.state == ACTIVE:
            if age is not None and age >= demote_after_days:
                out.append(
                    Proposal(
                        skill.name, "demote", ACTIVE, DEMOTED,
                        f"unused for {age:.0f}d (>= {demote_after_days}d)",
                    )
                )
            elif skill.last_used is None and demote_after_days <= 0:
                out.append(
                    Proposal(
                        skill.name, "demote", ACTIVE, DEMOTED,
                        "never observed firing",
                    )
                )

        elif skill.state == DEMOTED:
            if age is not None and age < demote_after_days:
                # It's been used recently despite being demoted -> promote.
                out.append(
                    Proposal(
                        skill.name, "promote", DEMOTED, ACTIVE,
                        f"used {age:.0f}d ago while demoted",
                    )
                )
            elif age is None or age >= hide_after_days:
                detail = (
                    f"unused for {age:.0f}d (>= {hide_after_days}d)"
                    if age is not None
                    else "never observed firing"
                )
                out.append(
                    Proposal(skill.name, "hide", DEMOTED, HIDDEN, detail)
                )

    return out
