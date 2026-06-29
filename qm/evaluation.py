"""Evaluation helpers for layered Quartermaster behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from . import conflicts, metadata, report
from .compile import compile_loadout
from .registry import ARCHIVED, Registry


@dataclass(frozen=True)
class Evaluation:
    intent: str
    total_skills: int
    kept: int
    guardrails_total: int
    guardrails_kept: int
    guardrail_recall: float
    blocked_count: int
    conflict_count: int
    archived_count: int
    saved_tokens: int
    context_tokens: int

    def as_dict(self) -> Dict:
        return {
            "intent": self.intent,
            "total_skills": self.total_skills,
            "kept": self.kept,
            "guardrails_total": self.guardrails_total,
            "guardrails_kept": self.guardrails_kept,
            "guardrail_recall": self.guardrail_recall,
            "blocked_count": self.blocked_count,
            "conflict_count": self.conflict_count,
            "archived_count": self.archived_count,
            "saved_tokens": self.saved_tokens,
            "context_tokens": self.context_tokens,
        }


def evaluate(registry: Registry, intent: str, *, cap: int = 30) -> Evaluation:
    plan = compile_loadout(registry, intent, cap=cap)
    guardrails = [s for s in registry if s.metadata.layer == metadata.GUARDRAIL]
    kept_guardrails = [s for s in plan.keep if s.layer == metadata.GUARDRAIL]
    summary = report.token_summary(registry)
    guardrail_recall = (
        len(kept_guardrails) / len(guardrails)
        if guardrails
        else 1.0
    )
    return Evaluation(
        intent=intent,
        total_skills=len(registry),
        kept=len(plan.keep),
        guardrails_total=len(guardrails),
        guardrails_kept=len(kept_guardrails),
        guardrail_recall=guardrail_recall,
        blocked_count=len(plan.blocked),
        conflict_count=len(conflicts.registry_conflicts(registry)),
        archived_count=len(registry.by_state(ARCHIVED)),
        saved_tokens=summary["saved_tokens"],
        context_tokens=summary["context_tokens"],
    )
