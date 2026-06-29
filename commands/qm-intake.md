---
description: Safely scan and optionally import high-value skills from a local external repo checkout.
argument-hint: <local repo path>
---

Scan an external skill repo checkout without executing candidate code:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" intake "$ARGUMENTS" --dry-run
```

Review accepted/rejected candidates with the user. If they approve, import
accepted skills explicitly:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" intake "$ARGUMENTS" --yes
```

The scanner rejects suspicious shell/install/exfiltration patterns and imports
only accepted high-value skills. Do not import from a repo without the dry-run
review first.
