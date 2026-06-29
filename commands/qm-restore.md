---
description: Bring a demoted, hidden, or archived skill back to active.
argument-hint: <skill name>
---

Restore a skill to active state with Quartermaster. This also restores archived
skills from `$QM_HOME/archive` when the skill is no longer in active roots:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" restore "$ARGUMENTS"
```

If no skill name was given, run `qm status --all` first and ask the user which
skill to restore. Confirm the result after restoring.
