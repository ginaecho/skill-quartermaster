"""Archived-but-restorable skill storage."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

from . import store
from .registry import ARCHIVED, Skill


def archive_root() -> Path:
    path = store.home() / "archive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path() -> Path:
    return archive_root() / "index.json"


def read_index() -> Dict[str, Dict]:
    path = index_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_index(data: Dict[str, Dict]) -> None:
    index_path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def checksum_dir(path: Path) -> str:
    h = hashlib.sha256()
    for file in sorted(Path(path).rglob("*")):
        if file.is_file():
            rel = file.relative_to(path).as_posix().encode("utf-8")
            h.update(rel)
            h.update(b"\0")
            h.update(file.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def archive_skill(skill: Skill, *, reason: str = "manual archive") -> Dict:
    ts = int(time.time())
    destination = archive_root() / skill.name / str(ts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)

    original = skill.dir
    before = checksum_dir(original)
    shutil.move(str(original), str(destination))
    after = checksum_dir(destination)
    if before != after:
        raise RuntimeError(f"archive checksum mismatch for {skill.name}")

    data = read_index()
    entry = {
        "name": skill.name,
        "original_path": str(original),
        "archive_path": str(destination),
        "checksum": after,
        "archived_at": time.time(),
        "runtime": skill.runtime,
        "reason": reason,
    }
    data[skill.name] = entry
    write_index(data)
    store.record_transition(
        skill.name, skill.state, ARCHIVED, path=destination, actor="qm", reason=reason
    )
    hist = store.read_skill_history()
    if skill.name in hist:
        hist[skill.name]["archive_path"] = str(destination)
        store._write_skill_history(hist)
    return entry


def restore_skill(name: str, *, target_root: Optional[Path] = None) -> Optional[Path]:
    data = read_index()
    entry = data.get(name)
    if not entry:
        return None
    source = Path(entry.get("archive_path", ""))
    if not source.exists():
        return None
    target = Path(entry.get("original_path", ""))
    if target_root is not None:
        target = Path(target_root) / name
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    before = checksum_dir(source)
    shutil.move(str(source), str(target))
    after = checksum_dir(target)
    if before != after or before != entry.get("checksum"):
        raise RuntimeError(f"restore checksum mismatch for {name}")

    del data[name]
    write_index(data)
    store.record_transition(name, ARCHIVED, "active", path=target / "SKILL.md", actor="qm", reason="restore from archive")
    hist = store.read_skill_history()
    if name in hist:
        hist[name]["archive_path"] = ""
        store._write_skill_history(hist)
    return target / "SKILL.md"


def delete_archived(name: str) -> bool:
    data = read_index()
    entry = data.get(name)
    if not entry:
        return False
    path = Path(entry.get("archive_path", ""))
    if path.exists():
        shutil.rmtree(path)
    del data[name]
    write_index(data)
    store.record_transition(name, ARCHIVED, "deleted", path=path, actor="qm", reason="human-approved archived delete")
    return True
