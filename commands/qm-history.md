---
description: Inspect Quartermaster's historical dictionary entry for a skill.
argument-hint: <skill name>
---

Show recorded usage, selection, state, runtime, archive path, and metadata for a
skill:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" history "$ARGUMENTS"
```

Use this before deciding whether to restore, archive, demote, or author a
replacement skill. The history is local-only under `$QM_HOME/skills.json`.
