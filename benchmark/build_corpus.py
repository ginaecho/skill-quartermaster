#!/usr/bin/env python3
"""Flatten one or more skill repos into a deduped <name>/SKILL.md corpus.

Each source is searched recursively for `SKILL.md` files (skipping `.git` and
`template/` dirs). Skills are keyed by their frontmatter `name` and the first
occurrence wins, so earlier sources take priority on a name clash.

Usage:
  python3 benchmark/build_corpus.py SRC [SRC ...] --out /tmp/skillhub
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
from pathlib import Path


def _name(text: str):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 2:
            m = re.search(r"^name:\s*(.+)$", parts[1], re.M)
            if m:
                return m.group(1).strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    seen = set()
    copied = dup = noname = 0
    for src in args.sources:
        for f in sorted(glob.glob(f"{src}/**/SKILL.md", recursive=True)):
            if "/.git/" in f or "/template/" in f:
                continue
            text = Path(f).read_text(encoding="utf-8", errors="ignore")
            name = _name(text)
            if not name:
                noname += 1
                continue
            slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name)[:60]
            if slug in seen:
                dup += 1
                continue
            seen.add(slug)
            (out / slug).mkdir()
            shutil.copy(f, out / slug / "SKILL.md")
            copied += 1

    print(f"copied={copied} duplicates_skipped={dup} no_name_skipped={noname}")
    print(f"corpus at {out} ({copied} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
