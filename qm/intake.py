"""Trusted external skill intake.

The intake path is deliberately local-first and non-executing: users clone or
download a public repo themselves, then Quartermaster scans SKILL.md files,
scores value, flags risk, and only copies approved skills with `--yes`.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from . import frontmatter, metadata

SUSPICIOUS_PATTERNS = (
    r"\bcurl\b.*\|.*\bsh\b",
    r"\bwget\b.*\|.*\bsh\b",
    r"\brm\s+-rf\b",
    r"\bsudo\b",
    r"\bchmod\s+\+x\b",
    r"\beval\b",
    r"\bbase64\s+-d\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\btoken\b.*\b(exfiltrate|upload|send)\b",
    r"\bsecret\b.*\b(exfiltrate|upload|send)\b",
)

HIGH_VALUE_TERMS = {
    "security", "test", "testing", "review", "guardrail", "python", "typescript",
    "github", "ci", "docker", "database", "postgres", "fastapi", "react",
    "refactor", "documentation", "terraform", "kubernetes",
}


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    trust: str
    rationale: str


CURATED_SOURCES = (
    Source(
        "anthropics-skills",
        "https://github.com/anthropics/skills",
        "high",
        "Official Anthropic skills repository; prefer as the first external corpus.",
    ),
    Source(
        "claude-code-templates",
        "https://github.com/davila7/claude-code-templates",
        "medium",
        "Large community corpus useful for breadth; requires strict filtering.",
    ),
    Source(
        "obra-superpowers",
        "https://github.com/obra/superpowers",
        "medium",
        "Small workflow-oriented community skill set; scan before import.",
    ),
)


@dataclass
class IntakeCandidate:
    name: str
    path: Path
    description: str
    layer: str
    value_score: int
    risk_flags: List[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.risk_flags and self.value_score >= 3


def curated_sources() -> List[Source]:
    return list(CURATED_SOURCES)


def scan(root: Path) -> List[IntakeCandidate]:
    root = Path(root)
    candidates: List[IntakeCandidate] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        if ".git" in skill_md.parts:
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        fm = frontmatter.parse(text)
        name = fm.get("name") or skill_md.parent.name
        description = fm.get("description", "") or ""
        meta = metadata.parse(fm, name=name, description=description)
        candidates.append(
            IntakeCandidate(
                name=name,
                path=skill_md,
                description=description,
                layer=meta.layer,
                value_score=_value_score(name, description, meta),
                risk_flags=_risk_flags(text),
            )
        )
    candidates.sort(key=lambda c: (-int(c.accepted), -c.value_score, c.name.lower()))
    return candidates


def import_candidates(candidates: Iterable[IntakeCandidate], target_root: Path, *, limit: int = 10) -> List[Path]:
    target_root = Path(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for cand in candidates:
        if not cand.accepted:
            continue
        dest = target_root / cand.name
        if dest.exists():
            continue
        shutil.copytree(cand.path.parent, dest)
        copied.append(dest / "SKILL.md")
        if len(copied) >= limit:
            break
    return copied


def _risk_flags(text: str) -> List[str]:
    low = text.lower()
    flags = []
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, low):
            flags.append(pattern)
    return flags


def _value_score(name: str, description: str, meta: metadata.SkillMetadata) -> int:
    words = set(re.findall(r"[a-z0-9]+", f"{name} {description} {' '.join(meta.tags)}".lower()))
    score = len(words & HIGH_VALUE_TERMS)
    if meta.layer == metadata.GUARDRAIL:
        score += 3
    if meta.priority > 0:
        score += 1
    if len(description) >= 40:
        score += 1
    return score
