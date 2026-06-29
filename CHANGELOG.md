# Changelog

All notable changes to Quartermaster. The project follows the phased roadmap
in the README.

## Unreleased — runtime adapters

- Added the first Phase 0 runtime adapter seam. `qm --runtime` and
  `QM_RUNTIME` now select between `claude`, `codex`, `copilot`, `vscode`, and
  `generic` adapters; `qm runtimes` lists them.
- Preserved Claude Code as the default runtime while moving root discovery and
  state derivation/writes behind adapter methods.
- Added generic non-Claude state handling through Quartermaster-owned
  `qm-state` frontmatter so future Codex/Copilot/VS Code packaging can share
  the same lifecycle core.
- Added the Phase 1 skill metadata model. Quartermaster now parses optional
  `qm-layer`, `qm-priority`, `qm-tags`, `qm-risk`, `qm-provides`,
  `qm-requires`, `qm-requires-guardrails`, and `qm-conflicts-with`
  frontmatter, attaches normalized metadata to registry entries, infers layers
  for existing skills, and exposes `qm status --layers`.
- Added the Phase 2 historical dictionary at `$QM_HOME/skills.json`. Registry
  discovery, usage telemetry, transitions, and compile selections now update a
  queryable per-skill history; `qm history <skill>` prints it.
- Added the Phase 3 layer-aware compiler. Compile plans now group selected
  skills by layer, compute transparent priority from intent/metadata/history,
  reserve room for guardrail/style skills, explain dropped skills, and export a
  runtime loadout manifest through the selected adapter.
- Added Phase 4 guardrail dominance. Risky action/tool skills are blocked
  unless required guardrails are present; matching guardrails are auto-added and
  can displace lower-priority non-guardrails. Policy review uses longer stale
  windows for guardrail skills.
- Added Phase 5 conflict detection. Quartermaster detects explicit
  `qm-conflicts-with` conflicts and inferred action/tool provider conflicts,
  resolves compile-time non-guardrail conflicts by priority, lets guardrails
  dominate non-guardrails, blocks conflicting guardrails for user decision, and
  exposes `qm conflicts`.
- Added Phase 6 archived-but-restorable storage. `qm archive <skill>` moves a
  skill to `$QM_HOME/archive`, records checksums and a manifest, `qm status
  --all` shows archived skills, `qm restore <skill>` restores byte-identically,
  and archived deletion remains `--yes` gated.
- Added Phase 7 policy integration. `qm review` now includes archived skills,
  can propose hidden-to-archive and archived-to-restore transitions, and applies
  archive/restore proposals through reversible archive storage.
- Added Phase 8 evaluation support. `qm.evaluation` and
  `benchmark/layered_eval.py` report guardrail recall, blocked count, conflict
  count, archived count, and context/token metrics for layered loadouts.
- Added Phase 9 trusted skill intake. `qm sources` lists curated public skill
  repositories to consider, and `qm intake <local_repo>` scans local checkouts
  without executing code, rejects suspicious candidates, scores high-value
  skills, and imports only accepted skills after explicit `--yes`.

## v0.5 — feedback loop

- `qm feedback "<gripe>"` routes a plain-language complaint to the right lever:
  style miss → always-on style file; capability miss → gap log; "stop
  suggesting X" / "I keep using X" → demote/promote suggestion for a named
  skill. Explicit phrases outweigh incidental topic words; ambiguous input is
  reported rather than guessed. Only local notes/gaps are auto-written.

## v1.0 (partial) — trust & polish

- `qm revert [-n N] [--skill X]` — one-click revert from the audit trail.
  Deletions and skill admissions are surfaced but never auto-undone (human-
  gated); reverts are themselves logged so the trail stays complete.
- Demoting/hiding a probationary skill now clears its probation overlay.
- `qm compile` refuses a too-vague intent that would demote the whole shelf.
- Marketplace + plugin manifests in place for one-command install.
- Not yet shipped: semantic-embedding compiler and a graphical dashboard
  (`qm status` is the textual dashboard).

## v0.4 — authoring arm

- `qm gap` / `qm gaps` record and cluster capability gaps (natural-language,
  with complaint-filler stripped); duplicates against existing skills are
  suppressed.
- `qm author <name>` scaffolds a probationary skill stub and hands a brief to
  `skill-creator` (it never writes skill content itself).
- `qm graduate <skill>` ends probation. Probation rules added to the policy
  engine (graduate-if-used, demote-if-expired).

## v0.3 — intent compiler

- `qm compile "<intent>"` builds a per-project active loadout by transparent
  keyword relevance, capped near the ~30-skill accuracy sweet spot.

## v0.2 — telemetry + policy

- PreToolUse hook records local-only skill usage.
- Policy engine proposes demote-if-unused / promote-if-used / hide; `qm review`
  batches proposals behind a single approval.

## v0 — lifecycle core

- Registry derives `active`/`demoted`/`hidden` state from skill frontmatter
  flags; round-trip-safe transitions; reversible audit log; `qm status` with
  the token-saved report. Deletion is the only destructive action and is
  human-gated.
