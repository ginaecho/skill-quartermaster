# Benchmark

Numeric evidence that Quartermaster works, run against a **real** corpus of
open-source skills (not synthetic fixtures).

## Corpus

The benchmark needs a directory of `<skill-name>/SKILL.md` folders. The headline
run uses **851 unique real skills** consolidated (deduped by `name`) from public
repositories:

| Source | Skills | Notes |
|---|---|---|
| [`davila7/claude-code-templates`](https://github.com/davila7/claude-code-templates) | ~840 | the large community "skills hub" |
| [`anthropics/skills`](https://github.com/anthropics/skills) | 17 | official Anthropic skills (rich, multi-line descriptions) |
| [`obra/superpowers`](https://github.com/obra/superpowers) | 14 | community workflow skills |
| [`cexll/myclaude`](https://github.com/cexll/myclaude) | 11 | community skills |

These are real `SKILL.md` files with real `name`/`description` frontmatter (and,
for a handful, real `allowed-tools`/`user-invocable` fields) — so the run also
stresses frontmatter parsing and round-trip safety on production data.

## Build the corpus

```bash
# clone the sources
git clone --depth 1 https://github.com/davila7/claude-code-templates /tmp/c8
git clone --depth 1 https://github.com/anthropics/skills              /tmp/corpus
git clone --depth 1 https://github.com/obra/superpowers               /tmp/c2
git clone --depth 1 https://github.com/cexll/myclaude                 /tmp/c6

# flatten + dedupe by skill name into <name>/SKILL.md folders
python3 benchmark/build_corpus.py /tmp/c8 /tmp/corpus /tmp/c2 /tmp/c6 --out /tmp/skillhub
```

## Run

```bash
python3 benchmark/run_benchmark.py /tmp/skillhub --out BENCHMARK.md
```

The corpus is copied to a temp dir (source never modified) and all Quartermaster
state goes to a temp `QM_HOME`, so the run is repeatable and side-effect-free.
Results land in [`../BENCHMARK.md`](../BENCHMARK.md).

## What `run_benchmark.py` measures

1. **Discovery & state derivation** — skills found and states read from real frontmatter.
2. **Standing context cost** — indexed tokens with the whole hub active (~4 chars/token heuristic).
3. **Compiled loadout + savings** — compile to a project intent, hide the rest, report the token-saved headline.
4. **Policy engine** — two cycles on simulated usage: demote-the-stale-tail, then hide-the-long-demoted; fresh skills left alone.
5. **Non-destructive guarantee** — file count before/after (0 deleted) + byte-identical demote→restore round-trips.
6. **Authoring arm** — recurring natural-language gaps cluster into a single authoring proposal.

## Performance experiment — does the loadout keep what the task NEEDS?

Saving tokens is meaningless if the loadout hides the skill the task required.
`quality_experiment.py` measures **capability retention** at the selection layer:

```bash
python3 benchmark/quality_experiment.py /tmp/skillhub /tmp/c8 --out PERFORMANCE.md
```

It reports two metrics, each with an independent control, and writes
[`../PERFORMANCE.md`](../PERFORMANCE.md):

- **M1 — loadout relevance vs. random.** Ground truth = the source repo's own
  category folders (human-authored, independent of our selector); queries =
  hand-written domain sentences (independent of any skill text). Result: the
  30-skill loadout is **~10× more relevant than random** selection of the same
  size (per-domain lift 2.2×–18×).
- **M2 — targeted recall vs. cap.** For a sample of skills, does the specific
  skill survive the cut? At cap=30 (the ~96%-savings point) recall is **100%**
  (named need) / **100%** (described need, name words stripped) vs **3.5%**
  random — and stays ≥97% even cutting to the top 5 of 851.

The report is explicit about **what it proves** (the right skills are present in
the trimmed set) and **what it does not** (a live end-to-end LLM coding eval —
the designed next step), including the upper/lower-bound caveats on each metric.

## A/B eval — real model in the loop (`ab_eval/`)

`quality_experiment.py` proves the *necessary* condition; the A/B harness in
[`ab_eval/`](./ab_eval/) closes the loop with a real model. It measures
**skill-selection accuracy** — full installed set vs. compiled loadout — on
tasks with known correct skills, and reports whether trimming helps, hurts, or is
neutral (the hypothesis: loadout ≥ full). Live run needs `ANTHROPIC_API_KEY`; an
offline simulation validates the pipeline. See [`ab_eval/README.md`](./ab_eval/README.md).

> Token counts are estimates (`len/4`), the standard rough heuristic; they
> measure the *name + description* that progressive disclosure loads up front,
> which is the standing per-session cost a large installed set imposes.
