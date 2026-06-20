---
description: Bring a demoted or hidden skill back to active.
argument-hint: <skill name>
---

Restore a skill to active state with Quartermaster:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" restore "$ARGUMENTS"
```

If no skill name was given, run `qm status` first and ask the user which skill
to restore. Confirm the result after restoring.
