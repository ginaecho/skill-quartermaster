---
name: quartermaster
description: Manage the lifecycle of installed coding-agent skills — list their state, compile layered safety-first loadouts, demote/hide/archive unused skills to save context, restore them, inspect history/conflicts, author skills for recurring gaps, and (only with explicit approval) delete. Use when the user wants to curate active skills, reduce context cost, manage guardrails, or restore archived capabilities.
---

# Quartermaster

Quartermaster is a **non-destructive** lifecycle manager for coding-agent skills.
It moves skills along a tiered ladder based on real usage and **never removes
anything from disk without explicit human approval**.

Use the bundled `qm` CLI for all operations. It uses runtime adapters for
Claude Code, Codex, Copilot CLI, VS Code, and generic command agents; logs every
change to a reversible audit trail; and prints the token-saved number.

## The state ladder

| State | In context? | Auto-loadable? | User can invoke? | On disk? | Frontmatter |
|---|---|---|---|---|---|
| **active** | yes (indexed) | yes | yes | yes | (no flags) |
| **demoted** | yes (indexed) | no | yes (manual) | yes | `disable-model-invocation: true` |
| **hidden** | no | no | no | yes | `+ user-invocable: false` |
| **archived** | no | no | no | yes, outside active roots | archive manifest |
| **deleted** | no | — | — | **no** | (file removed — human-gated only) |

Demote, hide, and archive are safe and reversible. **Delete is the only
destructive action and requires explicit `--yes` confirmation.**

## Running the CLI

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" <command>
# or, if bin/ is on PATH:
qm <command>
```

## Commands

- `qm runtimes` — list supported runtime adapters.
- `qm runtime-setup [runtime] [--all]` — write workspace-local setup files for
  Claude, Codex, Copilot CLI, VS Code, or generic command agents.
- `qm status [--layers] [--all]` — table of every skill, state, last-used date,
  token cost, optional metadata layer/priority, and optional archived skills.
- `qm compile "<project intent>"` — propose an active loadout matched to the
  project. Shows layered keep/demote/block decisions, guardrails, conflicts,
  and a loadout manifest path when applied.
- `qm review` — show proposed demotions/promotions/hides/archives/restores and
  approve them in one batch.
- `qm restore <skill>` / `qm activate <skill>` — bring a skill back to active,
  including from archive.
- `qm demote <skill>` — take a skill out of auto-selection (manual-only).
- `qm hide <skill>` — remove a skill from context entirely.
- `qm archive <skill> --yes` — move a skill out of active roots into reversible
  archive storage.
- `qm delete <skill> --yes` — permanently remove a (hidden) skill. **Destructive.**
- `qm revert [-n N] [--skill X]` — undo the last N automatic changes (one-click
  revert). Skips deletions/admissions, which stay human-gated.
- `qm history <skill>` — inspect historical usage, selection, state, and
  metadata for a skill.
- `qm conflicts` — report explicit and inferred skill conflicts.
- `qm sources` — list curated external public skill sources to consider.
- `qm intake <local_repo> --dry-run` — scan a local external skill repo without
  executing code; `--yes` imports only accepted high-value candidates.
- `qm log` — print the audit trail of every transition.

### Authoring arm (the capability-gap loop)

- `qm gap "<what you needed>"` — record a capability gap: a need with no
  matching skill. When the same gap recurs and nothing on the shelf covers it,
  Quartermaster recommends authoring a new skill.
- `qm gaps` — show clustered gaps and which ones warrant a new skill.
- `qm author <name> [--desc ...] [--brief ...]` — scaffold a new skill and admit
  it as **active, probationary** (on trial). This writes a stub only.
- `qm graduate <skill>` — end a skill's probation once it has proven useful.

### Feedback (plain-language complaints)

- `qm feedback "<what's off>"` — route a natural-language complaint to the right
  lever. A *style* miss is appended to the always-on style file; a *capability*
  miss is recorded as a gap (feeding the authoring arm); "stop suggesting X" /
  "I keep using X" become demote/promote suggestions for a named skill. Only the
  local style note and gap log are written automatically — skill moves are
  suggested unless you pass `--apply`.

## Probation

A newly authored skill is admitted **probationary**: it is `active` and usable
immediately, but on trial. `qm review` proposes graduating it if it gets used,
or demoting it if it sits unused past the probation window. `qm status` marks
probationary skills with `◉ prob`.

## How to behave when using this skill

1. **Default to non-destructive verbs.** Reach for `demote`, `hide`, `compile`,
   `archive`, and `review`. These are always safe.
2. **Never run `qm delete` on your own initiative.** Only delete when the user
   explicitly asks to permanently remove a specific skill, and surface that it
   is irreversible before doing so. Pass `--yes` only after the user confirms.
3. **Show the numbers.** After a lifecycle change, run `qm status` so the user
   sees the updated loadout and token savings.
4. **Apply in batches with approval.** For `compile` and `review`, present the
   proposed plan first; apply only after the user agrees (or pass `--yes` when
   they've already said go).
5. **Reassure on reversibility.** Every non-delete change is undone with
   `qm restore <skill>`; mention this when you demote, hide, or archive
   something.
6. **Author through skill-creator.** When `qm gaps` recommends a new skill (or
   the user asks for one), run `qm author <name>` to create the probationary
   stub, then invoke the **`skill-creator`** skill to write the actual
   instructions into the generated `SKILL.md`. `qm author` only scaffolds — it
   never writes the skill's content itself. Leave the skill probationary until
   the user confirms it works, then `qm graduate <name>`.
7. **Turn complaints into action.** When the user gripes in plain language
   ("this isn't matching my style", "I keep needing X", "stop suggesting Y"),
   run `qm feedback "<their words>"`. Apply the style note / gap automatically,
   but confirm before moving a skill (or pass `--apply` once they agree).
8. **Undo is one command.** Any automatic change can be reversed with
   `qm revert` (last change) or `qm restore <skill>`. Offer it freely.
9. **Respect guardrails.** If `qm compile` reports a blocked risky skill or a
   guardrail conflict, do not force the action. Explain the missing guardrail or
   conflict and ask the user how to resolve it.
10. **Treat external repos as untrusted.** Use `qm sources` to suggest candidate
    repos, ask the user to clone one, run `qm intake <path> --dry-run`, and only
    import with `--yes` after accepted candidates are reviewed.

## Notes

- Telemetry is local-only (under `~/.quartermaster/`, or `$QM_HOME`). Nothing is
  sent over the network.
- To manage a specific skills directory, pass `--skills-dir <path>` or set
  `QM_SKILLS_DIR`.
- To select an agent runtime, pass `--runtime claude|codex|copilot|vscode|generic`
  or set `QM_RUNTIME`. Claude remains the default adapter.
- To prepare workspace-local runtime files, run `qm runtime-setup <runtime>` or
  `qm runtime-setup --all`.
