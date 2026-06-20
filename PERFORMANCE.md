# Quartermaster performance experiment

**Question.** Token savings are easy if you don't care what you drop. The real question is whether the compiled loadout still contains the skills a task *needs*. This experiment measures capability retention at the selection layer.

- Corpus: **851** real skills.  Source categories mapped for **840** of them.
- Selector under test: `qm compile` (v0.3 keyword relevance), cap=30.
- Ground truth for M1: the **source repo's own category folders** (human-authored, independent of our selector).

## M1 — Loadout relevance vs. random (independent ground truth)

For each hand-written domain task we compile a 30-skill loadout and count how many slots fall in the task's target category (per the source repo). We compare to what *random* selection of the same size would yield.

| Task (target category) | category size | base rate | random@30 | **Quartermaster@30** | lift |
|---|--:|--:|--:|--:|--:|
| audit my web application for secur… (security) | 44 | 5.2% | 1.6 | **19** | **12.2×** |
| build a responsive web frontend wi… (web-development) | 30 | 3.5% | 1.1 | **5** | **4.7×** |
| extract text and tables from pdf f… (document-processing) | 12 | 1.4% | 0.4 | **7** | **16.5×** |
| create visual designs, posters, br… (creative-design) | 42 | 4.9% | 1.5 | **5** | **3.4×** |
| design and optimize a relational d… (database) | 11 | 1.3% | 0.4 | **7** | **18.1×** |
| run machine learning experiments, … (ai-research) | 129 | 15.2% | 4.5 | **10** | **2.2×** |

**Mean: 29% of loadout slots on-target, 10× more relevant than random selection of the same size.**

Interpretation: the loadout is dominated by the skills the source repo filed under the task's domain — so the cut to 30 keeps relevant skills and discards the off-topic majority, rather than dropping capability at random.

## M2 — Targeted recall: do *specifically needed* skills survive the cut?

For a random sample of skills we build the query a user would type when they need that skill — its **name** (humanized; short, not the description) — and check whether the skill stays in the top-`cap` loadout among all 851 competitors. Recall = fraction retained. Random baseline = cap/N.

| cap | recall (named need) | recall (described need) | random baseline | token savings @cap* |
|--:|--:|--:|--:|--:|
| 5 | **97%** | **100%** | 0.6% | ~99% |
| 10 | **99%** | **100%** | 1.2% | ~99% |
| 20 | **99%** | **100%** | 2.4% | ~98% |
| 30 | **100%** | **100%** | 3.5% | ~96% |
| 50 | **100%** | **100%** | 5.9% | ~94% |
| 100 | **100%** | **100%** | 11.8% | ~88% |

_Sample: 300 skills (named-need), 297 with a usable description (described-need), seed=7._
- **named need** = user types the skill's name ('I need the X skill').
- **described need** = user describes the task in their own words; the skill's own name words are stripped from the query, so it cannot match on the name — only on overlapping task vocabulary.
* token-savings column assumes a loadout of `cap` active skills out of 851; it lines up with the §3 benchmark headline (~96% at cap=30).

**At cap=30 — the ~96% token-savings operating point — recall is 100% for a named need and 100% for a described need, vs. 3.5% for random.** Shrinking the active set saves the tokens *without* losing the skills a task needs.

## What this proves

- The compiled loadout **concentrates task-relevant skills** (10× over random, 29% on-target) using ground-truth labels and queries that are independent of the selector.
- Specifically-needed skills are **retained at high rate** when the active set is cut to the ~30 sweet spot (100% recall), so the token savings do not drop the capability a task requires.
- Combined with the cited selection-cliff literature (tool-selection accuracy degrades past ~30–100 options), removing the off-topic majority is expected to *help*, not hurt, the model's ability to pick the right skill.

## What this does NOT prove (and how to close it)

- It does **not** measure end-to-end coding quality with a live model. That requires an A/B eval: same tasks, **full skill set vs. compiled loadout**, graded by task success (e.g. SWE-bench-style pass@1 or a tool-selection-accuracy benchmark) with a human or LLM judge.
- A runnable **skill-selection A/B harness** that does exactly this — real model in the loop, full set vs. loadout, gold-hit accuracy — is in `benchmark/ab_eval/` (set `ANTHROPIC_API_KEY` for the live run). It closes the selection half; full task-*execution* grading (pass@1) needs an execution sandbox and is the next rung.
- M2's *described-need* query is derived from each skill's own description (with name words removed), so it shares vocabulary with the target. It tests that a task description surfaces its skill, but real user phrasing overlaps less — so treat M2 recall as an **upper bound** for keyword matching. The selector is v0.3 keyword matching; a semantic-embedding compiler would close the gap for genuine paraphrases.
- M1's category precision is a **lower bound** on relevance: a real task (e.g. a web app) legitimately pulls skills from several categories (web-development *and* security *and* database), which count against a single-category precision but are still relevant.

---
_Reproduce_: `python3 benchmark/quality_experiment.py <corpus> <source_repo>`
