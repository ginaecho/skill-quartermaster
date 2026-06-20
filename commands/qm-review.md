---
description: Show Quartermaster's proposed skill demotions/promotions/hides and approve them in one batch.
---

Run Quartermaster's policy engine in dry-run mode and present the proposals:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" review --dry-run
```

Explain each proposal (what changes, and why — e.g. unused for N days). Ask the
user to approve. On approval, apply them:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" review --yes
```

All proposals are non-destructive (demote/hide/promote) and reversible with
`qm restore <skill>`. Never delete anything here.
