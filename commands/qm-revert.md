---
description: Undo Quartermaster's most recent automatic skill change(s).
argument-hint: "[number of changes, default 1]"
---

Preview what would be undone, then apply it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" revert -n ${ARGUMENTS:-1} --dry-run
```

Show the plan to the user. On confirmation:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" revert -n ${ARGUMENTS:-1} --yes
```

Revert walks the audit trail backwards and applies the inverse of each change.
Deletions and skill admissions are skipped — those stay human-gated. Every
revert is itself logged, so the trail stays complete.
