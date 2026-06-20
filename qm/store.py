"""Local-only state store: audit log and usage telemetry.

Everything Quartermaster records lives on disk under a single directory
(default ``~/.quartermaster``, override with ``QM_HOME``). Nothing is ever
sent over the network — telemetry is local-only by design, because we are
asking users to trust a tool that touches their skills.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional


def home() -> Path:
    return Path(os.environ.get("QM_HOME", Path.home() / ".quartermaster"))


def _ensure_home() -> Path:
    h = home()
    h.mkdir(parents=True, exist_ok=True)
    return h


def _audit_path() -> Path:
    return _ensure_home() / "audit.jsonl"


def _usage_path() -> Path:
    return _ensure_home() / "usage.jsonl"


# --- Audit log -----------------------------------------------------------

def record_transition(
    skill: str,
    from_state: str,
    to_state: str,
    *,
    path: str = "",
    actor: str = "qm",
    reason: str = "",
) -> Dict:
    """Append a state-transition entry to the audit log and return it."""
    entry = {
        "ts": time.time(),
        "skill": skill,
        "from": from_state,
        "to": to_state,
        "path": str(path),
        "actor": actor,
        "reason": reason,
    }
    with _audit_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read_audit() -> List[Dict]:
    p = _audit_path()
    if not p.exists():
        return []
    out: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# --- Usage telemetry -----------------------------------------------------

def record_usage(skill: str, *, ts: Optional[float] = None) -> None:
    """Record that ``skill`` fired. Called by the PreToolUse hook."""
    entry = {"ts": ts if ts is not None else time.time(), "skill": skill}
    with _usage_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def last_used_map() -> Dict[str, float]:
    """Map of skill name -> most recent usage timestamp."""
    p = _usage_path()
    if not p.exists():
        return {}
    out: Dict[str, float] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = entry.get("skill")
        ts = entry.get("ts")
        if name and isinstance(ts, (int, float)):
            if name not in out or ts > out[name]:
                out[name] = ts
    return out
