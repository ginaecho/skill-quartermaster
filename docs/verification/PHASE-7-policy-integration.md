# Phase 7 Verification: Policy Integration

## Scope

Phase 7 integrates the new lifecycle concepts into policy review.

Implemented behavior verified here:

- Hidden skills can be proposed for archive after a configurable stale window.
- Archived skills can be proposed for restore when recent usage/request evidence
  exists.
- `qm review` includes archived records when computing proposals.
- `qm review --yes` applies archive proposals through archive storage.
- Guardrail-aware stale windows from Phase 4 remain active.

## Test Commands And Results

### Targeted Policy Integration Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_policy_integration.py -q
```

Result:

```text
....                                                                     [100%]
4 passed in 0.33s
```

Evidence:

- `test_policy_proposes_archive_for_long_hidden_skill` proves hidden-to-archive
  proposals work.
- `test_policy_proposes_restore_for_recently_used_archived_skill` proves
  archived-to-restore proposals work.
- `test_review_dry_run_reports_archive_proposal` proves CLI dry-run displays
  archive proposals.
- `test_review_yes_applies_archive_proposal` proves review applies archive
  proposals and updates history.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 69%]
................................                                         [100%]
104 passed in 1.31s
```

Evidence:

- Existing adapter, metadata, history, layered compile, guardrail, conflict,
  archive, lifecycle, authoring, feedback, and frontmatter tests still pass.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/old"
cat > "$tmp/skills/old/SKILL.md" <<'EOF'
---
name: old
description: old skill
disable-model-invocation: true
user-invocable: false
---
# old
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 - <<'PY'
import time
from qm import store
store.record_usage('old', ts=time.time() - 120*86400)
PY
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" \
  python3 bin/qm review --archive-after 90 --dry-run
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" \
  python3 bin/qm review --archive-after 90 --yes
```

Result:

```text
1 proposal(s):

  1. archive old  (hidden → archived)  — unused for 120d (>= 90d)

(dry run — nothing changed)
1 proposal(s):

  1. archive old  (hidden → archived)  — unused for 120d (>= 90d)

Applied 1 transition(s). All reversible via `qm restore <skill>`.
```

Evidence:

- Review proposes archive without mutation in dry-run mode.
- Review applies the archive proposal only with explicit `--yes`.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| `qm review --dry-run` can propose archive and restore actions. | Pass | Targeted tests and smoke test |
| Archive proposals are reversible and non-destructive. | Pass | Archive module tests plus review apply test |
| Guardrail-aware policy behavior remains intact. | Pass | Full regression includes guardrail policy tests |
| Existing tests still pass. | Pass | Full regression suite: `104 passed` |

## Decision

Phase 7 is verified as successful.

Proceed to Phase 8: Evaluation And Benchmarks.
