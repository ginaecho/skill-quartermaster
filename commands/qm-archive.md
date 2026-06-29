---
description: Move a skill to reversible archive storage outside active skill roots.
argument-hint: <skill name>
---

Archive a skill with Quartermaster.

First preview the current state if needed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" status --all
```

Then archive the named skill after the user confirms:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" archive "$ARGUMENTS" --yes
```

Archiving is non-destructive: the skill is moved to `$QM_HOME/archive`, recorded
in the archive manifest with a checksum, and restored with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" restore "$ARGUMENTS"
```

Never use `qm delete` as a substitute for archive.
