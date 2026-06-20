---
description: Route a plain-language complaint about skills/style to the right Quartermaster lever.
argument-hint: <what's off, e.g. "this isn't matching my style">
---

Pass the user's feedback to Quartermaster, which classifies and routes it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" feedback "$ARGUMENTS"
```

How it routes:
- **style** miss → appended to the always-on style file (the "constitution").
- **capability** miss → recorded as a gap (run `/qm-gaps` to consider authoring).
- **"stop suggesting X"** → suggests demoting X.
- **"I keep using X"** → suggests restoring/promoting X.

Only the local style note and gap log are written automatically. For a
suggested demote/promote, confirm with the user, then either run the suggested
`qm` command or re-run with `--apply`.
