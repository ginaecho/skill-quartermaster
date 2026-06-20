# Quartermaster benchmark

_Corpus_: `/tmp/skillhub` — real open-source skills.  
_Run_: seed=7, cap=30, 2026-06-20.

## 1. Discovery & state derivation

- Skills discovered: **851** (from 851 `SKILL.md` files)
- States derived from real frontmatter: {'active': 851}
- Skills shipping their own invocation flags (`disable-model-invocation`/`user-invocable`): **5**

## 2. Standing context cost (all skills installed & active)

- Indexed tokens up front (name+description, ~4 chars/token): **~59.7k**
- Mean per skill: **~70 tokens**
- Skills in the model's auto-selection set: **851** (far past the ~30 accuracy sweet spot / ~100 cliff)

## 3. Compiled loadout + headline savings

- Project intent: _a python fastapi backend with postgres database, docker, redis cache, pytest tests and github actions ci_
- Active loadout: **30** skills (auto-select set 851 → 30, **28× smaller**)
- Skills hidden out of context: **821**
- Context tokens: ~59.7k → ~2.2k
- **Tokens saved this session: ~57.5k (96.3%)**
- Deleted: **0**

> 851 skills installed → 30 loaded → ~57.5k tokens saved → 0 deleted

Sample of the compiled loadout (skill — matched intent terms):

- `github-actions-creator` — actions, ci, docker, github
- `senior-backend` — backend, database, postgres, python
- `fastapi-endpoint` — fastapi, pytest, tests
- `gh-fix-ci` — actions, ci, github
- `github-workflow-automation` — actions, ci, github
- `python-testing-patterns` — pytest, python, tests
- `railway-database` — database, postgres, redis
- `railway-templates` — database, postgres, redis
- `supply-chain-guard` — actions, ci, github
- `android-cicd` — ci, github
- `backend-dev-guidelines` — backend, database
- `backend-patterns` — backend, database

## 4. Policy engine on simulated usage

- Simulated history: 42 fresh (<5d), 128 warm (20-40d), 681 stale (>60d)
- Cycle 1 (all active) → **809** demote proposals (unused ≥14d)
- Cycle 2 (after accepting demotions) → **737** hide proposals (demoted + unused ≥30d)
- Fresh skills correctly left active: **42** untouched in cycle 1
- Every proposal is reversible and nothing is executed without approval.

## 5. Non-destructive guarantee

- Files on disk before vs after every operation above: **851 → 851** (deleted: **0**)
- demote→restore byte-identical: **200/200** sampled skills

## 6. Authoring arm

- Fed 3 natural-language gap reports → clustered → **1** authoring proposal(s)
  - suggests `module-terraform-generate` (cluster: module / terraform / generate, 2 hits)

---

_Reproduce_: build a corpus of `<skill>/SKILL.md` dirs and run `python3 benchmark/run_benchmark.py <corpus_dir>`.
