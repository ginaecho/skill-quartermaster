---
description: Write workspace-local setup files for a Quartermaster runtime adapter.
argument-hint: "[runtime|--all]"
---

Set up local runtime guidance/manifests for Claude, Codex, Copilot CLI, VS Code,
or generic command agents:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" runtime-setup $ARGUMENTS
```

Examples:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" runtime-setup codex
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" runtime-setup --all
```

This writes local files only. It does not require vendor credentials and does
not delete or move skills.
