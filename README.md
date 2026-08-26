<h1 align="center">🎖️ Quartermaster</h1>

<p align="center">
  <strong>A kinder way to choose agent skills.</strong><br>
  Skills are the how-to guides your coding agent loads. Quartermaster keeps only the ones your project needs,<br>
  proves new ones are better with fair side-by-side trials, and leaves every final decision to a human.<br>
  <strong>It never deletes anything without your yes.</strong>
</p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="claude code" src="https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2">
  <a href="https://doi.org/10.5281/zenodo.21009805"><img alt="DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.21009805.svg"></a>
</p>

<p align="center">
  <img src="docs/assets/a-kinder-way.svg" alt="A scout finds promising skills, a fair arena trials them head-to-head, evidence grows in an append-only log, three humans review, and trust is earned: candidate, scouted, verified." width="100%">
</p>

## Why

Skill marketplaces ship hundreds of skills at once. Past a few dozen, your agent starts picking the wrong one — and you become the janitor, with no safe way to clean up. Quartermaster fixes both, built on four rules:

1. **Trust is earned.** New skills start as candidates and advance only by winning trials and passing review. No skill jumps the queue.
2. **Fair trials, not stars.** Candidate vs. your current skill — same task, same seed, pinned versions.
3. **Evidence is append-only.** Pass/fail, latency, cost, notes — recorded, never rewritten.
4. **Humans decide.** The tool proposes; you approve. Everything is audited and reversible.

## Proof it works

On **851 real open-source skills**: loadout trimmed to **30**, **96% of context tokens saved** (~57.5k), **0 files deleted**, demote→restore **byte-identical**. And in a live A/B (`claude-opus-4-8`, 60 tasks), the agent picked the right skill **more often** with the 30-skill loadout than with all 840 — **97% vs 93%**. Full reports: [`BENCHMARK.md`](./BENCHMARK.md) · [`PERFORMANCE.md`](./PERFORMANCE.md) · [`benchmark/ab_eval/`](./benchmark/ab_eval/).

## How it works

<p align="center">
  <img src="docs/assets/from-hello-to-trusted-teammate.svg" alt="Three bands: intake and trust (registration, safety gate, registry, discovery), scouting engine (task matcher, sandboxed A/B arena, evidence log, dossier), human control (blind 3-reviewer quorum, decision policy, lifecycle controller)." width="100%">
</p>

- **Intake & trust** — you clone a candidate repo; Quartermaster scans it **without running its code**, hashes content, flags risky patterns, and imports only what you accept.
- **Scouting engine** — `qm scout` pins exact versions, runs randomized paired A/B jobs in **your own sandboxed worker** (any provider), and writes an honest dossier: quality deltas, confidence intervals, cost, limitations.
- **Human control** — three reviewers score the dossier **blind**; two accepts approve, any safety veto blocks. Even then, lifecycle changes go through your normal review, and `qm revert` undoes them.

Every skill sits on a reversible ladder — each step logged, only the last one gated by your explicit `--yes`:

| | **active** | **demoted** | **hidden** | **archived** | **deleted** |
|---|:---:|:---:|:---:|:---:|:---:|
| in context | ✅ | ✅ | ❌ | ❌ | ❌ |
| auto-selected | ✅ | ❌ | ❌ | ❌ | — |
| on disk | ✅ | ✅ | ✅ | ✅ | ❌ |

## How to run

```bash
# Claude Code plugin …
/plugin marketplace add ginaecho/skill-quartermaster
/plugin install quartermaster@skill-quartermaster

# … or zero install (pure Python, stdlib only)
export QM_SKILLS_DIR=~/.claude/skills
python3 bin/qm status
```

```bash
# Daily loop
qm status              # every skill: state, last used, token cost
qm compile "<intent>"  # pick the ~30 skills this project needs
qm review              # approve proposed changes
qm restore <skill>     # bring anything back
qm revert              # undo the last automatic change

# Vet a new skill: scan, then trial
qm intake <cloned-repo> --dry-run       # scan safely — never executes code
qm scout plan <candidate> --suite benchmark/scout/suite.example.json \
  --current-skill <current-default> --source <repo-url> --version <commit>
qm scout run scout-plan.json --runner python --runner-arg <isolated_runner.py>
qm scout report scout-plan.json scout-trials.jsonl
qm scout review scout-evidence.json reviewer-votes.json --author <owner>
```

`qm --help` lists the rest (demote, hide, archive, conflicts, gaps, authoring, feedback). A worked Copilot case study lives in [`benchmark/scout/`](./benchmark/scout/); schemas and trust boundaries in [`docs/SCOUTING.md`](./docs/SCOUTING.md). All state stays in `~/.quartermaster/` — **nothing leaves your machine**. Tests: `python3 -m pytest` (128 pass).

## Roadmap

Shipped: lifecycle core, telemetry, authoring arm, feedback, Skill Scout. In design for v1.0: semantic discovery, prompt-injection & provenance gates, trust tiers, dashboard — the not-yet parts of the figures above.

## Contributing & license

Issues before large PRs, please. Adapters for other harnesses (Cursor, Copilot, Zed) especially welcome. MIT — see [LICENSE](./LICENSE).

---

<p align="center"><sub>♥ Every production skill: explainable, reproducible, and cared for.</sub></p>
