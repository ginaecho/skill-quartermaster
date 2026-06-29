#!/usr/bin/env python3
"""Evaluate layered Quartermaster behavior on a skill directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qm.evaluation import evaluate  # noqa: E402
from qm.registry import Registry  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run layered Quartermaster evaluation metrics.")
    p.add_argument("skills_dir", help="Directory containing <skill>/SKILL.md folders")
    p.add_argument("--intent", required=True, help="project/task intent")
    p.add_argument("--cap", type=int, default=30)
    p.add_argument("--include-archived", action="store_true")
    args = p.parse_args(argv)

    reg = Registry.load(skills_dir=Path(args.skills_dir), include_archived=args.include_archived)
    result = evaluate(reg, args.intent, cap=args.cap)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
