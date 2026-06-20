#!/usr/bin/env python3
"""PreToolUse hook: record which skill fired, local-only.

Claude Code invokes this with a JSON event on stdin before a tool runs. When
the tool is a Skill invocation, we log the skill name to Quartermaster's usage
trail so the policy engine can reason about what's actually used. We never block
the tool and never emit anything to the network — on any error we exit cleanly
so a telemetry hiccup can never get in the user's way.

Wire it up in your plugin/settings hooks config as a PreToolUse matcher on the
Skill tool. It reads the same data Quartermaster's CLI does via QM_HOME.
"""
import json
import os
import sys


def _extract_skill_name(event: dict):
    tool = event.get("tool_name") or event.get("tool") or ""
    if tool not in ("Skill", "skill"):
        return None
    tin = event.get("tool_input") or event.get("input") or {}
    if isinstance(tin, dict):
        return tin.get("skill") or tin.get("name") or tin.get("command")
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    name = _extract_skill_name(event)
    if not name:
        return 0

    try:
        # Import lazily so the hook works whether or not the package is on path.
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        if root not in sys.path:
            sys.path.insert(0, root)
        from qm import store

        store.record_usage(str(name))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
