# Phase 1 Verification: Skill Metadata Model

## Scope

Phase 1 adds an optional, dependency-free metadata model for skills.

Implemented behavior verified here:

- Parse optional `qm-*` frontmatter keys.
- Normalize metadata into a `SkillMetadata` dataclass.
- Attach metadata to every registry `Skill`.
- Infer a default layer for existing skills without metadata.
- Treat malformed priority and invalid layer values safely.
- Preserve existing skill loading behavior.
- Expose layer and priority through `qm status --layers`.

## Test Commands And Results

### Targeted Metadata Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_metadata.py -q
```

Result:

```text
......                                                                   [100%]
6 passed in 0.26s
```

Evidence:

- `test_parse_explicit_metadata_fields` proves all planned Phase 1 keys parse:
  `qm-layer`, `qm-priority`, `qm-tags`, `qm-risk`, `qm-provides`,
  `qm-requires`, `qm-requires-guardrails`, and `qm-conflicts-with`.
- `test_malformed_priority_defaults_to_zero_and_invalid_layer_is_inferred`
  proves malformed metadata fails safe.
- `test_existing_skill_without_metadata_gets_safe_defaults` proves old skills
  still load with default metadata.
- `test_layer_inference_uses_name_description_and_tags` proves fallback layer
  inference works.
- `test_registry_attaches_metadata_from_frontmatter` proves registry entries
  receive normalized metadata.
- `test_status_layers_prints_layer_and_priority` proves the CLI can display
  layer and priority.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 0.87s
```

Evidence:

- Existing runtime adapter, lifecycle, transition, policy, compile, history,
  authoring, feedback, and frontmatter tests still pass after metadata was
  added.
- Existing skills without metadata remain compatible.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/secure"
cat > "$tmp/skills/secure/SKILL.md" <<'EOF'
---
name: secure
description: security hardening helper
qm-layer: guardrail
qm-priority: 100
---
# secure
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" python3 bin/qm status --layers
```

Result:

```text
  SKILL   STATE    LAYER       PRI LAST USED   TOKENS
  ---------------------------------------------------
  secure  ● active guardrail   100 never            8

  1 skills  ·  1 active  ·  0 demoted  ·  0 hidden
  context: ~8 tokens   saved by hiding: ~0 tokens   (0 deleted)
```

Evidence:

- The CLI reads explicit frontmatter metadata.
- The metadata is attached to the registry entry used by reports.
- Default status remains unchanged unless `--layers` is requested.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Existing tests pass unchanged. | Pass | Full regression suite: `75 passed` |
| Existing skills without new metadata still load. | Pass | Default metadata test and regression suite |
| `qm status` can optionally show layer and priority metadata. | Pass | `status --layers` test and CLI smoke test |
| Metadata parsing has no new dependency. | Pass | Implementation uses stdlib and existing frontmatter parser |
| Malformed metadata fails safe. | Pass | Malformed priority/invalid layer test |

## Decision

Phase 1 is verified as successful.

Proceed to Phase 2: Historical Dictionary.
