---
name: quartermaster
description: Manage the lifecycle of installed Claude Code skills — list their state, compile a per-project loadout, demote/hide unused skills to save context, restore them, and (only with explicit approval) delete. Use when the user wants to see installed skills, reduce skill clutter or context cost, turn a skill off without deleting it, or curate which skills are active for a project.
---

# Quartermaster

Quartermaster is a **non-destructive** lifecycle manager for Claude Code skills.
It moves skills along a tiered ladder based on real usage and **never removes
anything from disk without explicit human approval**.

Use the bundled `qm` CLI for all operations. It edits each skill's frontmatter
flags, logs every change to a reversible audit trail, and prints the
token-saved number.

## The state ladder

| State | In context? | Auto-loadable? | User can invoke? | On disk? | Frontmatter |
|---|---|---|---|---|---|
| **active** | yes (indexed) | yes | yes | yes | (no flags) |
| **demoted** | yes (indexed) | no | yes (manual) | yes | `disable-model-invocation: true` |
| **hidden** | no | no | no | yes | `+ user-invocable: false` |
| **deleted** | no | — | — | **no** | (file removed — human-gated only) |

Demote and hide are safe and reversible. **Delete is the only destructive
action and requires explicit `--yes` confirmation.**

## Running the CLI

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" <command>
# or, if bin/ is on PATH:
qm <command>
```

## Commands

- `qm status` — table of every skill, its state, last-used date, and token cost,
  plus the headline `N skills → M loaded → ~Xk tokens saved → 0 deleted`.
- `qm compile "<project intent>"` — propose an active loadout matched to the
  project, demoting off-intent skills. Shows the plan and asks before applying.
- `qm review` — show the policy engine's proposed demotions/promotions/hides and
  approve them in one batch.
- `qm restore <skill>` / `qm activate <skill>` — bring a skill back to active.
- `qm demote <skill>` — take a skill out of auto-selection (manual-only).
- `qm hide <skill>` — remove a skill from context entirely.
- `qm delete <skill> --yes` — permanently remove a (hidden) skill. **Destructive.**
- `qm log` — print the audit trail of every transition.

## How to behave when using this skill

1. **Default to non-destructive verbs.** Reach for `demote`, `hide`, `compile`,
   and `review`. These are always safe.
2. **Never run `qm delete` on your own initiative.** Only delete when the user
   explicitly asks to permanently remove a specific skill, and surface that it
   is irreversible before doing so. Pass `--yes` only after the user confirms.
3. **Show the numbers.** After a lifecycle change, run `qm status` so the user
   sees the updated loadout and token savings.
4. **Apply in batches with approval.** For `compile` and `review`, present the
   proposed plan first; apply only after the user agrees (or pass `--yes` when
   they've already said go).
5. **Reassure on reversibility.** Every non-delete change is undone with
   `qm restore <skill>`; mention this when you demote or hide something.

## Notes

- Telemetry is local-only (under `~/.quartermaster/`, or `$QM_HOME`). Nothing is
  sent over the network.
- To manage a specific skills directory, pass `--skills-dir <path>` or set
  `QM_SKILLS_DIR`. By default it scans `.claude/skills/` and `~/.claude/skills/`.
