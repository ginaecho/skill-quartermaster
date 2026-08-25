# Live Skill Scout case: ASD-STE100

This case validates the Skill Scout workflow with a public skill and a live
subscription agent. It is not sufficient evidence to approve or reject the
skill for general use.

## Inputs

| Input | Pinned value |
|---|---|
| Candidate | [`danyuchn/asd-ste100-skill`](https://github.com/danyuchn/asd-ste100-skill) |
| Commit | `d5ce157870cf9c41efd1d6e836706a2be3c7b9da` |
| Candidate content SHA-256 | `4722fbf99277...` |
| Suite | `asd-ste100-agent-clarity@2026-08-25` |
| Agent | GitHub Copilot CLI |
| Model | `gpt-5-mini`, low reasoning effort |
| Repetitions | 2 per task and arm |
| Tasks | 2 applicable rewrite tasks and 1 marketing negative control |
| Jobs | 18 |
| Evidence ID | `4ea64c3d871776ee1850509d` |

The run used the no-skill natural arm and candidate forced/natural arms. No
current organizational default was supplied.

## Results

| Arm | Completion | Mean quality | Mean latency | Mean tokens |
|---|---:|---:|---:|---:|
| No skill / natural | 100% | 0.823 | 43.3 s | 15,687 |
| Candidate / forced | 100% | 0.877 | 50.1 s | 19,654 |
| Candidate / natural | 100% | 0.872 | 34.9 s | 15,817 |

| Comparison | Quality delta | 95% CI | Latency delta | Token delta |
|---|---:|---:|---:|---:|
| Candidate forced vs no skill | +0.054 | -0.437 to +0.545 | +6.9 s | +3,967 |
| Candidate natural vs no skill | +0.049 | -0.065 to +0.163 | -8.3 s | +130 |

Task-level mean quality:

| Task | No skill | Candidate forced | Candidate natural |
|---|---:|---:|---:|
| Preserve ambiguity and modality in an error | 0.833 | 0.722 | 0.889 |
| Rewrite a dense inter-agent instruction | 0.636 | 0.909 | 0.727 |
| Marketing negative control | 1.000 | 1.000 | 1.000 |

## Decision

**Automated recommendation: `do-not-advance`.**

The directional mean lift is positive, but both confidence intervals include
zero. Two repetitions across three tasks are enough to verify the pipeline, not
enough to establish reliable improvement. A qualification run should expand to
at least 10–20 tasks with five paired repetitions and a restricted holdout.

Natural invocation is **unobserved**, not assumed. Copilot CLI reported that the
skill was loaded but emitted no distinct skill-activation event for these
prompt-only jobs. The evidence therefore does not claim trigger precision or
recall. A runtime with native activation telemetry is required for that metric.

## What the case changed

The first attempted batch exposed two runner defects before any conclusion was
accepted:

1. Windows decoded Copilot output with CP-1252 instead of UTF-8.
2. Multiline prompt arguments were truncated, and silent output contained
   progress narration.

The runner now uses UTF-8 explicitly, sends each request through a workspace
file, parses only the final `assistant.message` JSON event, records subscription
token usage, and supports resumable failed-job execution. The invalid batches
were overwritten and are not cited as evidence.

Raw plans, outputs, internal evidence, and blinded review packets remain local
under `runs/2026-08-25_ste100_live/`; `runs/` is intentionally ignored because
artifacts contain machine-local paths and full model outputs.
