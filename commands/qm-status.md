---
description: Show installed skills, lifecycle state, optional layer metadata, archived skills, and token-saved report.
argument-hint: "[--layers] [--all]"
---

Run Quartermaster's status report and show the output to the user.

Use `$ARGUMENTS` if provided, for example `--layers` or `--all`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" status $ARGUMENTS
```

Summarize the headline numbers (skills installed, loaded, tokens saved) and
point out anything notable:
- `--layers` shows metadata layer and priority.
- `--all` includes archived skills.

Do not make any changes — `status` is read-only.
