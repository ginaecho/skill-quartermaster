# Phase 3 Verification: Layer-Aware Compiler

## Scope

Phase 3 replaces flat selection behavior with a richer compile plan while
preserving the existing `compile_loadout` API.

Implemented behavior verified here:

- Compile plans group kept skills by layer.
- Compiler reserves room for high-priority guardrail/style skills.
- Priority combines intent match, metadata priority, layer weight, usage count,
  and previous selection count.
- CLI dry-runs explain layer, score, priority, and reasons.
- Applied compile writes a runtime loadout manifest through the selected
  adapter.
- Existing cap behavior remains predictable.

## Test Commands And Results

### Targeted Layered Compiler Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_layered_compile.py -q
```

Result:

```text
....                                                                     [100%]
4 passed in 0.16s
```

Evidence:

- `test_layered_compile_reserves_guardrail_before_domain_cap` proves guardrails
  are not displaced by domain skills at a tight cap.
- `test_layered_compile_uses_metadata_and_history_in_priority` proves metadata
  and historical usage influence priority.
- `test_compile_dry_run_explains_layers` proves CLI output exposes layers and
  priority.
- `test_compile_apply_exports_runtime_manifest` proves applied compile exports
  a runtime manifest through the adapter.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 84%]
.............                                                            [100%]
85 passed in 1.15s
```

Evidence:

- Existing compile, policy, lifecycle, adapter, metadata, history, authoring,
  feedback, and frontmatter behavior still passes after layering.

### CLI Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/security" "$tmp/skills/rusty"
cat > "$tmp/skills/security/SKILL.md" <<'EOF'
---
name: security
description: security guardrail
qm-layer: guardrail
qm-priority: 100
---
# security
EOF
cat > "$tmp/skills/rusty/SKILL.md" <<'EOF'
---
name: rusty
description: rust cargo helper
---
# rusty
EOF
QM_HOME="$tmp/home" QM_SKILLS_DIR="$tmp/skills" \
  python3 bin/qm --runtime generic compile "rust cargo" --yes
```

Result:

```text
Intent: rust cargo
Loadout cap: 30

Keep active (2):
  [guardrail]
    ● security  [score 0, priority 130: metadata-priority:100; layer:guardrail]
  [domain]
    ● rusty  [score 2, priority 28: intent:cargo,rust; layer:domain]

Added guardrails:
  + security  [priority 130]

Loadout manifest: /var/folders/n0/g7l9b2qx04lgs1dxsr5v_qgc0000gn/T/tmp.ZfUciplPF6/home/loadouts/default-generic.json

Applied. 0 transition(s). Run `qm status` to see the loadout.
```

Evidence:

- Guardrail selection is shown before domain skills.
- Intent score and metadata/layer priority are visible.
- The selected runtime adapter writes a loadout manifest.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| `qm compile "<intent>" --dry-run` explains the loadout by layer. | Pass | Targeted CLI test |
| Guardrail skills are not displaced by many domain matches. | Pass | Tight-cap guardrail reservation test |
| Cap behavior remains predictable and tested. | Pass | Existing compile tests plus layered cap test |
| Runtime-specific output is generated only by adapters. | Pass | Manifest export is implemented in adapter hook and tested |
| Existing tests still pass. | Pass | Full regression suite: `85 passed` |

## Decision

Phase 3 is verified as successful.

Proceed to Phase 4: Guardrail Dominance Rules.
