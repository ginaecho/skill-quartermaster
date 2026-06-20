---
description: Show every installed skill, its lifecycle state, last-used date, and the token-saved report.
---

Run Quartermaster's status report and show the output to the user:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" status
```

Summarize the headline numbers (skills installed, loaded, tokens saved) and
point out anything notable (e.g. skills unused for a long time that could be
demoted). Do not make any changes — `status` is read-only.
