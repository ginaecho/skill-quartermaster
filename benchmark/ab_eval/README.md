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

## Any model, any provider

Picking the right skill is a plain completion, so the backend is pluggable —
you are **not limited to Anthropic**. Choose a provider with `--provider`:

| `--provider` | Backend | Example |
|---|---|---|
| `anthropic` | official `anthropic` SDK (`claude-opus-4-8`), prompt-caches the FULL menu | `--provider anthropic` |
| `openai` | official `openai` SDK against **any OpenAI-compatible endpoint** | see below |
| `command` | shells out to a **real agent CLI** (Claude Code, Copilot CLI, …) | see below |
| `offline` | keyword-selector simulation (pipeline check only) | `--offline` |

```bash
# Anthropic (default when ANTHROPIC_API_KEY is set)
export ANTHROPIC_API_KEY=sk-ant-...
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --n 60

# OpenAI
export OPENAI_API_KEY=sk-...
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --provider openai --model gpt-4o

# Any OpenAI-compatible provider via --base-url:
#   OpenRouter / Together / Groq / Fireworks / Azure …
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --provider openai \
    --model anthropic/claude-opus-4-8 --base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY

#   …or a LOCAL model (no key needed): Ollama / vLLM / LM Studio
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --provider openai \
    --model llama3.1 --base-url http://localhost:11434/v1

# Drive a real agent CLI (the "subscription agent" path):
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --provider command --command "claude -p"
python3 benchmark/ab_eval/run_ab_eval.py /tmp/skillhub /tmp/c8 --provider command --command "copilot -p"
```

The Anthropic path uses structured outputs (`output_config.format`) and prompt
caching on the large, stable FULL menu so repeat runs are cheap. Other providers
get a plain "reply with the exact skill name" prompt and the reply is mapped onto
a menu name. All providers and SDKs are lazy-imported — you only need the one you
use. Writes `benchmark/ab_eval/AB_RESULTS.md`.

> **`command` vs the real harness.** The `command` backend asks an agent CLI to
> *name* the best skill — it measures that CLI's model under our A/B, which is
> exactly the cross-provider comparison most people want. It does **not** observe
> the harness's *native* skill auto-selection (progressive disclosure). For that
> deepest test, install Quartermaster's loadout, run real tasks through the
> agent, and read which skill actually fired from the **PreToolUse telemetry
> hook** (`hooks/usage_hook.py`) — fully faithful, but harness-specific and not a
> one-shot script.

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

## Where to run it (local vs. cloud)

You don't have to run it on your laptop:

- **Your machine.** `pip install -r requirements.txt`, export the key, run the
  command above.
- **GitHub's cloud (Actions).** A manual-dispatch workflow is included at
  `.github/workflows/ab-eval.yml`. Add `ANTHROPIC_API_KEY` (and/or
  `OPENAI_API_KEY`) under **Settings → Secrets and variables → Actions**, then
  run it from the **Actions** tab (choose provider / model / `n`). It builds the
  corpus, runs the eval, prints the table to the run summary, and uploads
  `AB_RESULTS.md` as an artifact. This is the "GitHub cloud" answer — GitHub
  Copilot itself isn't a general compute target, but Actions is.
- **An Anthropic-hosted Claude Code session.** A Claude Code on the web session
  already runs in Anthropic's managed cloud — set `ANTHROPIC_API_KEY` in the
  environment's config (and allow egress to `api.anthropic.com`) and the agent
  can run the eval there, no laptop involved.

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
