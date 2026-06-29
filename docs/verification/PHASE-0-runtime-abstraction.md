# Phase 0 Verification: Runtime Abstraction

## Scope

Phase 0 makes Quartermaster runtime-aware before richer metadata, layering,
conflict, and archive behavior are added.

Implemented behavior verified here:

- Claude remains the default runtime.
- `QM_RUNTIME` and `qm --runtime <name>` select an adapter.
- `qm runtimes` lists supported adapters.
- `qm runtime-setup` writes workspace-local setup files for selected runtimes.
- Registry discovery and lifecycle state derivation use the selected adapter.
- Transitions write state through the selected adapter.
- Existing Claude behavior remains backward compatible.
- Generic/non-Claude runtime state is persisted through `qm-state`.

## Test Commands And Results

### Targeted Adapter Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_adapters.py -q
```

Result:

```text
.......                                                                  [100%]
7 passed in 0.62s
```

Evidence:

- `test_default_runtime_is_claude` proves the default adapter remains Claude.
- `test_unknown_runtime_is_rejected` proves invalid runtime names fail fast.
- `test_registry_uses_runtime_from_environment` proves `QM_RUNTIME=generic`
  changes registry state derivation.
- `test_generic_transition_writes_qm_state` proves generic demotion writes
  `qm-state: demoted` rather than Claude flags.
- `test_generic_restore_writes_explicit_active_state` proves generic restore
  writes `qm-state: active`.
- `test_claude_runtime_keeps_existing_frontmatter_flags` proves Claude demotion
  still writes `disable-model-invocation: true`.
- `test_runtimes_command_lists_supported_adapters` proves the CLI lists
  `claude`, `codex`, `copilot`, `generic`, and `vscode`.
- `test_runtime_setup_writes_codex_files` proves Codex setup writes local
  instruction/manifest files and creates a skill root.
- `test_runtime_setup_all_writes_each_runtime` proves setup can write files for
  all runtime adapters.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
.....................................................................    [100%]
69 passed in 1.79s
```

Evidence:

- Existing lifecycle, frontmatter, policy, compile, history, feedback, authoring,
  and CLI behavior still passes after introducing adapters.
- No existing Claude-centric behavior regressed.

### CLI Smoke Tests

Command:

```bash
python3 bin/qm runtimes
python3 bin/qm --runtime generic status
```

Result:

```text
Available runtimes:
  * claude   Claude Code skills, plugin commands, and frontmatter flags.
      roots: .claude/skills, /Users/tzu-chunchen/.claude/skills
    codex    Codex-compatible exported loadouts and local skill folders.
      roots: .codex/skills, /Users/tzu-chunchen/.codex/skills
    copilot  GitHub Copilot CLI loadout manifests and command wrappers.
      roots: .github/copilot/skills, /Users/tzu-chunchen/.quartermaster/copilot/skills
    generic  Runtime-neutral skill folders using Quartermaster manifests.
      roots: .quartermaster/skills, /Users/tzu-chunchen/.quartermaster/skills
    vscode   VS Code workspace-local instructions and skill manifests.
      roots: .vscode/quartermaster/skills, /Users/tzu-chunchen/.quartermaster/vscode/skills
No skills found. Set QM_SKILLS_DIR or run inside a project with runtime skills.
```

Evidence:

- The CLI exposes all planned runtime adapter names.
- Claude is marked as the active default runtime.
- Generic runtime can be selected without crashing even when no generic skill
  roots exist.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Current Claude behavior still works through the `claude` adapter. | Pass | Full regression suite, Claude frontmatter adapter test |
| `qm status` and runtime selection work with `--runtime generic`. | Pass | CLI smoke test and generic adapter tests |
| Core registry/transitions no longer hard-code only Claude state writes. | Pass | Generic transition tests write/read `qm-state` |
| Tests cover adapter selection and default compatibility. | Pass | `tests/test_adapters.py` |
| Runtime adapters can write workspace-local setup files. | Pass | Runtime setup tests |

## Decision

Phase 0 is verified as successful.

Proceed to Phase 1: Skill Metadata Model.
