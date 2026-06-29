---
description: Compile an active skill loadout for this project from a plain-language intent.
argument-hint: <project intent, e.g. "rust web API with sqlx and axum">
---

Use Quartermaster to compile a per-project skill loadout.

The user's intent is: $ARGUMENTS

If no intent was provided, infer it from the project (README, language, key
dependencies) and state the inferred intent before proceeding.

First show the plan without applying:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" compile "<intent>" --dry-run
```

Present the proposed layered keep/demote/block split to the user. Explain any
guardrails, conflicts, or blocked risky skills before applying. Once they
approve, apply it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" compile "<intent>" --yes
```

Then run `qm status --layers` so the user sees the resulting loadout, layer
priority, and token savings. Applied compiles also write a loadout manifest
under `$QM_HOME/loadouts/` through the selected runtime adapter.

Nothing is deleted — off-intent skills are only demoted and fully reversible
with `qm restore`.
