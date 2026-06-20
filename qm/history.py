"""One-click revert (v1.0): undo automatic changes from the audit trail.

The audit log is the trust spine — every transition is recorded, so every
transition can be walked back. ``revert`` finds the most recent reversible
entries and applies their inverse, logging the reversal itself so the trail
stays complete.

Two transitions are intentionally *not* auto-reversible:
  * a deletion (``to == "deleted"``) — the file is gone; nothing to restore.
  * a skill admission (``from == "(absent)"``) — undoing it would delete a
    skill, which must stay human-gated. We surface it instead of doing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import store, transitions
from .registry import ACTIVE, DEMOTED, HIDDEN, Registry

_REAL_STATES = {ACTIVE, DEMOTED, HIDDEN}
PROBATION = "probationary"
ABSENT = "(absent)"
DELETED = "deleted"


@dataclass
class RevertPlan:
    entry: Dict
    skill: str
    target: str           # state/overlay to restore to
    note: str             # how it will be reverted

    @property
    def describe(self) -> str:
        return f"{self.skill}: {self.entry['to']} → {self.target}  ({self.note})"


class RevertError(Exception):
    pass


def _is_revert_entry(entry: Dict) -> bool:
    return str(entry.get("reason", "")).startswith("revert of ")


def plan_revert(
    registry: Registry,
    *,
    limit: int = 1,
    skill: Optional[str] = None,
) -> List[RevertPlan]:
    """Build a list of reversible plans, most recent first.

    Skips deletions, admissions, and prior reverts. ``limit`` caps how many are
    returned; ``skill`` restricts to a single skill's history.
    """
    plans: List[RevertPlan] = []
    for entry in reversed(store.read_audit()):
        if len(plans) >= limit:
            break
        if skill is not None and entry.get("skill") != skill:
            continue
        if _is_revert_entry(entry):
            continue

        frm, to = entry.get("from"), entry.get("to")
        name = entry.get("skill")

        if to == DELETED or frm == ABSENT:
            # Not auto-reversible; record nothing, let the caller report it.
            plans.append(RevertPlan(entry, name, target="(blocked)",
                                    note="deletion/admission — human-gated"))
            continue

        sk = registry.get(name)
        if sk is None:
            plans.append(RevertPlan(entry, name, target="(missing)",
                                    note="skill no longer on disk"))
            continue

        if frm == PROBATION:
            # A graduation; reverting re-marks it probationary (stays active).
            plans.append(RevertPlan(entry, name, target=PROBATION,
                                    note="restore probation"))
        elif frm in _REAL_STATES:
            plans.append(RevertPlan(entry, name, target=frm,
                                    note=f"set back to {frm}"))
        else:
            plans.append(RevertPlan(entry, name, target="(blocked)",
                                    note=f"unrecognized prior state {frm!r}"))

    return plans


def apply_revert(registry: Registry, plan: RevertPlan) -> bool:
    """Apply a single revert plan. Returns True if anything changed."""
    if plan.target in ("(blocked)", "(missing)"):
        return False

    reason = f"revert of {plan.entry.get('ts')}"
    if plan.target == PROBATION:
        store.set_probation(plan.skill)
        store.record_transition(plan.skill, ACTIVE, PROBATION, reason=reason)
        return True

    sk = registry.get(plan.skill)
    if sk is None:
        return False
    prev = transitions.set_state(sk, plan.target, reason=reason)
    return prev != plan.target
