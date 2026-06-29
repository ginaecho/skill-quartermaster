# Phase 5 Verification: Conflict Detection

## Scope

Phase 5 adds explicit and inferred conflict detection, compile-time conflict
resolution, and an installed-skill diagnostic command.

Implemented behavior verified here:

- Explicit `qm-conflicts-with` metadata is detected.
- Action/tool skills that provide the same capability are inferred as conflicts.
- Compile-time non-guardrail conflicts are resolved by priority.
- Guardrails dominate non-guardrails.
- Guardrail-vs-guardrail conflicts are blocked for user decision.
- `qm conflicts` reports installed conflicts.

## Test Commands And Results

### Targeted Conflict Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_conflicts.py -q
```

Result:

```text
.....                                                                    [100%]
5 passed in 0.29s
```

Evidence:

- `test_explicit_conflict_is_detected` proves `qm-conflicts-with` works.
- `test_inferred_action_provider_conflict_is_detected` proves duplicate
  action/tool providers are detected.
- `test_compile_drops_lower_priority_conflict` proves compile plans drop the
  lower-priority conflicting skill.
- `test_guardrail_conflict_blocks_both_for_user_decision` proves guardrail
  conflicts fail safe.
- `test_conflicts_command_reports_conflicts` proves CLI diagnostics work.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 76%]
......................                                                   [100%]
94 passed in 1.19s
```

Evidence:

- Existing adapter, metadata, history, layered compile, guardrail, lifecycle,
  policy, authoring, feedback, and frontmatter tests still pass.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/a" "$tmp/skills/b"
cat > "$tmp/skills/a/SKILL.md" <<'EOF'
---
name: a
description: a
qm-conflicts-with: b
---
# a
EOF
cat > "$tmp/skills/b/SKILL.md" <<'EOF'
---
name: b
description: b
---
# b
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm conflicts
```

Result:

```text
1 conflict(s):
  ! a ↔ b  — a declares conflict with b
```

Evidence:

- Installed-skill conflict diagnostics are user-visible and non-mutating.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Compiler reports conflicts before applying a loadout. | Pass | Compile conflict tests use `plan.blocked` |
| Non-guardrail conflicts are resolved by priority. | Pass | Lower-priority conflict test |
| Guardrail conflicts require user decision. | Pass | Guardrail conflict block test |
| Tests cover explicit conflict, inferred conflict, and no-conflict paths. | Pass | Targeted conflict tests plus full regression |
| Existing tests still pass. | Pass | Full regression suite: `94 passed` |

## Decision

Phase 5 is verified as successful.

Proceed to Phase 6: Archive And Restore.
