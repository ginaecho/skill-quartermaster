# Skill Scout

Skill Scout semi-automates comparative evaluation of proposed skills. It
produces evidence for human governance; it does not claim field adoption and
does not change Quartermaster lifecycle state.

## Workflow

```text
candidate + current default + versioned suite
                    |
                    v
       pinned, randomized scout plan
                    |
                    v
 external isolated subscription-agent runners
                    |
                    v
       validated append-only trial rows
                    |
                    v
 internal evidence + blinded review packet
                    |
                    v
      3 independent evidence-bound votes
                    |
                    v
 approved / rejected / revise / blocked
```

The plan contains five arms when a current default is supplied:

| Arm | Purpose |
|---|---|
| No skill / natural | Absolute baseline |
| Current skill / forced | Existing workflow efficacy |
| Current skill / natural | Existing workflow selection behavior |
| Candidate / forced | Candidate efficacy when applicable |
| Candidate / natural | Candidate trigger precision and recall |

Every task is repeated under paired arms. Suites must contain both applicable
tasks and negative controls where the skill should not fire.

## Candidate contract

Scout reads the standard Agent Skills `name`, `description`, `license`, and
`compatibility` fields and supports these optional frontmatter fields:

```yaml
---
name: code-review
description: Reviews code when correctness or security findings are requested.
license: MIT
scout-author: team-or-owner
scout-non-goals: prose editing
scout-prerequisites: git
scout-compatible: copilot, claude, codex
scout-outputs: prioritized review findings
scout-risks: repository-read
---
```

Missing contract fields are preserved as limitations in the evidence pack.
Candidate identity combines a stable source/name ID with an immutable SHA-256
digest over all files in the skill directory. `latest` may be used for
discovery, but a real run should record the source commit in `--version`.

## Benchmark suite

See [`../benchmark/scout/suite.example.json`](../benchmark/scout/suite.example.json).

```json
{
  "id": "code-review",
  "version": "2026-08-25",
  "tasks": [
    {
      "id": "seeded-null-bug",
      "prompt": "Review the supplied change.",
      "rubric": "Identify the seeded null-handling regression.",
      "should_invoke": true,
      "tags": ["correctness"]
    },
    {
      "id": "write-release-note",
      "prompt": "Write a release note from these facts.",
      "rubric": "Complete the prose task without invoking code review.",
      "should_invoke": false,
      "tags": ["negative-control"]
    }
  ]
}
```

Keep representative examples public and use a rotating restricted holdout for
approval. Candidate authors must not be the sole authors or judges of the suite.

## Commands

Create a reproducible plan:

```bash
qm scout plan ./candidate-skill \
  --suite benchmark/scout/suite.example.json \
  --current-skill ./current-skill \
  --source https://github.com/example/skills \
  --version 4f30a9d \
  --current-source https://github.com/example/playbook \
  --current-version v2.1.0 \
  --repetitions 5 \
  --seed 7 \
  --out scout-plan.json
```

Execute all randomized jobs through an isolated runner:

```bash
qm scout run scout-plan.json \
  --out scout-trials.jsonl \
  --runner python \
  --runner-arg path/to/organization_runner.py
```

If a provider or worker fails, rerun with `--resume`. Scout preserves successful
rows and executes only missing or failed jobs.

Arguments are passed safely as an argument vector. Repeat `--runner-arg` for
each runner argument; use `--runner-arg=--model` when a value begins with a
dash. Scout does not invoke a shell.

Build the internal evidence and blinded packet:

```bash
qm scout report scout-plan.json scout-trials.jsonl \
  --out scout-evidence.json \
  --review-out scout-review-packet.json
```

Resolve the reviewer votes:

```bash
qm scout review scout-evidence.json reviewer-votes.json \
  --author team-or-owner \
  --out scout-decision.json
```

## Runner interface

Scout sends one JSON object to runner stdin for each job:

```json
{
  "schema_version": 1,
  "plan_id": "24-character-id",
  "candidate": {
    "name": "candidate-skill",
    "content_sha256": "...",
    "path": "pinned local path"
  },
  "current_skill": null,
  "job": {
    "job_id": "24-character-id",
    "task_id": "seeded-null-bug",
    "repetition": 1,
    "condition": "candidate-skill",
    "invocation_mode": "natural",
    "blind_label": "D",
    "prompt": "Review the supplied change.",
    "rubric": "Identify the seeded null-handling regression.",
    "should_invoke": true,
    "skill_path": "pinned local path"
  }
}
```

The runner returns exactly one JSON object on stdout:

```json
{
  "success": true,
  "quality": 0.9,
  "invoked": true,
  "tokens": 4200,
  "cost": 0.08,
  "output": "The agent output or a durable artifact reference.",
  "safety_flags": [],
  "error": ""
}
```

`quality` is bounded to `[0, 1]`; tokens and cost must be non-negative.
Wall-clock latency is measured by Scout rather than trusted from the runner.
Malformed, failed, oversized, and timed-out responses become explicit failed
trials instead of aborting the batch.

An organization runner should:

1. Create a fresh ephemeral workspace for every job.
2. Install no skill, the current skill, or the candidate according to the arm.
3. In `forced` mode, explicitly load the assigned skill. In `natural` mode,
   expose it normally and observe whether the agent selects it.
4. Run the same pinned agent/model/tool configuration and budget for all arms.
5. Capture native skill telemetry to populate `invoked`.
6. Apply deterministic task checks before an independent blind LLM judge.
7. Remove credentials and destroy the workspace after the job.

This seam supports many subscription-backed workers in parallel without
putting provider credentials or provider-specific orchestration in
Quartermaster.

### GitHub Copilot subscription runner

`benchmark/scout/copilot_runner.py` is a live adapter for GitHub Copilot CLI.
It creates a temporary workspace per job, installs only the assigned candidate
skill, uses the configured subscription model, and applies a deterministic JSON
rubric. Configure it with `SCOUT_MODEL`, `SCOUT_EFFORT`, and
`SCOUT_AGENT_TIMEOUT`.

Copilot CLI reports which skills are loaded but currently emits no distinct
activation event for these prompt-only jobs. The runner therefore records
natural invocation as `null` (unobserved), never as a guessed `true` or `false`.
Forced candidate jobs record invocation because the runner explicitly requests
the skill. Evidence profiles show the number of observed selection trials.

The real ASD-STE100 example suite is in
`benchmark/scout/cases/asd-ste100-suite.json`. Its live Copilot results and
the resulting non-approval decision are documented in
`benchmark/scout/cases/asd-ste100-results.md`.

## Review votes

Each vote is bound to the exact evidence ID:

```json
[
  {
    "evidence_id": "24-character-evidence-id",
    "reviewer": "reviewer-one",
    "decision": "accept",
    "rationale": "Improves correctness on the holdout without control regressions.",
    "safety_veto": false
  },
  {
    "evidence_id": "24-character-evidence-id",
    "reviewer": "reviewer-two",
    "decision": "accept",
    "rationale": "The quality lift and limitations are credible.",
    "safety_veto": false
  },
  {
    "evidence_id": "24-character-evidence-id",
    "reviewer": "reviewer-three",
    "decision": "revise",
    "rationale": "Clarify the supported runtime list.",
    "safety_veto": false
  }
]
```

Reviewers must be distinct, the candidate author is excluded, and every vote
requires a rationale. Two accepts produce `approved`; a safety veto produces
`blocked`. Votes never directly activate or archive a skill.

## Evidence and ranking

The internal evidence retains:

- Exact candidate/current content hashes and source versions
- Suite and plan versions
- Forced and natural profiles
- Paired quality deltas against no-skill and current-skill baselines
- Student-t 95% confidence intervals over task-level paired deltas
- Completion, invocation accuracy, within-task reliability, latency, tokens,
  cost, failures, and safety flags
- Automated recommendation, limitations, and every raw trial

The displayed score is secondary to the dimension profile. At catalog time,
call `EvidencePack.ranking_score_at(now)` to apply the configured 90-day
freshness half-life. Historical evidence remains unchanged.

The blinded packet intentionally excludes skill identities, arm mappings,
profiles, comparisons, and the automated recommendation. Reviewers score raw
outputs before the internal evidence reveals which arm produced them.

## Lifecycle recommendations

Scout can suggest `retain`, `re-evaluate`, `merge`, or `archive`, but the
suggestion is non-destructive. Archive requires aligned evidence: stale
evaluation, no observed usage, and domination by an approved alternative.
High-overlap skills with no meaningful quality difference may be proposed for
merge. Quartermaster's existing review, audit, archive, and restore paths own
all state changes.
