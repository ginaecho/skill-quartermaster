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

Present the proposed keep/demote split to the user. Once they approve, apply it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" compile "<intent>" --yes
```

Then run `qm status` so the user sees the resulting loadout and token savings.
Nothing is deleted — off-intent skills are only demoted and fully reversible
with `qm restore`.
