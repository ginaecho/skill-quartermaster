# Phase 6 Verification: Archive And Restore

## Scope

Phase 6 adds reversible archived storage as a lifecycle state outside active
skill roots.

Implemented behavior verified here:

- `qm archive <skill>` moves a skill directory to `$QM_HOME/archive`.
- Archive manifest records original path, archive path, checksum, runtime, and
  reason.
- `qm status --all` includes archived skills.
- `qm restore <skill>` restores an archived skill byte-identically.
- `qm delete <skill> --yes` can permanently remove an archived skill.
- Archived deletion remains human-gated.
- Historical dictionary keeps archive state and metadata.

## Test Commands And Results

### Targeted Archive Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_archive.py -q
```

Result:

```text
......                                                                   [100%]
6 passed in 0.40s
```

Evidence:

- `test_archive_moves_skill_and_records_manifest` proves archive movement,
  manifest creation, checksum recording, and audit logging.
- `test_restore_from_archive_is_byte_identical` proves restore checksum matches
  the original directory.
- `test_status_all_includes_archived_skill` proves archived skills appear only
  through explicit all-state status.
- `test_delete_archived_requires_yes` proves archived deletion is human-gated.
- `test_delete_archived_with_yes_removes_archive` proves explicit deletion
  removes archived files and logs the destructive transition.
- `test_archived_history_survives_hidden_from_active_roots` proves the
  historical dictionary keeps archive state and metadata.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 1.08s
```

Evidence:

- Existing adapter, metadata, history, layered compile, guardrail, conflict,
  lifecycle, policy, authoring, feedback, and frontmatter tests still pass.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/a"
cat > "$tmp/skills/a/SKILL.md" <<'EOF'
---
name: a
description: alpha skill
---
# a
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm archive a --yes
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm status --all
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm restore a
```

Result:

```text
a: active → archived.
Archive path: /var/folders/n0/g7l9b2qx04lgs1dxsr5v_qgc0000gn/T/tmp.xc7dotWML0/home/archive/a/1782675598
Restore with `qm restore a`.
  SKILL  STATE    LAST USED   TOKENS
  ----------------------------------
  a     □ archived never            -

  1 skills  ·  0 active  ·  0 demoted  ·  0 hidden  ·  1 archived
  context: ~0 tokens   saved by hiding: ~0 tokens   (0 deleted)
a: archived → active.
Restored to /var/folders/n0/g7l9b2qx04lgs1dxsr5v_qgc0000gn/T/tmp.xc7dotWML0/skills/a/SKILL.md.
```

Evidence:

- The CLI can archive, show, and restore without direct file manipulation.
- Archived skills are not counted as loaded or in-context.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Archive removes the skill from active roots but keeps it listed in history. | Pass | Archive tests and history test |
| Restore recreates the original skill directory byte-identically. | Pass | Restore checksum test |
| Delete remains explicit and irreversible. | Pass | Archived delete gate/delete tests |
| Existing `demote`, `hide`, and `restore` behavior remains compatible. | Pass | Full regression suite |
| Existing tests still pass. | Pass | Full regression suite: `100 passed` |

## Decision

Phase 6 is verified as successful.

Proceed to Phase 7: Policy Integration.
