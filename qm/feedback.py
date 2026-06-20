"""Feedback ingestion (v0.5): parse plain-language complaints into signals.

The agent does the toil; the human just talks. A free-text complaint is routed
to the right lever:

    * a *style* miss      -> append to the always-on style file (constitution)
    * a *capability* miss -> record a gap (feeds the authoring arm)
    * "stop suggesting X" -> propose demoting the named skill
    * "I keep using X"    -> propose promoting/restoring the named skill

Classification is deliberately transparent keyword matching (not a model call),
so the user can always see *why* a complaint was routed the way it was. When the
signal is ambiguous, we say so rather than guessing — nothing is applied
automatically except the local style note and gap log, both reversible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from . import store
from .compile import _tokens
from .registry import ACTIVE, DEMOTED, HIDDEN, Registry

# Single-word and phrase markers per category. Phrases are matched as
# substrings on the lowercased text; words against the token set.
_STYLE_WORDS = {
    "style", "format", "formatting", "tone", "prefer", "preference",
    "convention", "conventions", "naming", "indent", "indentation", "quotes",
    "spacing", "lint", "consistent", "consistency", "wording", "voice",
    "verbose", "concise", "comment", "comments", "docstring", "aesthetic",
    "readable", "readability",
}
_STYLE_PHRASES = (
    "my style", "isn't matching", "isnt matching", "not matching my",
    "coding style", "code style", "match my", "the way it writes",
)

_CAPABILITY_WORDS = {
    "missing", "lack", "lacks", "lacking", "unable", "wish", "gap",
    "failed", "failing", "fails",
}
_CAPABILITY_PHRASES = (
    "no skill", "couldn't", "couldnt", "can't", "cant", "cannot",
    "doesn't handle", "doesnt handle", "don't have a", "dont have a",
    "kept needing", "keep needing", "i need a", "needed to", "nothing handles",
    "no matching", "wish it could",
)

_DEMOTE_PHRASES = (
    "stop suggesting", "stop using", "keeps firing", "keeps suggesting",
    "don't want", "dont want", "too noisy", "irrelevant", "annoying",
    "shouldn't fire", "shouldnt fire", "wrong skill", "stop loading",
    "turn off", "disable",
)
_PROMOTE_PHRASES = (
    "keep using", "keep invoking", "always use", "rely on", "i love",
    "every time i use", "constantly use", "bring back", "favorite",
)


@dataclass
class Signal:
    kind: str                       # style|capability|demote|promote|ambiguous
    detail: str
    skill: Optional[str] = None     # named skill, when relevant
    scores: dict = field(default_factory=dict)


def _phrase_hits(text: str, phrases) -> int:
    return sum(1 for p in phrases if p in text)


def find_named_skill(text: str, registry: Registry) -> Optional[str]:
    """Return a skill named in the feedback, if any.

    Matches on the exact skill name first, then on a distinctive name word
    (>= 4 chars) so "the docx skill" resolves to "docx-writer".
    """
    low = text.lower()
    names = [s.name for s in registry]
    for name in sorted(names, key=len, reverse=True):
        if name.lower() in low:
            return name
    toks = set(_tokens(text))
    for name in names:
        for w in _tokens(name):
            if len(w) >= 4 and w in toks:
                return name
    return None


def classify(text: str, registry: Optional[Registry] = None) -> Signal:
    low = text.lower()
    toks = set(_tokens(text))

    # Explicit phrases ("needed to", "no skill", "stop suggesting") are stronger
    # signals of intent than an incidental topic word ("lint", "format"), which
    # can belong to either category — so weight phrase hits more heavily.
    style = 2 * _phrase_hits(low, _STYLE_PHRASES) + len(toks & _STYLE_WORDS)
    capability = 2 * _phrase_hits(low, _CAPABILITY_PHRASES) + len(toks & _CAPABILITY_WORDS)
    demote = 2 * _phrase_hits(low, _DEMOTE_PHRASES)
    promote = 2 * _phrase_hits(low, _PROMOTE_PHRASES)

    named = find_named_skill(text, registry) if registry is not None else None
    scores = {"style": style, "capability": capability, "demote": demote, "promote": promote}

    # A named skill plus a clear directive routes to promote/demote first.
    if named and demote and demote >= promote:
        return Signal("demote", f"demote {named}", skill=named, scores=scores)
    if named and promote and promote > demote:
        return Signal("promote", f"promote {named}", skill=named, scores=scores)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second_score = ranked[1][1]
    if top_score == 0 or top_score == second_score:
        return Signal("ambiguous", text.strip(), skill=named, scores=scores)
    return Signal(top, text.strip(), skill=named, scores=scores)


@dataclass
class IngestResult:
    signal: Signal
    applied: str           # human-readable description of what changed
    follow_up: str = ""    # suggested next command, if any


def ingest(text: str, registry: Registry) -> IngestResult:
    """Route a complaint to the right lever and apply the safe part of it.

    Style notes and gap records are written immediately (both reversible/local).
    Promote/demote are surfaced as a suggestion for the user to confirm — we do
    not silently move skills based on a parsed sentence.
    """
    sig = classify(text, registry)

    if sig.kind == "style":
        path = store.append_style(text)
        return IngestResult(sig, f"noted style preference in {path}")

    if sig.kind == "capability":
        store.record_gap(text, context="feedback")
        return IngestResult(
            sig,
            "recorded a capability gap",
            follow_up="qm gaps   # review whether to author a new skill",
        )

    if sig.kind == "demote" and sig.skill:
        return IngestResult(
            sig,
            f"suggests demoting '{sig.skill}'",
            follow_up=f"qm demote {sig.skill}",
        )

    if sig.kind == "promote" and sig.skill:
        return IngestResult(
            sig,
            f"suggests restoring/promoting '{sig.skill}'",
            follow_up=f"qm restore {sig.skill}",
        )

    return IngestResult(
        sig,
        "couldn't confidently classify this feedback",
        follow_up='Rephrase, or use qm gap / qm demote / qm restore directly.',
    )
