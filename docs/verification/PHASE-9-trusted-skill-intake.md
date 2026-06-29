# Phase 9 Verification: Trusted Skill Intake

## Scope

Phase 9 adds a safe path for considering public Git repositories as skill
sources without blindly installing untrusted content.

Implemented behavior verified here:

- `qm sources` lists curated candidate repositories and trust notes.
- `qm intake <local_repo> --dry-run` scans local checkouts only.
- The scanner never executes candidate code.
- Suspicious shell/install/exfiltration patterns are rejected.
- High-value guardrail/testing/review/tooling skills are accepted.
- `qm intake <local_repo> --yes` imports only accepted skills.

## Test Commands And Results

### Targeted Intake Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_intake.py -q
```

Result:

```text
.....                                                                    [100%]
5 passed in 0.16s
```

Evidence:

- `test_intake_accepts_safe_high_value_skill` proves safe guardrail-like skills
  pass the value gate.
- `test_intake_rejects_suspicious_skill` proves suspicious shell execution is
  rejected.
- `test_intake_imports_only_accepted_skills` proves import copies only accepted
  candidates.
- `test_sources_command_lists_curated_repos` proves curated sources are visible.
- `test_intake_cli_dry_run` proves the CLI scans without importing.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Risky candidate skills are rejected. | Pass | Suspicious skill test |
| Safe, high-value skills are accepted. | Pass | Guardrail candidate test |
| Import copies only accepted skills. | Pass | Import test |
| Intake is local-only and never runs candidate code. | Pass | Implementation and dry-run test |

## Decision

Phase 9 is verified as successful.

Full regression result:

```text
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 0.69s
```

CLI smoke result:

```text
Curated external skill sources:
  anthropics-skills [high]
    https://github.com/anthropics/skills
    Official Anthropic skills repository; prefer as the first external corpus.
  claude-code-templates [medium]
    https://github.com/davila7/claude-code-templates
    Large community corpus useful for breadth; requires strict filtering.
  obra-superpowers [medium]
    https://github.com/obra/superpowers
    Small workflow-oriented community skill set; scan before import.

Clone externally, inspect if desired, then run `qm intake <path> --dry-run`.
Scanned 1 candidate skill(s).
Accepted by safety/value gate: 1

  accept security-review              layer=guardrail value=6  risks=-

(dry run — nothing imported)
```
