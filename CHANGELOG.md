# Changelog

All notable changes to Quartermaster. The project follows the phased roadmap
in the README.

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
