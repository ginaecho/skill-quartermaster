# Quartermaster Roadmap: Layered, Safety-First Skill Loadouts

This plan extends Quartermaster from a non-destructive lifecycle manager into a
layered skill orchestration system. The goal is to keep the active context small
while making the selected loadout safer, more coherent, and easier to restore.
It should be agent-agnostic: Claude Code is one supported runtime, not the only
one. The same lifecycle and loadout logic should work for Codex, GitHub Copilot
CLI, local VS Code/GitHub workflows, and future agent shells.

## Target Model

Quartermaster should compile a project or task intent into a structured loadout:

1. Safety and guardrail skills are selected first and have dominance over action
   skills.
2. Skills are grouped into layers so the agent receives policy, planning,
   domain, action, and tool guidance in a predictable order.
3. Conflicting skills are detected before activation.
4. Rarely used skills are demoted, hidden, and eventually archived without
   losing their metadata or restore path.
5. A persistent historical registry records skill usage, layer decisions,
   conflicts, archive locations, and project/task usefulness.
6. Runtime adapters translate the same compiled loadout into each agent's
   native format, hook model, and skill/tool discovery path.

The current `active -> demoted -> hidden -> deleted` ladder remains. We add
metadata, policy, and archive behavior around it rather than replacing it.

## Supported Runtimes

Quartermaster should separate its core logic from agent-specific packaging.

| Runtime | Role | Adapter responsibilities |
|---|---|---|
| Claude Code | Existing plugin/skill runtime | `.claude-plugin`, slash commands, skill frontmatter flags, PreToolUse hook |
| Codex | OpenAI/Codex coding agent runtime | Codex skill/plugin layout, local CLI wrapper, usage capture where available |
| GitHub Copilot CLI | Subscription CLI agent path | Command wrapper, prompt/loadout injection, usage/result logging |
| VS Code + GitHub local | IDE-local workflow | Workspace config, generated instructions, task integration, extension-friendly files |
| Generic command agent | Fallback for any CLI | stdin/stdout prompt wrapper, exported loadout manifest, best-effort telemetry |

Core modules must not assume Claude-specific directories or frontmatter flags.
They should operate on a normalized skill model and delegate filesystem layout,
activation semantics, and telemetry to adapters.

## Concepts To Add

### Layers

Initial layer taxonomy:

| Layer | Purpose | Examples |
|---|---|---|
| `guardrail` | Safety, security, privacy, compliance, repo rules | security review, secret handling, safe deploy |
| `planning` | Architecture, decomposition, review strategy | design review, test strategy |
| `domain` | Project/task-specific capabilities | FastAPI, React, Postgres, Terraform |
| `action` | Agent execution behaviors | edit workflow, refactor, run tests, create PR |
| `tool` | MCP/tool adapter usage | GitHub, browser, database, cloud API |
| `style` | User/repo conventions | formatting, tone, naming, documentation |

Layer ordering matters. `guardrail` and `style` should be loaded before skills
that cause external actions or code changes.

### Runtime Adapters

Agent-specific behavior should live behind a small adapter interface.

Adapter capabilities:

- discover skill roots
- read and write activation state
- expose a compiled loadout to the agent
- collect usage telemetry when possible
- install commands/hooks/instructions for that runtime
- restore archived skills into the correct runtime location

Initial adapters:

- `claude`: preserves current behavior for `.claude/skills`,
  `.claude-plugin`, slash commands, and `disable-model-invocation`.
- `codex`: exports Quartermaster instructions and loadout metadata into Codex
  skill/plugin-compatible locations.
- `copilot`: supports command-driven use through wrappers and loadout manifests.
- `vscode`: emits workspace-local files that VS Code/GitHub workflows can use.
- `generic`: works with any CLI through `QM_SKILLS_DIR` plus a generated
  loadout manifest.

### Priority

Each skill should receive a computed priority, not just a relevance score.

Suggested priority inputs:

- `layer_weight`: guardrails and style get high base weight.
- `intent_score`: match against project/task intent.
- `usage_score`: recent usage and successful historical use.
- `project_affinity`: usefulness in this repo or similar repos.
- `risk_score`: skills that can touch production, secrets, network, files, or
  external systems require stronger guardrail coverage.
- `probation_penalty`: newly authored skills can be active but should not
  displace proven guardrails.

Priority should be transparent in CLI output so users can understand why a skill
was selected.

### Guardrail Dominance

Guardrails are not just another matched skill. They define constraints.

Rules:

- A risky action/tool skill must not be selected without compatible guardrails.
- If a guardrail conflicts with an action skill, the guardrail wins.
- If two guardrails conflict, compilation should fail safe and ask for user
  resolution instead of guessing.
- Guardrail skills should be sticky: recent non-use alone should not demote
  them as aggressively as ordinary domain/action skills.

### Conflict Detection

Conflict detection should work in two stages:

- Static metadata conflicts declared by skill authors or Quartermaster.
- Heuristic conflicts inferred from names/descriptions until explicit metadata
  exists.

Examples:

- `conflicts_with: ["unsafe-deploy", "force-push"]`
- `requires_guardrails: ["secret-handling", "security-review"]`
- `provides: ["deploy"]`
- `risk_tags: ["network", "production", "secrets"]`

Compiler behavior:

- If two selected non-guardrail skills conflict, choose the higher-priority one
  and report the dropped skill.
- If an action/tool skill lacks required guardrails, auto-add guardrails when
  available.
- If required guardrails are missing, keep the action/tool skill demoted and
  report a blocked capability.

### Archived But Restorable Storage

`hidden` still leaves a skill in place but out of context. `archived` should
physically move a skill out of active skill roots while preserving a restore
record.

Proposed ladder:

`active -> demoted -> hidden -> archived -> deleted`

Archive behavior:

- Move `<skills_root>/<skill>` to `$QM_HOME/archive/<skill>/<timestamp>/`.
- Record original path, archive path, metadata, checksum, and reason.
- Keep a registry entry so `qm status --all` can still show archived skills.
- `qm restore <skill>` should restore from archive if the skill is absent from
  active roots.
- `qm delete` remains human-gated and should work on archived skills only with
  explicit confirmation.

Archive is not deletion. It is reversible storage reclamation and context
cleanup.

## Implementation Phases

### Phase 0: Runtime Abstraction

Make Quartermaster provider-neutral before adding richer orchestration rules.

Status: implemented and verified. Claude remains the default runtime; `codex`,
`copilot`, `vscode`, and `generic` adapters are selectable, provide
runtime-specific roots/state semantics, export loadout manifests, and write
workspace-local setup files through `qm runtime-setup`. Live telemetry from
external non-Claude products remains best-effort because those runtimes do not
share one common hook API.

Deliverables:

- Add `qm/adapters.py` or `qm/adapters/` with a minimal adapter protocol:
  - `name`
  - `default_roots()`
  - `discover()`
  - `read_state()`
  - `write_state()`
  - `expose_loadout()`
  - `record_usage_event()`
- Move Claude-specific assumptions out of core modules:
  - `.claude/skills`
  - `.claude-plugin`
  - `disable-model-invocation`
  - `user-invocable`
  - PreToolUse hook shape
- Add runtime selection:
  - `QM_RUNTIME=claude|codex|copilot|vscode|generic`
  - `qm --runtime <name> ...`
- Keep `claude` as the default adapter initially so existing behavior does not
  break.
- Add a generic exported loadout manifest, for example
  `$QM_HOME/loadouts/<project>.json`, usable by Codex, Copilot CLI, VS Code, and
  any command-line agent.

Acceptance criteria:

- Current Claude behavior still works through the `claude` adapter.
- `qm status` and `qm compile --dry-run` work with `--runtime generic`.
- Core scoring, policy, and history code no longer hard-code Claude-only paths.
- Tests cover adapter selection and default compatibility.

### Phase 1: Skill Metadata Model

Add a dependency-free metadata module, likely `qm/metadata.py`.

Status: implemented and verified. Metadata is optional, parsed without new
dependencies, attached to each registry `Skill`, inferred for existing skills,
and visible through `qm status --layers`.

Deliverables:

- Parse optional frontmatter keys:
  - `qm-layer`
  - `qm-priority`
  - `qm-tags`
  - `qm-risk`
  - `qm-provides`
  - `qm-requires`
  - `qm-requires-guardrails`
  - `qm-conflicts-with`
- Normalize metadata into a dataclass attached to each `Skill`.
- Infer default layer from explicit metadata first, then heuristics.
- Preserve frontmatter round-trip behavior.
- Add tests for parsing, defaults, malformed values, and compatibility with
  existing skills.

Acceptance criteria:

- Existing tests pass unchanged.
- Existing skills without new metadata still load.
- `qm status` can optionally show layer and priority metadata.

### Phase 2: Historical Dictionary

Extend local state from raw logs into a queryable skill history index.

Status: implemented and verified. `$QM_HOME/skills.json` records seen skills,
usage, selections, transitions, metadata, runtime, path, and useful intents;
`qm history <skill>` exposes the entry.

Deliverables:

- Add `history.json` or `skills.json` under `QM_HOME`.
- Record:
  - first seen
  - last seen
  - last used
  - usage count
  - selected count
  - demoted/hidden/archive counts
  - useful project/task intents
  - conflict notes
  - archive location if archived
- Update the index during registry load, usage hook, compile apply, transitions,
  archive, and restore.
- Add `qm history <skill>` to inspect one skill.

Acceptance criteria:

- The historical dictionary survives a skill being hidden or archived.
- `qm history <skill>` works for active, hidden, and archived skills.

### Phase 3: Layer-Aware Compiler

Replace the current flat keyword `compile_loadout` ranking with a layered plan.

Status: implemented and verified. Compile plans now group keep selections by
layer, compute transparent priority from intent/metadata/history, reserve room
for guardrail/style layers, report cap/off-intent drops, and export a runtime
loadout manifest through the selected adapter.

Deliverables:

- Add `LayeredCompilePlan` with selected skills grouped by layer.
- Keep a total cap plus optional per-layer caps.
- Always reserve room for guardrails/style before domain/action/tool skills.
- Score skills with relevance plus metadata and history.
- Print:
  - selected by layer
  - priority reasons
  - dropped due to cap
  - added guardrails
  - blocked risky skills
- Export the plan through the selected runtime adapter.
- Keep `--dry-run` and `--yes` behavior.

Acceptance criteria:

- `qm compile "<intent>" --dry-run` explains the loadout by layer.
- Guardrail skills are not displaced by many domain matches.
- Cap behavior remains predictable and tested.
- Runtime-specific output is generated only by adapters, not by the compiler.

### Phase 4: Guardrail Dominance Rules

Make safety constraints part of compilation and review policy.

Status: implemented and verified. Risky action/tool skills are blocked when
required guardrails are missing, available matching guardrails are auto-added,
lower-priority non-guardrails can be displaced to make room, and policy review
uses longer stale windows for guardrail skills.

Deliverables:

- Add a guardrail resolver:
  - detects risky selected skills
  - finds required guardrails
  - auto-includes available guardrails
  - blocks or demotes unsafe actions when required guardrails are absent
- Add policy exemptions or longer windows for guardrail demotion.
- Add CLI output that clearly distinguishes:
  - selected because relevant
  - selected because guardrail
  - blocked because missing guardrail

Acceptance criteria:

- Risky action/tool skills cannot become active without required guardrails.
- Guardrail conflicts fail safe.
- Review policy does not casually hide important guardrails.

### Phase 5: Conflict Detection

Add explicit and inferred conflict handling.

Status: implemented and verified. Explicit `qm-conflicts-with` and inferred
action/tool provider conflicts are detected; compile resolves non-guardrail
conflicts by priority, lets guardrails dominate non-guardrails, blocks
guardrail conflicts for user decision, and `qm conflicts` reports installed
conflicts.

Deliverables:

- Add `qm/conflicts.py`.
- Parse explicit conflicts from metadata.
- Infer basic conflicts from tags/risk/provides until richer metadata exists.
- Add conflict results to compile plans.
- Add `qm doctor` or `qm conflicts` to report installed skill conflicts.

Acceptance criteria:

- Compiler reports conflicts before applying a loadout.
- Non-guardrail conflicts are resolved by priority.
- Guardrail conflicts require user decision.
- Tests cover explicit conflict, inferred conflict, and no-conflict paths.

### Phase 6: Archive And Restore

Add reversible archived storage as a new lifecycle state.

Status: implemented and verified. `qm archive` moves skill directories to
`$QM_HOME/archive` with checksums and an index manifest, `qm status --all`
includes archived skills, `qm restore` restores archived skills
byte-identically, and archived deletion remains explicitly `--yes` gated.

Deliverables:

- Add `ARCHIVED` state in registry/report/history concepts.
- Add archive manifest under `QM_HOME/archive/index.json`.
- Implement:
  - `qm archive <skill>`
  - `qm restore <skill>` from archive
  - `qm status --all` including archived skills
  - `qm delete <skill> --yes` for archived skills
- Ensure archive moves preserve file contents and metadata.
- Compute checksums before and after archive/restore.

Acceptance criteria:

- Archive removes the skill from active roots but keeps it listed in history.
- Restore recreates the original skill directory byte-identically.
- Delete remains explicit and irreversible.
- Existing `demote`, `hide`, and `restore` behavior remains compatible.

### Phase 7: Policy Integration

Make review proposals use the new concepts.

Status: implemented and verified. Review policy proposes hidden-to-archive and
archived-to-restore transitions, applies archive/restore proposals through the
archive module, and preserves guardrail-aware stale windows.

Deliverables:

- Layer-aware stale rules:
  - guardrails have longer stale windows
  - action/tool skills can be demoted more aggressively
  - archived proposals happen only after long hidden periods
- Usage-aware revival:
  - if an archived skill is requested by name or intent, propose restore
  - if a demoted skill keeps being manually used, promote it
- Add proposal reasons that include layer and history.

Acceptance criteria:

- `qm review --dry-run` can propose archive, restore, demote, hide, promote, and
  graduate actions without applying them.
- Archive proposals are never destructive and remain reversible.

### Phase 8: Evaluation And Benchmarks

Update the benchmark suite to prove the richer compiler helps.

Status: implemented and verified for local deterministic metrics.
`qm.evaluation` and `benchmark/layered_eval.py` report guardrail recall,
blocked risky actions, conflict count, archived count, and token/context
metrics. Live model/task-success benchmarking remains outside this local
verification pass.

Deliverables:

- Add synthetic metadata to benchmark corpus or infer layers for it.
- Measure:
  - guardrail recall
  - risky-action blocking accuracy
  - conflict detection precision
  - targeted skill recall after archive
  - context savings with layered caps
- Add regression tests for previous headline claims.

Acceptance criteria:

- Layered compiler keeps or improves recall at cap 30.
- Guardrail skills have high recall even when not directly named.
- Archive/restore is byte-identical on sampled skills.

## CLI Surface Proposal

New or extended commands:

```bash
qm runtimes
qm status --layers
qm status --all
qm --runtime codex status
qm --runtime copilot compile "<intent>" --dry-run
qm compile "<intent>" --dry-run
qm compile "<intent>" --explain --yes
qm history <skill>
qm conflicts
qm archive <skill>
qm restore <skill>
```

Existing commands should continue working with their current meanings.

## Data Compatibility

Quartermaster should remain safe for existing skill folders.

Rules:

- New metadata keys are optional.
- No migration should rewrite skill files just to add metadata.
- Inferred metadata lives in the local history/index unless the user explicitly
  asks to write it into `SKILL.md`.
- Archive must record enough information to restore skills even if the user
  changes `QM_SKILLS_DIR` later.
- Runtime adapters must be additive. Adding Codex/Copilot/VS Code support must
  not remove or weaken the existing Claude plugin path.

## Suggested Build Order

Implement one phase at a time:

1. Runtime abstraction.
2. Metadata model.
3. Historical dictionary.
4. Layer-aware compiler.
5. Guardrail dominance.
6. Conflict detection.
7. Archive/restore.
8. Policy integration.
9. Benchmarks and docs.

This order keeps the foundation testable. Runtime abstraction comes first so
new concepts are implemented once in core logic instead of being baked into a
Claude-only path. Metadata and history are prerequisites for every later
feature; archive should wait until restore semantics and history are reliable.
