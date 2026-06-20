# A/B eval — does trimming the skill set hurt the agent?

`PERFORMANCE.md` proves the *necessary* condition (the right skills survive the
cut). This harness closes the loop with the *sufficient* test: put a real model
in the loop and measure whether it still selects the correct skill when it sees
only Quartermaster's compiled loadout instead of the full installed set.

## What it measures

**Skill-selection accuracy** — the mechanism by which an installed skill set
actually changes agent behavior. For each task (a user request with a known
correct "gold" skill), the model picks one skill from a menu, under two
conditions:

| Condition | Menu | Represents |
|---|---|---|
| **A — FULL** | the entire installed set (e.g. 851 skills) | the status quo: dump every skill in |
| **B — LOADOUT** | Quartermaster's compiled loadout (~30) | curated per-project |

We report **gold-hit accuracy A vs B**. The loadout condition is decomposed into:

- **recall** — was the gold skill even in the loadout? (a hidden skill can't be picked — the regression risk Quartermaster must avoid)
- **selection accuracy given present** — the selection-cliff effect: does a smaller menu make the right skill easier to find?

### Why the comparison is sound

Tasks are built from each gold skill's own description with the **skill's name
words removed**, so the query never names the answer. Any remaining vocabulary
overlap is a **shared confound that cancels in the A−B difference** — both
conditions see the same task wording and gold labels. That is the whole point of
an A/B: absolute accuracy may be optimistic, but the *relative* result (does
trimming help, hurt, or neither) is valid. The hypothesis Quartermaster needs to
hold is **B ≥ A**: the loadout does not reduce the agent's ability to find the
right skill, while costing a fraction of the context (see `../../BENCHMARK.md`,
~96% fewer tokens).

## Run it

**Live (real evidence) — needs the Anthropic SDK and an API key:**

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --n 60
```

Uses `claude-opus-4-8`, structured outputs (`output_config.format`), and prompt
caching on the large, stable FULL menu so it's cheap to repeat. Writes
`benchmark/ab_eval/AB_RESULTS.md`.

**Cost.** The FULL menu (~851 skills ≈ 60k tokens) is identical across tasks, so
it's cached after the first call (~0.1× reads thereafter); loadout menus are
small. A 60-task run is on the order of a few dollars. Lower `--full-size` or
`--n` to spend less.

**Offline (pipeline check only):**

```bash
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --n 40 --offline
```

Substitutes a keyword selector for the model. This **validates the harness and
methodology**, not agent performance — offline numbers are labeled as such in the
output and should never be cited as evidence. (Build the corpus with
`../build_corpus.py` — see `../README.md`.)

## What this proves / does not prove

- **Proves (live run):** whether the compiled loadout preserves — or improves —
  the model's skill-selection accuracy versus dumping in the full set, with a
  real model in the loop and an A/B that cancels shared confounds.
- **Does not prove:** full task *execution* quality (writing correct code end to
  end). Selection is the lever Quartermaster controls; execution depends on the
  skill contents, which Quartermaster never edits. A SWE-bench-style pass@1
  comparison would be the next rung and needs an execution sandbox + graded
  tasks — out of scope for this repo's offline harness, but the selection result
  here is the precondition any such eval depends on.

## Knobs

`--n` tasks · `--cap` loadout size · `--full-size` cap the FULL menu (0 = all) ·
`--seed` reproducibility · `--offline` force the simulation.
