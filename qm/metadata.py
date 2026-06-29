"""Skill metadata parsing and inference.

Metadata is optional. Quartermaster reads explicit `qm-*` frontmatter keys when
present and falls back to conservative heuristics for existing skills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from . import frontmatter

GUARDRAIL = "guardrail"
PLANNING = "planning"
DOMAIN = "domain"
ACTION = "action"
TOOL = "tool"
STYLE = "style"

LAYERS = (GUARDRAIL, PLANNING, DOMAIN, ACTION, TOOL, STYLE)

_SPLIT = re.compile(r"[,;\n]+")
_WORD = re.compile(r"[a-z0-9]+")

_LAYER_HINTS = (
    (GUARDRAIL, {
        "auth", "compliance", "credential", "credentials", "guardrail",
        "harden", "privacy", "safe", "safety", "secret", "secrets",
        "secure", "security", "threat", "vulnerability",
    }),
    (STYLE, {
        "comment", "comments", "convention", "format", "formatting",
        "lint", "naming", "style", "tone", "voice",
    }),
    (TOOL, {
        "api", "browser", "cli", "database", "github", "mcp", "postgres",
        "redis", "tool", "tools",
    }),
    (ACTION, {
        "build", "commit", "deploy", "edit", "fix", "generate", "migrate",
        "publish", "refactor", "release", "run", "scaffold", "test",
    }),
    (PLANNING, {
        "architecture", "design", "plan", "planning", "review", "strategy",
    }),
)


@dataclass(frozen=True)
class SkillMetadata:
    layer: str = DOMAIN
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    risk: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    requires_guardrails: List[str] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)
    explicit_layer: bool = False


def _normalize_token(value: str) -> str:
    return "-".join(_WORD.findall(value.lower()))


def _unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        token = _normalize_token(value)
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def parse_list(raw: str) -> List[str]:
    """Parse a simple frontmatter scalar list.

    Supports comma/semicolon separated values and lightweight bracket notation
    such as `[security, secrets]`. This intentionally avoids a YAML dependency.
    """
    raw = (raw or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    raw = raw.replace('"', "").replace("'", "")
    return _unique(part.strip() for part in _SPLIT.split(raw))


def parse_priority(raw: str) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return 0


def infer_layer(name: str, description: str, tags: Iterable[str] = ()) -> str:
    text = " ".join([name, description, " ".join(tags)]).lower()
    words = set(_WORD.findall(text))
    for layer, hints in _LAYER_HINTS:
        if words & hints:
            return layer
    return DOMAIN


def parse(
    fm: frontmatter.Frontmatter,
    *,
    name: str = "",
    description: str = "",
) -> SkillMetadata:
    tags = parse_list(fm.get("qm-tags") or "")
    risk = parse_list(fm.get("qm-risk") or "")
    provides = parse_list(fm.get("qm-provides") or "")
    requires = parse_list(fm.get("qm-requires") or "")
    requires_guardrails = parse_list(fm.get("qm-requires-guardrails") or "")
    conflicts_with = parse_list(fm.get("qm-conflicts-with") or "")
    priority = parse_priority(fm.get("qm-priority") or "")

    raw_layer = _normalize_token(fm.get("qm-layer") or "")
    explicit_layer = raw_layer in LAYERS
    layer = raw_layer if explicit_layer else infer_layer(name, description, tags + risk)

    return SkillMetadata(
        layer=layer,
        priority=priority,
        tags=tags,
        risk=risk,
        provides=provides,
        requires=requires,
        requires_guardrails=requires_guardrails,
        conflicts_with=conflicts_with,
        explicit_layer=explicit_layer,
    )
