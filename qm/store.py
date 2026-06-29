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


def _gaps_path() -> Path:
    return _ensure_home() / "gaps.jsonl"


def _probation_path() -> Path:
    return _ensure_home() / "probation.json"


def _skills_history_path() -> Path:
    return _ensure_home() / "skills.json"


# --- Historical skill dictionary ----------------------------------------

def read_skill_history() -> Dict[str, Dict]:
    p = _skills_history_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_skill_history(data: Dict[str, Dict]) -> None:
    _skills_history_path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _history_entry(data: Dict[str, Dict], skill: str, *, ts: Optional[float] = None) -> Dict:
    now = ts if ts is not None else time.time()
    entry = data.setdefault(
        skill,
        {
            "first_seen": now,
            "last_seen": now,
            "last_used": None,
            "usage_count": 0,
            "selected_count": 0,
            "demoted_count": 0,
            "hidden_count": 0,
            "archive_count": 0,
            "states": {},
            "useful_intents": [],
            "conflict_notes": [],
            "archive_path": "",
            "path": "",
            "runtime": "",
            "metadata": {},
        },
    )
    entry.setdefault("first_seen", now)
    entry["last_seen"] = now
    return entry


def note_skill_seen(
    skill: str,
    *,
    path: str = "",
    state: str = "",
    runtime: str = "",
    metadata: Optional[Dict] = None,
    ts: Optional[float] = None,
) -> Dict:
    data = read_skill_history()
    entry = _history_entry(data, skill, ts=ts)
    if path:
        entry["path"] = str(path)
    if runtime:
        entry["runtime"] = runtime
    if metadata is not None:
        entry["metadata"] = metadata
    if state:
        states = entry.setdefault("states", {})
        states[state] = states.get(state, 0) + 1
        entry["state"] = state
    _write_skill_history(data)
    return entry


def note_skill_selected(skill: str, *, intent: str = "", ts: Optional[float] = None) -> Dict:
    data = read_skill_history()
    entry = _history_entry(data, skill, ts=ts)
    entry["selected_count"] = int(entry.get("selected_count") or 0) + 1
    if intent:
        intents = entry.setdefault("useful_intents", [])
        if intent not in intents:
            intents.append(intent)
    _write_skill_history(data)
    return entry


def note_conflict(skill: str, note: str, *, ts: Optional[float] = None) -> Dict:
    data = read_skill_history()
    entry = _history_entry(data, skill, ts=ts)
    notes = entry.setdefault("conflict_notes", [])
    if note and note not in notes:
        notes.append(note)
    _write_skill_history(data)
    return entry


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
    data = read_skill_history()
    hist = _history_entry(data, skill, ts=entry["ts"])
    hist["state"] = to_state
    if path:
        hist["path"] = str(path)
    states = hist.setdefault("states", {})
    states[to_state] = states.get(to_state, 0) + 1
    if to_state == "demoted":
        hist["demoted_count"] = int(hist.get("demoted_count") or 0) + 1
    elif to_state == "hidden":
        hist["hidden_count"] = int(hist.get("hidden_count") or 0) + 1
    elif to_state == "archived":
        hist["archive_count"] = int(hist.get("archive_count") or 0) + 1
    _write_skill_history(data)
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
    when = ts if ts is not None else time.time()
    entry = {"ts": when, "skill": skill}
    with _usage_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    data = read_skill_history()
    hist = _history_entry(data, skill, ts=when)
    hist["last_used"] = when
    hist["usage_count"] = int(hist.get("usage_count") or 0) + 1
    _write_skill_history(data)


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


# --- Capability gaps -----------------------------------------------------

def record_gap(text: str, *, context: str = "", ts: Optional[float] = None) -> Dict:
    """Record a capability gap: a need with no matching skill.

    The authoring arm clusters these; a recurring gap is what triggers a
    proposal to draft a new skill.
    """
    entry = {
        "ts": ts if ts is not None else time.time(),
        "text": text,
        "context": context,
    }
    with _gaps_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read_gaps() -> List[Dict]:
    p = _gaps_path()
    if not p.exists():
        return []
    out: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --- Probation overlay ---------------------------------------------------
# Probation is Quartermaster's own concept, not a Claude Code primitive, so it
# lives here as an overlay rather than polluting skill files with non-standard
# frontmatter keys. A probationary skill is still `active`; this just tracks
# that it is on trial.

def read_probation() -> Dict[str, Dict]:
    p = _probation_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_probation(data: Dict[str, Dict]) -> None:
    _probation_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def set_probation(skill: str, *, brief: str = "", ts: Optional[float] = None) -> None:
    data = read_probation()
    data[skill] = {
        "admitted": ts if ts is not None else time.time(),
        "brief": brief,
    }
    _write_probation(data)


def clear_probation(skill: str) -> bool:
    data = read_probation()
    if skill in data:
        del data[skill]
        _write_probation(data)
        return True
    return False


# --- Style file (the "constitution") -------------------------------------
# Style feedback is appended to an always-on rules file rather than a skill.
# Default lives under the project so it can be @-included or referenced from
# CLAUDE.md; override with QM_STYLE_FILE.

_STYLE_HEADER = "## Quartermaster style notes\n"


def style_file() -> Path:
    env = os.environ.get("QM_STYLE_FILE")
    if env:
        return Path(env).expanduser()
    return Path(".claude") / "quartermaster-style.md"


def append_style(note: str, *, ts: Optional[float] = None) -> Path:
    """Append a style note to the managed style file. Returns its path."""
    path = style_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d", time.localtime(ts if ts is not None else time.time()))
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if existing.startswith(_STYLE_HEADER) or _STYLE_HEADER in existing else _STYLE_HEADER
    lead = "" if (not existing or existing.endswith("\n")) else "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{lead}{prefix}- ({stamp}) {note.strip()}\n")
    return path


def read_style() -> str:
    path = style_file()
    return path.read_text(encoding="utf-8") if path.exists() else ""
