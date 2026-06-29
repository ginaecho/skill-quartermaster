---
description: Report explicit and inferred conflicts among installed skills.
---

Run Quartermaster's conflict detector:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" conflicts
```

Explain any conflicts to the user before applying a compiled loadout. Guardrail
conflicts require user resolution; do not force a risky action through a
reported conflict.
