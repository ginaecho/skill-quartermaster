# Phase 2 Verification: Historical Dictionary

## Scope

Phase 2 turns raw local logs into a queryable per-skill dictionary at
`$QM_HOME/skills.json`.

Implemented behavior verified here:

- Registry load records skills as seen.
- Historical entries include path, runtime, state, metadata, and timestamps.
- Usage telemetry updates `last_used` and `usage_count`.
- State transitions update state counters and current state.
- Compile selections update `selected_count` and useful intents.
- `qm history <skill>` prints a human-readable dictionary entry.

## Test Commands And Results

### Targeted Historical Dictionary Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_skill_history.py -q
```

Result:

```text
......                                                                   [100%]
6 passed in 0.47s
```

Evidence:

- `test_registry_load_records_skill_seen` proves discovery writes dictionary
  entries with path, runtime, state, and metadata.
- `test_usage_updates_historical_dictionary` proves usage telemetry increments
  `usage_count` and updates `last_used`.
- `test_transition_updates_counts_and_state` proves demote/hide transitions
  update counters and current state.
- `test_compile_records_selected_intent` proves compile selections record useful
  intents and selected count.
- `test_history_command_prints_entry` proves `qm history <skill>` reads and
  prints the dictionary entry.
- `test_history_command_unknown_skill` proves unknown history requests fail
  clearly.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 1.41s
```

Evidence:

- Existing adapter, metadata, lifecycle, policy, compile, history/revert,
  authoring, feedback, and frontmatter behavior still passes after adding the
  historical dictionary.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/rusty"
cat > "$tmp/skills/rusty/SKILL.md" <<'EOF'
---
name: rusty
description: rust cargo helper
qm-layer: action
qm-priority: 10
---
# rusty
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm status >/dev/null
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm history rusty
```

Result:

```text
History for rusty:
  state: active
  path: /var/folders/n0/g7l9b2qx04lgs1dxsr5v_qgc0000gn/T/tmp.sZmiaaaze5/skills/rusty/SKILL.md
  runtime: claude
  first_seen: 2026-06-28 21:23
  last_seen: 2026-06-28 21:23
  last_used: -
  usage_count: 0
  selected_count: 0
  demoted_count: 0
  hidden_count: 0
  archive_count: 0
  archive_path: -
  metadata:
    layer: action
    priority: 10
    tags: []
    risk: []
    provides: []
    requires: []
    requires_guardrails: []
    conflicts_with: []
```

Evidence:

- A read-only `qm status` scan creates/refreshes the historical dictionary.
- `qm history` exposes both lifecycle information and Phase 1 metadata.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Historical dictionary survives normal skill discovery. | Pass | Registry load test and CLI smoke test |
| Usage telemetry updates historical usage. | Pass | Usage test |
| Transitions update historical state/counters. | Pass | Transition test |
| Compile records selected skills and useful intents. | Pass | Compile selection test |
| `qm history <skill>` works for active skills. | Pass | CLI command test and smoke test |
| Existing tests still pass. | Pass | Full regression suite: `81 passed` |

## Decision

Phase 2 is verified as successful.

Proceed to Phase 3: Layer-Aware Compiler.
