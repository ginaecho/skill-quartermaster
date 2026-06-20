"""Round-trip-safe YAML frontmatter parsing for SKILL.md files.

Quartermaster only ever touches a small set of known keys
(``disable-model-invocation``, ``user-invocable``). To avoid depending on
PyYAML (which is not guaranteed to be present in a Claude Code environment)
and to avoid reformatting a user's skill files, this module operates on the
raw frontmatter lines and edits only the keys it is asked to.

A SKILL.md looks like::

    ---
    name: my-skill
    description: Does the thing.
    disable-model-invocation: true
    ---
    # body...

The body is preserved byte-for-byte. Only the frontmatter block is rewritten,
and within it only the requested keys change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


_FENCE = "---"


@dataclass
class Frontmatter:
    """A parsed frontmatter block plus the document body.

    ``lines`` holds the raw frontmatter lines (without the ``---`` fences),
    which lets us round-trip formatting we don't understand. ``values`` is a
    convenience mapping of the simple ``key: value`` pairs we do understand.
    """

    lines: List[str] = field(default_factory=list)
    body: str = ""
    has_fence: bool = True

    @property
    def values(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for line in self.lines:
            key, sep, val = line.partition(":")
            if not sep:
                continue
            key = key.strip()
            if not key or key.startswith("#") or key.startswith(" "):
                # skip comments and nested/continuation lines
                continue
            out[key] = val.strip()
        return out

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.values.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in ("true", "yes", "1", "on")

    def set(self, key: str, value: str) -> None:
        """Set ``key`` to ``value``, updating in place or appending."""
        for i, line in enumerate(self.lines):
            existing, sep, _ = line.partition(":")
            if sep and existing.strip() == key:
                self.lines[i] = f"{key}: {value}"
                return
        self.lines.append(f"{key}: {value}")

    def remove(self, key: str) -> bool:
        """Remove ``key`` if present. Returns True if something was removed."""
        for i, line in enumerate(list(self.lines)):
            existing, sep, _ = line.partition(":")
            if sep and existing.strip() == key:
                del self.lines[i]
                return True
        return False

    def render(self) -> str:
        if not self.has_fence:
            return self.body
        block = "\n".join(self.lines)
        return f"{_FENCE}\n{block}\n{_FENCE}\n{self.body}"


def parse(text: str) -> Frontmatter:
    """Parse document text into a :class:`Frontmatter`.

    If there is no frontmatter fence, returns one with ``has_fence=False`` and
    the whole text as the body.
    """
    # Normalise leading BOM / whitespace-only first line handling minimally.
    if not text.startswith(_FENCE):
        return Frontmatter(lines=[], body=text, has_fence=False)

    rest = text[len(_FENCE):]
    # The opening fence must be followed by a newline.
    if not rest.startswith("\n"):
        return Frontmatter(lines=[], body=text, has_fence=False)
    rest = rest[1:]

    closing = rest.find(f"\n{_FENCE}")
    if closing == -1:
        # Unterminated frontmatter; treat as plain body.
        return Frontmatter(lines=[], body=text, has_fence=False)

    block = rest[:closing]
    after = rest[closing + 1 + len(_FENCE):]
    if after.startswith("\n"):
        after = after[1:]

    lines = block.split("\n") if block else []
    return Frontmatter(lines=lines, body=after, has_fence=True)
