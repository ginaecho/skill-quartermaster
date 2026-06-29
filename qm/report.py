"""Human-facing formatting: the status table and the token-saved report.

The token-saved number is the headline artifact ("200 skills -> 12 loaded ->
~8k tokens saved -> 0 deleted"), so it lives here as first-class output.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from .registry import ACTIVE, ARCHIVED, DEMOTED, HIDDEN, Registry, Skill

_STATE_GLYPH = {ACTIVE: "●", DEMOTED: "◐", HIDDEN: "○", ARCHIVED: "□"}


def _fmt_age(last_used: Optional[float], now: float) -> str:
    if last_used is None:
        return "never"
    days = (now - last_used) / 86400.0
    if days < 1:
        return "today"
    if days < 2:
        return "1d ago"
    return f"{days:.0f}d ago"


def _human_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def token_summary(registry: Registry) -> Dict[str, int]:
    """Compute the headline numbers."""
    total = len(registry)
    active = registry.by_state(ACTIVE)
    demoted = registry.by_state(DEMOTED)
    hidden = registry.by_state(HIDDEN)
    archived = registry.by_state(ARCHIVED)

    context_tokens = sum(s.index_tokens for s in active + demoted)
    saved_tokens = sum(s.index_tokens for s in hidden)
    baseline_tokens = context_tokens + saved_tokens

    return {
        "total": total,
        "active": len(active),
        "demoted": len(demoted),
        "hidden": len(hidden),
        "archived": len(archived),
        "loaded": len(active),  # auto-loadable
        "in_context": len(active) + len(demoted),
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "baseline_tokens": baseline_tokens,
    }


def render_headline(registry: Registry) -> str:
    s = token_summary(registry)
    return (
        f"{s['total']} skills installed  →  "
        f"{s['loaded']} loaded for this project  →  "
        f"~{_human_tokens(s['saved_tokens'])} tokens saved  →  "
        f"0 deleted"
    )


def render_status(
    registry: Registry,
    *,
    now: Optional[float] = None,
    show_layers: bool = False,
) -> str:
    now = now if now is not None else time.time()
    skills: List[Skill] = registry.all
    if not skills:
        return "No skills found. Set QM_SKILLS_DIR or run inside a project with runtime skills."

    name_w = max(4, min(32, max(len(s.name) for s in skills)))
    rows = []
    if show_layers:
        header = (
            f"  {'SKILL'.ljust(name_w)}  {'STATE':<8} {'LAYER':<10} "
            f"{'PRI':>4} {'LAST USED':<10} {'TOKENS':>7}"
        )
    else:
        header = f"  {'SKILL'.ljust(name_w)}  {'STATE':<8} {'LAST USED':<10} {'TOKENS':>7}"
    rows.append(header)
    rows.append("  " + "-" * (len(header) - 2))
    for s in skills:
        glyph = "◉" if s.probation else _STATE_GLYPH.get(s.state, "?")
        label = "prob" if s.probation else s.state
        tok = _human_tokens(s.index_tokens) if s.indexed else "-"
        base = f"  {s.name[:name_w].ljust(name_w)}  {glyph} {label:<6} "
        if show_layers:
            rows.append(
                f"{base}"
                f"{s.metadata.layer:<10} "
                f"{s.metadata.priority:>4} "
                f"{_fmt_age(s.last_used, now):<10} "
                f"{tok:>7}"
            )
        else:
            rows.append(
                f"{base}"
                f"{_fmt_age(s.last_used, now):<10} "
                f"{tok:>7}"
            )

    summary = token_summary(registry)
    probationary = [s for s in skills if s.probation]
    rows.append("")
    rows.append(
        f"  {summary['total']} skills  ·  "
        f"{summary['active']} active  ·  "
        f"{summary['demoted']} demoted  ·  "
        f"{summary['hidden']} hidden"
        + (f"  ·  {summary['archived']} archived" if summary["archived"] else "")
        + (f"  ·  {len(probationary)} on probation" if probationary else "")
    )
    rows.append(
        f"  context: ~{_human_tokens(summary['context_tokens'])} tokens"
        f"   saved by hiding: ~{_human_tokens(summary['saved_tokens'])} tokens"
        f"   (0 deleted)"
    )
    return "\n".join(rows)
