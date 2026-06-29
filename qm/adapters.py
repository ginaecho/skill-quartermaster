"""Runtime adapters for agent-specific skill layout and state semantics.

Quartermaster's core policy should not care whether skills are being exposed to
Claude Code, Codex, Copilot CLI, VS Code, or a generic command-line agent. This
module keeps the runtime-specific filesystem roots and activation flags behind
a small adapter interface.
"""

from __future__ import annotations

import os
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import frontmatter

ACTIVE = "active"
DEMOTED = "demoted"
HIDDEN = "hidden"


class AdapterError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeAdapter:
    name: str
    description: str
    default_roots: Tuple[Path, ...]

    def roots(self) -> List[Path]:
        return [p.expanduser() for p in self.default_roots]

    def derive_state(self, fm: frontmatter.Frontmatter) -> str:
        raise NotImplementedError

    def write_state(self, fm: frontmatter.Frontmatter, target: str) -> None:
        raise NotImplementedError

    def expose_loadout(self, plan, *, intent: str = "", project: str = "default") -> Optional[Path]:
        """Expose a compiled loadout to the runtime, if supported.

        Phase 3 writes a runtime-neutral manifest. Native adapters can later
        override this to emit agent-specific files.
        """
        from . import store

        safe_project = re.sub(r"[^a-zA-Z0-9_.-]+", "-", project).strip("-") or "default"
        out_dir = store.home() / "loadouts"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{safe_project}-{self.name}.json"
        data = {
            "runtime": self.name,
            "intent": intent,
            "cap": plan.cap,
            "generated_at": time.time(),
            "keep": [
                {
                    "name": s.skill.name,
                    "layer": s.layer,
                    "score": s.score,
                    "priority": s.priority,
                    "matched": s.matched,
                    "reasons": s.reasons,
                    "path": str(s.skill.path),
                }
                for s in plan.keep
            ],
            "drop": [
                {
                    "name": s.skill.name,
                    "layer": s.layer,
                    "score": s.score,
                    "priority": s.priority,
                    "path": str(s.skill.path),
                }
                for s in plan.drop
            ],
            "blocked": list(plan.blocked),
        }
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def record_usage_event(self, *_args, **_kwargs) -> None:
        """Record a runtime-specific usage event, if supported."""
        return None

    def setup(self, *, root: Optional[Path] = None) -> List[Path]:
        root = Path(root or ".")
        paths = self._setup_paths(root)
        written: List[Path] = []
        for path, text in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(path)
        for skill_root in self.default_roots[:1]:
            path = root / skill_root
            path.mkdir(parents=True, exist_ok=True)
            written.append(path)
        return written

    def _setup_paths(self, root: Path) -> List[Tuple[Path, str]]:
        return [
            (
                root / ".quartermaster" / f"{self.name}-runtime.md",
                _runtime_instructions(self),
            ),
            (
                root / ".quartermaster" / f"{self.name}-runtime.json",
                json.dumps(_runtime_manifest(self), indent=2, sort_keys=True) + "\n",
            ),
        ]


@dataclass(frozen=True)
class ClaudeAdapter(RuntimeAdapter):
    def derive_state(self, fm: frontmatter.Frontmatter) -> str:
        disabled = fm.get_bool("disable-model-invocation", False)
        user_invocable = fm.get_bool("user-invocable", True)
        if disabled and not user_invocable:
            return HIDDEN
        if disabled:
            return DEMOTED
        return ACTIVE

    def write_state(self, fm: frontmatter.Frontmatter, target: str) -> None:
        if target == ACTIVE:
            fm.remove("disable-model-invocation")
            fm.remove("user-invocable")
        elif target == DEMOTED:
            fm.set("disable-model-invocation", "true")
            fm.remove("user-invocable")
        elif target == HIDDEN:
            fm.set("disable-model-invocation", "true")
            fm.set("user-invocable", "false")
        else:
            raise AdapterError(f"unknown target state: {target!r}")

    def _setup_paths(self, root: Path) -> List[Tuple[Path, str]]:
        return [
            (root / ".claude" / "quartermaster.md", _runtime_instructions(self)),
            (
                root / ".quartermaster" / "claude-runtime.json",
                json.dumps(_runtime_manifest(self), indent=2, sort_keys=True) + "\n",
            ),
        ]


@dataclass(frozen=True)
class ManifestAdapter(RuntimeAdapter):
    """Generic adapter for runtimes without Claude frontmatter semantics.

    It uses a Quartermaster-owned `qm-state` frontmatter key when it must persist
    state. If that key is absent, it falls back to Claude-compatible flags so a
    directory can be inspected across adapters without losing information.
    """

    def derive_state(self, fm: frontmatter.Frontmatter) -> str:
        raw = (fm.get("qm-state") or "").strip().lower()
        if raw in (ACTIVE, DEMOTED, HIDDEN):
            return raw
        return CLAUDE.derive_state(fm)

    def write_state(self, fm: frontmatter.Frontmatter, target: str) -> None:
        if target not in (ACTIVE, DEMOTED, HIDDEN):
            raise AdapterError(f"unknown target state: {target!r}")
        fm.set("qm-state", target)


@dataclass(frozen=True)
class CodexAdapter(ManifestAdapter):
    def _setup_paths(self, root: Path) -> List[Tuple[Path, str]]:
        return [
            (root / ".codex" / "quartermaster.md", _runtime_instructions(self)),
            (
                root / ".quartermaster" / "codex-runtime.json",
                json.dumps(_runtime_manifest(self), indent=2, sort_keys=True) + "\n",
            ),
        ]


@dataclass(frozen=True)
class CopilotAdapter(ManifestAdapter):
    def _setup_paths(self, root: Path) -> List[Tuple[Path, str]]:
        return [
            (root / ".github" / "copilot" / "quartermaster.md", _runtime_instructions(self)),
            (
                root / ".quartermaster" / "copilot-runtime.json",
                json.dumps(_runtime_manifest(self), indent=2, sort_keys=True) + "\n",
            ),
        ]


@dataclass(frozen=True)
class VSCodeAdapter(ManifestAdapter):
    def _setup_paths(self, root: Path) -> List[Tuple[Path, str]]:
        return [
            (root / ".vscode" / "quartermaster.instructions.md", _runtime_instructions(self)),
            (
                root / ".vscode" / "quartermaster.runtime.json",
                json.dumps(_runtime_manifest(self), indent=2, sort_keys=True) + "\n",
            ),
        ]


CLAUDE = ClaudeAdapter(
    name="claude",
    description="Claude Code skills, plugin commands, and frontmatter flags.",
    default_roots=(Path(".claude/skills"), Path.home() / ".claude" / "skills"),
)

GENERIC = ManifestAdapter(
    name="generic",
    description="Runtime-neutral skill folders using Quartermaster manifests.",
    default_roots=(Path(".quartermaster/skills"), Path.home() / ".quartermaster" / "skills"),
)

CODEX = CodexAdapter(
    name="codex",
    description="Codex-compatible exported loadouts and local skill folders.",
    default_roots=(Path(".codex/skills"), Path.home() / ".codex" / "skills"),
)

COPILOT = CopilotAdapter(
    name="copilot",
    description="GitHub Copilot CLI loadout manifests and command wrappers.",
    default_roots=(Path(".github/copilot/skills"), Path.home() / ".quartermaster" / "copilot" / "skills"),
)

VSCODE = VSCodeAdapter(
    name="vscode",
    description="VS Code workspace-local instructions and skill manifests.",
    default_roots=(Path(".vscode/quartermaster/skills"), Path.home() / ".quartermaster" / "vscode" / "skills"),
)

_ADAPTERS: Dict[str, RuntimeAdapter] = {
    a.name: a for a in (CLAUDE, CODEX, COPILOT, VSCODE, GENERIC)
}


def names() -> List[str]:
    return sorted(_ADAPTERS)


def all_adapters() -> List[RuntimeAdapter]:
    return [_ADAPTERS[name] for name in names()]


def get(name: Optional[str] = None) -> RuntimeAdapter:
    selected = (name or os.environ.get("QM_RUNTIME") or CLAUDE.name).strip().lower()
    try:
        return _ADAPTERS[selected]
    except KeyError as exc:
        valid = ", ".join(names())
        raise AdapterError(f"unknown runtime {selected!r}; expected one of: {valid}") from exc


def resolve_roots(
    *,
    adapter: RuntimeAdapter,
    skills_dir: Optional[os.PathLike] = None,
) -> List[Path]:
    if skills_dir is not None:
        return [Path(skills_dir)]
    env = os.environ.get("QM_SKILLS_DIR")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p]
    return adapter.roots()


def _runtime_manifest(adapter: RuntimeAdapter) -> Dict:
    return {
        "runtime": adapter.name,
        "description": adapter.description,
        "skill_roots": [str(p) for p in adapter.default_roots],
        "commands": {
            "status": f"qm --runtime {adapter.name} status --layers --all",
            "compile": f"qm --runtime {adapter.name} compile \"<intent>\" --dry-run",
            "review": f"qm --runtime {adapter.name} review --dry-run",
            "restore": f"qm --runtime {adapter.name} restore <skill>",
        },
        "loadout_manifest_dir": "$QM_HOME/loadouts",
    }


def _runtime_instructions(adapter: RuntimeAdapter) -> str:
    return f"""# Quartermaster Runtime Setup: {adapter.name}

Quartermaster manages the active skill loadout for this runtime.

Use these commands from the repository root:

```bash
qm --runtime {adapter.name} status --layers --all
qm --runtime {adapter.name} compile "<project intent>" --dry-run
qm --runtime {adapter.name} review --dry-run
qm --runtime {adapter.name} restore <skill>
```

Applied compile plans write loadout manifests under `$QM_HOME/loadouts/`.
Do not delete skills directly. Use `qm archive <skill>` for reversible removal
and `qm delete <skill> --yes` only after explicit human approval.
"""
