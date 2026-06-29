# Phase 4 Verification: Guardrail Dominance

## Scope

Phase 4 makes guardrails enforce constraints instead of behaving like ordinary
matched skills.

Implemented behavior verified here:

- Risky action/tool skills can declare required guardrails.
- Compile blocks risky skills when required guardrails are missing.
- Compile auto-adds matching guardrails when available.
- Required guardrails can displace lower-priority non-guardrail skills at cap.
- CLI output reports blocked skills and missing guardrails.
- Review policy uses longer stale windows for guardrail skills.

## Test Commands And Results

### Targeted Guardrail Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_guardrails.py -q
```

Result:

```text
....                                                                     [100%]
4 passed in 0.41s
```

Evidence:

- `test_risky_action_without_required_guardrail_is_blocked` proves unsafe
  action skills are removed from keep when guardrails are missing.
- `test_required_guardrail_is_auto_added_and_can_displace_lower_priority`
  proves available guardrails are inserted and protected from cap pressure.
- `test_compile_cli_reports_blocked_guardrail_gap` proves CLI output explains
  blocked capabilities.
- `test_guardrail_policy_uses_longer_stale_windows` proves policy review does
  not demote guardrails on the same stale window as ordinary skills.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 80%]
.................                                                        [100%]
89 passed in 1.38s
```

Evidence:

- Existing adapter, metadata, history, layered compile, lifecycle, policy,
  authoring, feedback, and frontmatter tests still pass.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/deploy"
cat > "$tmp/skills/deploy/SKILL.md" <<'EOF'
---
name: deploy
description: deploy production service
qm-layer: action
qm-risk: production
qm-requires-guardrails: change-review
---
# deploy
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" \
  python3 bin/qm compile "deploy production" --dry-run
```

Result:

```text
Intent: deploy production
Loadout cap: 30

Keep active (0):

Blocked:
  ! deploy: missing guardrail for change-review

Demote (1):
  ◐ deploy  [off-intent, layer action, priority 26]

(dry run — nothing changed)
```

Evidence:

- The risky action matched the intent but was still blocked because its required
  guardrail was absent.
- The CLI surfaces the missing guardrail before any changes are applied.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Risky action/tool skills cannot become active without required guardrails. | Pass | Blocked risky action test and smoke test |
| Available guardrails are auto-added. | Pass | Auto-add/displacement test |
| Guardrail conflicts fail safe. | Deferred to Phase 5 | Conflict-specific behavior belongs to the conflict detection phase |
| Review policy does not casually hide important guardrails. | Pass | Guardrail stale-window policy test |
| Existing tests still pass. | Pass | Full regression suite: `89 passed` |

## Decision

Phase 4 is verified as successful for guardrail requirement enforcement and
stale-window protection. Guardrail-vs-guardrail conflict behavior is explicitly
covered in Phase 5.

Proceed to Phase 5: Conflict Detection.
