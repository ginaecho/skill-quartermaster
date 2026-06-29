---
description: List Quartermaster's supported runtime adapters.
---

Show supported agent runtime adapters and their default skill roots:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" runtimes
```

Use `--runtime <name>` or `QM_RUNTIME=<name>` to select an adapter. Claude is
the default; Codex, Copilot CLI, VS Code, and generic command-agent adapters
currently share the runtime-neutral lifecycle and loadout manifest layer.
