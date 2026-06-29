# Phase 8 Verification: Evaluation And Benchmarks

## Scope

Phase 8 adds deterministic local evaluation support for the layered compiler and
lifecycle model.

Implemented behavior verified here:

- `qm.evaluation.evaluate()` computes guardrail recall, blocked count, conflict
  count, archived count, context tokens, and saved tokens.
- `benchmark/layered_eval.py` runs those metrics from the command line against
  any `<skill>/SKILL.md` corpus.
- The benchmark path is pure local/stdlib and does not require external model
  APIs.

## Test Commands And Results

### Targeted Evaluation Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_evaluation.py -q
```

Result:

```text
..                                                                       [100%]
2 passed in 0.32s
```

Evidence:

- `test_evaluation_reports_guardrail_conflict_and_context_metrics` proves the
  evaluator reports guardrail recall, conflict count, kept skills, and context
  tokens.
- `test_layered_eval_script_outputs_json` proves the benchmark script emits
  machine-readable JSON.

### Full Regression Suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
........................................................................ [ 67%]
..................................                                       [100%]
106 passed in 1.43s
```

Evidence:

- Existing adapter, metadata, history, layered compile, guardrail, conflict,
  archive, policy, lifecycle, authoring, feedback, and frontmatter tests still
  pass after adding evaluation support.

### Benchmark Smoke Test

Command:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/skills/rusty" "$tmp/skills/security"
cat > "$tmp/skills/rusty/SKILL.md" <<'EOF'
---
name: rusty
description: rust cargo helper
---
# rusty
EOF
cat > "$tmp/skills/security/SKILL.md" <<'EOF'
---
name: security
description: security guardrail
qm-layer: guardrail
qm-priority: 100
---
# security
EOF
QM_HOME="$tmp/home" python3 benchmark/layered_eval.py "$tmp/skills" \
  --intent "rust cargo" --cap 2
```

Result:

```json
{
  "archived_count": 0,
  "blocked_count": 0,
  "conflict_count": 0,
  "context_tokens": 13,
  "guardrail_recall": 1.0,
  "guardrails_kept": 1,
  "guardrails_total": 1,
  "intent": "rust cargo",
  "kept": 2,
  "saved_tokens": 0,
  "total_skills": 2
}
```

Evidence:

- The benchmark CLI can evaluate a corpus without installing Quartermaster.
- Guardrail recall and token/context metrics are emitted as stable JSON.

## Acceptance Criteria

| Criterion | Result | Evidence |
|---|---|---|
| Add deterministic metrics for guardrail recall and risky-action blocking. | Pass | Evaluation tests and JSON smoke output |
| Add conflict and archive visibility metrics. | Pass | Evaluation tests |
| Add context/token metrics. | Pass | Evaluation tests and JSON smoke output |
| Keep previous benchmark paths compatible. | Pass | Full regression suite |
| Existing tests still pass. | Pass | Full regression suite: `106 passed` |

## Decision

Phase 8 is verified as successful for deterministic local evaluation.

Live model/task-success benchmarking remains a separate external evaluation
track because it requires provider credentials and/or live agent runtimes.
