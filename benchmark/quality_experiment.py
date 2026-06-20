#!/usr/bin/env python3
"""Performance experiment: does the compiled loadout keep the skills a task NEEDS?

Saving tokens is worthless if Quartermaster hides the skill the task required.
This experiment measures *capability retention* — directly, at the selection
layer — so the token savings can be trusted not to come at the cost of dropping
relevant skills.

It does NOT run a live LLM coding eval (see "What this does NOT prove" in the
generated report). It measures the thing Quartermaster actually controls: which
skills end up in the active set.

Two metrics, each with an independent control:

  M1. Loadout relevance (precision & lift over random)
      - ground truth : the SOURCE REPO's own category folders (human-authored,
                       independent of our selector)
      - query        : a domain sentence written by hand (independent of any
                       skill's text — no leakage from the corpus)
      - measure      : of the 30 loadout slots, how many belong to the target
                       category, vs. what random selection would yield.

  M2. Targeted recall vs. cap (the performance/context trade-off curve)
      - for a random sample of skills, build the query a user would type when
        they need that skill (its name, humanized — short, not the description)
      - measure the fraction whose skill survives in the top-`cap` loadout, for
        a range of caps. Random baseline = cap / N.

Usage:
  python3 benchmark/quality_experiment.py <corpus_dir> <source_repo_dir> [--out PERFORMANCE.md]
"""

from __future__ import annotations

import argparse
import glob
import os
import random
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def category_map(src: str) -> dict:
    """skill-name -> author-assigned category, from `.../skills/<cat>/<name>/SKILL.md`."""
    out = {}
    for f in glob.glob(f"{src}/**/SKILL.md", recursive=True):
        if "/.git/" in f or "/template/" in f:
            continue
        parts = Path(f).parts
        if "skills" in parts:
            i = parts.index("skills")
            if i + 2 < len(parts):
                cat = parts[i + 1]
                name = parts[i + 2]
                out[name] = cat
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^name:\s*(.+)$", text.split("---", 2)[1], re.M) if text.startswith("---") else None
        if m and i + 2 < len(parts):
            out[m.group(1).strip()] = cat
    return out


# Hand-written domain tasks (our words) -> target author category.
TASKS = [
    ("security",
     "audit my web application for security vulnerabilities, harden authentication, "
     "scan dependencies for CVEs and review code for injection flaws"),
    ("web-development",
     "build a responsive web frontend with a modern javascript framework, reusable "
     "components, routing and css styling"),
    ("document-processing",
     "extract text and tables from pdf files and generate formatted word documents "
     "and excel spreadsheets"),
    ("creative-design",
     "create visual designs, posters, brand artwork and illustrations"),
    ("database",
     "design and optimize a relational database schema with migrations, indexes and "
     "query performance tuning"),
    ("ai-research",
     "run machine learning experiments, train and evaluate models and analyze "
     "research papers and datasets"),
]


def humanize(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("source")
    ap.add_argument("--out", default="PERFORMANCE.md")
    ap.add_argument("--cap", type=int, default=30)
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    os.environ.setdefault("QM_HOME", tempfile.mkdtemp(prefix="qm_perf_"))
    from qm.compile import score_skills
    from qm.registry import Registry

    reg = Registry.load(skills_dir=args.corpus)
    catmap = category_map(args.source)
    N = len(reg)
    rng = random.Random(args.seed)

    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out("# Quartermaster performance experiment")
    out("")
    out("**Question.** Token savings are easy if you don't care what you drop. "
        "The real question is whether the compiled loadout still contains the "
        "skills a task *needs*. This experiment measures capability retention at "
        "the selection layer.")
    out("")
    out(f"- Corpus: **{N}** real skills.  Source categories mapped for "
        f"**{sum(1 for s in reg if s.name in catmap)}** of them.")
    out(f"- Selector under test: `qm compile` (v0.3 keyword relevance), cap={args.cap}.")
    out(f"- Ground truth for M1: the **source repo's own category folders** "
        f"(human-authored, independent of our selector).")
    out("")

    # ---- M1: loadout relevance (precision & lift over random) ----
    out("## M1 — Loadout relevance vs. random (independent ground truth)")
    out("")
    out("For each hand-written domain task we compile a 30-skill loadout and count "
        "how many slots fall in the task's target category (per the source repo). "
        "We compare to what *random* selection of the same size would yield.")
    out("")
    out("| Task (target category) | category size | base rate | random@30 | "
        "**Quartermaster@30** | lift |")
    out("|---|--:|--:|--:|--:|--:|")
    lifts = []
    precisions = []
    for cat, intent in TASKS:
        scored = score_skills(reg, intent)
        topk = [s.skill.name for s in scored[: args.cap]]
        cat_size = sum(1 for s in reg if catmap.get(s.name) == cat)
        if cat_size == 0:
            continue
        base = cat_size / N
        rand_expected = args.cap * base
        qm_hits = sum(1 for n in topk if catmap.get(n) == cat)
        lift = (qm_hits / rand_expected) if rand_expected > 0 else float("inf")
        lifts.append(lift)
        precisions.append(qm_hits / args.cap)
        out(f"| {intent[:34]}… ({cat}) | {cat_size} | {base*100:.1f}% | "
            f"{rand_expected:.1f} | **{qm_hits}** | **{lift:.1f}×** |")
    out("")
    mean_lift = sum(lifts) / len(lifts)
    mean_prec = sum(precisions) / len(precisions)
    out(f"**Mean: {mean_prec*100:.0f}% of loadout slots on-target, "
        f"{mean_lift:.0f}× more relevant than random selection of the same size.**")
    out("")
    out("Interpretation: the loadout is dominated by the skills the source repo "
        "filed under the task's domain — so the cut to 30 keeps relevant skills "
        "and discards the off-topic majority, rather than dropping capability "
        "at random.")

    # ---- M2: targeted recall vs cap ----
    out("")
    out("## M2 — Targeted recall: do *specifically needed* skills survive the cut?")
    out("")
    out("For a random sample of skills we build the query a user would type when "
        "they need that skill — its **name** (humanized; short, not the "
        "description) — and check whether the skill stays in the top-`cap` "
        "loadout among all "
        f"{N} competitors. Recall = fraction retained. Random baseline = cap/N.")
    out("")
    names = [s.name for s in reg]
    sample = rng.sample(names, min(args.sample, len(names)))
    by_name = {s.name: s for s in reg}

    from qm.compile import _tokens as toks

    def described_need(skill) -> str:
        """A task described in the user's words: salient description tokens with
        the skill's own NAME words removed, so the query never echoes the name."""
        name_words = set(toks(skill.name))
        desc_words = [w for w in toks(skill.description) if w not in name_words]
        # keep order, de-dup, cap length to mimic a short user description
        seen = []
        for w in desc_words:
            if w not in seen:
                seen.append(w)
        return " ".join(seen[:14])

    caps = [5, 10, 20, 30, 50, 100]
    hits_name = {k: 0 for k in caps}
    hits_desc = {k: 0 for k in caps}
    desc_evaluated = 0
    for nm in sample:
        # named-need query
        order = [s.skill.name for s in score_skills(reg, humanize(nm))]
        rank = order.index(nm) if nm in order else len(order)
        for k in caps:
            if rank < k:
                hits_name[k] += 1
        # described-need query (name words stripped)
        q = described_need(by_name[nm])
        if not q.strip():
            continue
        desc_evaluated += 1
        order2 = [s.skill.name for s in score_skills(reg, q)]
        rank2 = order2.index(nm) if nm in order2 else len(order2)
        for k in caps:
            if rank2 < k:
                hits_desc[k] += 1

    out("| cap | recall (named need) | recall (described need) | random baseline | token savings @cap* |")
    out("|--:|--:|--:|--:|--:|")
    for k in caps:
        rn = hits_name[k] / len(sample)
        rd = hits_desc[k] / max(1, desc_evaluated)
        rand = k / N
        savings = 100.0 * (1 - k / N)
        out(f"| {k} | **{rn*100:.0f}%** | **{rd*100:.0f}%** | {rand*100:.1f}% | ~{savings:.0f}% |")
    out("")
    out(f"_Sample: {len(sample)} skills (named-need), "
        f"{desc_evaluated} with a usable description (described-need), seed={args.seed}._")
    out("- **named need** = user types the skill's name ('I need the X skill').")
    out("- **described need** = user describes the task in their own words; the "
        "skill's own name words are stripped from the query, so it cannot match "
        "on the name — only on overlapping task vocabulary.")
    out(f"* token-savings column assumes a loadout of `cap` active skills out of "
        f"{N}; it lines up with the §3 benchmark headline (~96% at cap=30).")
    out("")
    r30 = hits_name[30] / len(sample)
    r30d = hits_desc[30] / max(1, desc_evaluated)
    out(f"**At cap=30 — the ~96% token-savings operating point — recall is "
        f"{r30*100:.0f}% for a named need and {r30d*100:.0f}% for a described "
        f"need, vs. {30/N*100:.1f}% for random.** Shrinking the active set saves "
        f"the tokens *without* losing the skills a task needs.")

    # ---- framing ----
    out("")
    out("## What this proves")
    out("")
    out("- The compiled loadout **concentrates task-relevant skills** "
        f"({mean_lift:.0f}× over random, {mean_prec*100:.0f}% on-target) using "
        "ground-truth labels and queries that are independent of the selector.")
    out("- Specifically-needed skills are **retained at high rate** when the active "
        f"set is cut to the ~30 sweet spot ({r30*100:.0f}% recall), so the token "
        "savings do not drop the capability a task requires.")
    out("- Combined with the cited selection-cliff literature (tool-selection "
        "accuracy degrades past ~30–100 options), removing the off-topic majority "
        "is expected to *help*, not hurt, the model's ability to pick the right "
        "skill.")
    out("")
    out("## What this does NOT prove (and how to close it)")
    out("")
    out("- It does **not** measure end-to-end coding quality with a live model. "
        "That requires an A/B eval: same tasks, **full skill set vs. compiled "
        "loadout**, graded by task success (e.g. SWE-bench-style pass@1 or a "
        "tool-selection-accuracy benchmark) with a human or LLM judge.")
    out("- Such an eval needs many model calls and graded outcomes, so it is not "
        "reproducible inside this offline harness. The design above is the "
        "intended next step; this experiment validates the *necessary* condition "
        "(the right skills are present) that any such eval depends on.")
    out("- M2's *described-need* query is derived from each skill's own "
        "description (with name words removed), so it shares vocabulary with the "
        "target. It tests that a task description surfaces its skill, but real "
        "user phrasing overlaps less — so treat M2 recall as an **upper bound** "
        "for keyword matching. The selector is v0.3 keyword matching; a "
        "semantic-embedding compiler would close the gap for genuine paraphrases.")
    out("- M1's category precision is a **lower bound** on relevance: a real task "
        "(e.g. a web app) legitimately pulls skills from several categories "
        "(web-development *and* security *and* database), which count against a "
        "single-category precision but are still relevant.")
    out("")
    out("---")
    out("_Reproduce_: `python3 benchmark/quality_experiment.py <corpus> <source_repo>`")

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[wrote {args.out}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
