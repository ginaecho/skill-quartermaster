#!/usr/bin/env python3
"""A/B eval: does the model pick the RIGHT skill from the full set vs. the loadout?

This is the end-to-end test that `PERFORMANCE.md` flags as the missing piece. It
puts a real model in the loop and measures *skill-selection accuracy* — the
mechanism by which an installed skill set actually affects agent behavior.

For each eval task (a user request whose correct skill is known), the model is
asked to pick the single best skill from a menu, under two conditions:

  A) FULL    — the entire installed skill set (the status quo: hundreds of skills)
  B) LOADOUT — only Quartermaster's compiled loadout for that task (~30 skills)

We compare gold-hit accuracy A vs B. This captures BOTH effects at once:
  * recall   — is the right skill even present in the loadout? (a hidden skill
               can't be picked) — the risk Quartermaster must not regress
  * precision of selection — given the menu, does the model find the right skill?
               (the selection-cliff effect: accuracy degrades with menu size)

Because both conditions share the same task wording and gold labels, any
vocabulary overlap between task and skill is a *shared confound that cancels in
the A−B comparison* — the relative result is valid even if absolute accuracy is
inflated. That is the methodological point of an A/B.

Live run (real evidence) needs the Anthropic SDK + an API key:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 benchmark/ab_eval/run_ab_eval.py <corpus> <source_repo> --n 60

Without those, it runs an OFFLINE SIMULATION (a keyword-selector stand-in for the
model) so the pipeline is verifiable and the methodology is inspectable. Offline
numbers are labeled as such and are NOT the agent-performance evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

MODEL = "claude-opus-4-8"

PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "string", "description": "exact name of the single best skill, or NONE"},
    },
    "required": ["skill"],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = (
    "You are the skill-selection layer of a coding agent. Given a user task and a "
    "menu of available skills (name: description), choose the SINGLE skill whose "
    "instructions would best help accomplish the task. Reply with that skill's "
    "exact name. If truly none apply, reply NONE. Choose exactly one."
)


def _name_words(name: str):
    return set(re.findall(r"[a-z0-9]+", name.lower()))


@dataclass
class Task:
    gold: str
    query: str
    category: str


def build_tasks(reg, catmap, n, seed):
    """Build eval tasks: a user request derived from a gold skill's description
    with the skill's own name words removed (so the query never names the skill)."""
    from qm.compile import _tokens

    rng = random.Random(seed)
    candidates = [s for s in reg if s.description and s.name in catmap]
    rng.shuffle(candidates)
    tasks = []
    for s in candidates:
        nw = _name_words(s.name)
        words = [w for w in _tokens(s.description) if w not in nw]
        # de-dup preserving order, cap to a short user-request length
        seen, q = set(), []
        for w in words:
            if w not in seen:
                seen.add(w)
                q.append(w)
        query = " ".join(q[:18])
        if len(q) < 5:
            continue
        tasks.append(Task(gold=s.name, query=query, category=catmap[s.name]))
        if len(tasks) >= n:
            break
    return tasks


def menu_text(skills):
    return "\n".join(f"{s.name}: {s.description}" for s in skills)


# ---- model backends -----------------------------------------------------

class OfflineStub:
    """Keyword-selector stand-in for the model (NOT real agent evidence)."""

    label = "OFFLINE keyword-selector simulation (no model in the loop)"

    def __init__(self):
        from qm.compile import score_skills
        self._score = score_skills

    def pick(self, menu_skills, query, cached_key=None):
        # Rank the menu by keyword overlap; return the top name.
        from qm.registry import Registry
        ranked = self._score(Registry(list(menu_skills)), query)
        return ranked[0].skill.name if ranked else "NONE"


class ClaudeBackend:
    label = f"LIVE model: {MODEL}"

    def __init__(self):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self._full_menu_cached = None

    def pick(self, menu_skills, query, cached_key=None):
        menu = menu_text(menu_skills)
        # Cache the large, stable FULL menu across tasks; LOADOUT menus vary.
        system = [
            {"type": "text", "text": SYSTEM_INSTRUCTIONS},
            {"type": "text", "text": "AVAILABLE SKILLS:\n" + menu,
             **({"cache_control": {"type": "ephemeral"}} if cached_key == "full" else {})},
        ]
        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": PICK_SCHEMA}},
            messages=[{"role": "user", "content": f"TASK: {query}\n\nPick the single best skill."}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        try:
            return json.loads(text).get("skill", "NONE")
        except json.JSONDecodeError:
            return "NONE"


def get_backend(force_offline):
    if force_offline:
        return OfflineStub()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[no ANTHROPIC_API_KEY — running offline simulation]")
        return OfflineStub()
    try:
        return ClaudeBackend()
    except Exception as e:  # SDK missing or client init failed
        print(f"[anthropic SDK unavailable ({e}) — running offline simulation]")
        return OfflineStub()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("source")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--cap", type=int, default=30)
    ap.add_argument("--full-size", type=int, default=0, help="0 = entire corpus")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default="benchmark/ab_eval/AB_RESULTS.md")
    args = ap.parse_args()

    os.environ.setdefault("QM_HOME", "/tmp/qm_ab_home")
    from qm.compile import compile_loadout, score_skills
    from qm.registry import Registry
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from quality_experiment import category_map  # reuse the gold-label loader

    reg = Registry.load(skills_dir=args.corpus)
    catmap = category_map(args.source)
    by_name = {s.name: s for s in reg}
    full_pool = list(reg) if args.full_size == 0 else list(reg)[: args.full_size]

    backend = get_backend(args.offline)
    tasks = build_tasks(reg, catmap, args.n, args.seed)

    rng = random.Random(args.seed)
    full_menu = list(full_pool)
    rng.shuffle(full_menu)  # fixed order across tasks (cacheable, position-neutral)

    full_hit = loadout_hit = gold_in_loadout = 0
    full_inmenu = loadout_inmenu = 0
    rows = []
    for i, t in enumerate(tasks, 1):
        # FULL condition
        full_pick = backend.pick(full_menu, t.query, cached_key="full")
        fh = (full_pick == t.gold)
        full_hit += fh
        full_inmenu += (full_pick in by_name)

        # LOADOUT condition
        plan = compile_loadout(reg, t.query, cap=args.cap)
        loadout = [by_name[s.skill.name] for s in plan.keep]
        present = any(s.name == t.gold for s in loadout)
        gold_in_loadout += present
        lp = backend.pick(loadout, t.query, cached_key="loadout")
        lh = (lp == t.gold)
        loadout_hit += lh
        loadout_inmenu += (lp in {s.name for s in loadout})

        rows.append((t.gold, t.category, fh, lh, present))
        if i % 10 == 0:
            print(f"  {i}/{len(tasks)} done")

    n = len(tasks)
    fa = full_hit / n
    la = loadout_hit / n
    recall = gold_in_loadout / n
    sel_given_present = (loadout_hit / gold_in_loadout) if gold_in_loadout else 0.0

    L = []
    def out(s=""):
        print(s)
        L.append(s)

    out("# A/B eval — skill selection: full set vs. compiled loadout")
    out("")
    out(f"_Backend_: **{backend.label}**  ")
    out(f"_Tasks_: {n} (seed {args.seed}).  Full menu: {len(full_menu)} skills.  "
        f"Loadout cap: {args.cap}.")
    out("")
    out("Each task is a user request whose correct skill is known (gold). The "
        "model picks one skill from the menu; we score gold-hit accuracy.")
    out("")
    out("| Condition | menu size | gold-hit accuracy |")
    out("|---|--:|--:|")
    out(f"| **A — full installed set** | {len(full_menu)} | **{fa*100:.0f}%** |")
    out(f"| **B — Quartermaster loadout** | ≤{args.cap} | **{la*100:.0f}%** |")
    out(f"| Δ (loadout − full) | | **{(la-fa)*100:+.0f} pts** |")
    out("")
    out("Decomposition of the loadout condition:")
    out("")
    out(f"- Recall — gold skill present in the loadout: **{recall*100:.0f}%** "
        f"(if it's hidden, it can't be picked)")
    out(f"- Selection accuracy given the gold skill is present: "
        f"**{sel_given_present*100:.0f}%**")
    out("")
    if la >= fa:
        out(f"**Result: trimming to the loadout did not hurt selection "
            f"({la*100:.0f}% vs {fa*100:.0f}%)** — the agent finds the right "
            f"skill at least as often with ~{args.cap} skills as with "
            f"{len(full_menu)}, at a fraction of the context cost.")
    else:
        out(f"**Result: loadout accuracy {la*100:.0f}% vs full {fa*100:.0f}% "
            f"({(la-fa)*100:+.0f} pts).** The gap is bounded by recall "
            f"({recall*100:.0f}%): raise the cap or improve the compiler to close it.")
    out("")
    if isinstance(backend, OfflineStub):
        out("> ⚠️ **These are OFFLINE-SIMULATION numbers** (a keyword selector "
            "stands in for the model). They validate the harness and methodology "
            "only. Run with `ANTHROPIC_API_KEY` set for real agent-performance "
            "evidence.")
    out("")
    out("_Reproduce_: `python3 benchmark/ab_eval/run_ab_eval.py <corpus> <source>` "
        "(set ANTHROPIC_API_KEY for the live run).")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n[wrote {args.out}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
