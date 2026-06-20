"""``qm`` command-line interface — the thin lifecycle tool.

Verbs (matching the README):

    qm status              show every skill, its state, last-used, token cost
    qm compile <intent>    propose an active loadout for this project
    qm review              show proposed demotions/promotions, approve them
    qm restore <skill>     bring a skill back to active
    qm demote <skill>      manual-only (out of auto-selection)
    qm hide <skill>        out of context entirely
    qm activate <skill>    alias of restore
    qm delete <skill>      human-gated removal from disk (requires --yes)
    qm log                 print the audit trail

Everything but ``delete`` is non-destructive and reversible. ``delete`` refuses
to run without an explicit confirmation and only on a long-hidden skill unless
forced.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

from . import authoring
from . import compile as compile_mod
from . import policy, report, store, transitions
from .registry import ACTIVE, DEMOTED, HIDDEN, Registry


def _load_registry(args) -> Registry:
    return Registry.load(
        skills_dir=getattr(args, "skills_dir", None),
        last_used=store.last_used_map(),
        probation=store.read_probation(),
    )


def _skills_root(args, reg: Registry) -> "object":
    """Best-effort target directory for newly authored skills."""
    import os
    from pathlib import Path

    explicit = getattr(args, "skills_dir", None)
    if explicit:
        return Path(explicit)
    env = os.environ.get("QM_SKILLS_DIR")
    if env:
        return Path(env.split(os.pathsep)[0]).expanduser()
    # Fall back to the project-local skills dir.
    return Path(".claude/skills")


def _print(msg: str = "") -> None:
    print(msg)


# --- commands ------------------------------------------------------------

def cmd_status(args) -> int:
    reg = _load_registry(args)
    _print(report.render_status(reg))
    return 0


def cmd_compile(args) -> int:
    reg = _load_registry(args)
    intent = " ".join(args.intent).strip()
    if not intent:
        _print("Provide a project intent, e.g.  qm compile \"a rust web API with sqlx\"")
        return 2
    plan = compile_mod.compile_loadout(reg, intent, cap=args.cap)

    _print(f"Intent: {intent}")
    _print(f"Loadout cap: {plan.cap}\n")
    _print(f"Keep active ({len(plan.keep)}):")
    for s in plan.keep:
        why = ", ".join(s.matched) if s.matched else "(kept to fill loadout)"
        _print(f"  ● {s.skill.name}  [score {s.score}: {why}]")
    if plan.drop:
        _print(f"\nDemote ({len(plan.drop)}):")
        for s in plan.drop:
            _print(f"  ◐ {s.skill.name}")

    if args.dry_run:
        _print("\n(dry run — nothing changed)")
        return 0
    if not args.yes and not _confirm("\nApply this loadout?"):
        _print("Aborted. Nothing changed.")
        return 1

    changed = 0
    for s in plan.keep:
        sk = reg.get(s.skill.name)
        if sk and sk.state != ACTIVE:
            transitions.activate(sk, reason="compile: matched intent")
            changed += 1
    for s in plan.drop:
        sk = reg.get(s.skill.name)
        if sk and sk.state == ACTIVE:
            transitions.demote(sk, reason="compile: off-intent")
            changed += 1
    _print(f"\nApplied. {changed} transition(s). Run `qm status` to see the loadout.")
    return 0


def cmd_review(args) -> int:
    reg = _load_registry(args)
    proposals = policy.propose(
        reg,
        demote_after_days=args.demote_after,
        hide_after_days=args.hide_after,
    )
    if not proposals:
        _print("No proposals. Your loadout looks well-tuned. ✓")
        return 0

    _print(f"{len(proposals)} proposal(s):\n")
    for i, p in enumerate(proposals, 1):
        _print(f"  {i}. {p.action:<7} {p.skill}  ({p.from_state} → {p.to_state})  — {p.reason}")

    if args.dry_run:
        _print("\n(dry run — nothing changed)")
        return 0
    if not args.yes and not _confirm("\nApprove all of the above?"):
        _print("Aborted. Nothing changed.")
        return 1

    applied = 0
    for p in proposals:
        sk = reg.get(p.skill)
        if not sk:
            continue
        if p.action == "graduate":
            authoring.graduate(p.skill)
        else:
            transitions.set_state(sk, p.to_state, reason=f"review: {p.reason}")
        applied += 1
    _print(f"\nApplied {applied} transition(s). All reversible via `qm restore <skill>`.")
    return 0


def cmd_gap(args) -> int:
    text = " ".join(args.text).strip()
    if not text:
        _print('Describe the gap, e.g.  qm gap "needed to convert HEIC images, no skill matched"')
        return 2
    store.record_gap(text, context=args.context or "")
    reg = _load_registry(args)
    proposals = authoring.propose_authoring(reg, threshold=args.threshold)
    _print(f"Recorded gap: {text}")
    hit = next((p for p in proposals if text in p.cluster.samples), None)
    if hit:
        _print(
            f"\nThis gap has now recurred enough to suggest a new skill: "
            f"{hit.suggested_name}.\nRun `qm gaps` to review, or "
            f'`qm author {hit.suggested_name}` to scaffold it.'
        )
    return 0


def cmd_gaps(args) -> int:
    reg = _load_registry(args)
    gaps = store.read_gaps()
    if not gaps:
        _print("No capability gaps recorded yet. Log one with `qm gap \"<what you needed>\"`.")
        return 0
    clusters = authoring.cluster_gaps(gaps, reg)
    proposals = {p.cluster.key: p for p in authoring.propose_authoring(reg, gaps, threshold=args.threshold)}

    _print(f"{len(clusters)} gap cluster(s):\n")
    for c in clusters:
        if c.matched_skill:
            note = f"covered by existing skill '{c.matched_skill}'"
        elif c.key in proposals:
            note = f"→ author '{proposals[c.key].suggested_name}'"
        else:
            note = f"below threshold ({c.count}/{args.threshold})"
        _print(f"  [{c.count}x] {c.key}  —  {note}")

    if proposals:
        _print(
            f"\n{len(proposals)} skill(s) recommended. Scaffold one with "
            f"`qm author <name>` (it'll be admitted on probation)."
        )
    return 0


def cmd_author(args) -> int:
    from pathlib import Path

    reg = _load_registry(args)
    gaps = store.read_gaps()
    proposals = authoring.propose_authoring(reg, gaps, threshold=args.threshold)

    # Resolve which proposal/brief this name corresponds to, if any.
    match = next((p for p in proposals if p.suggested_name == args.name), None)
    description = args.desc or (match.description if match else f"TODO: describe {args.name}.")
    brief = args.brief or (match.brief if match else "")

    root = Path(_skills_root(args, reg))
    if reg.get(args.name) is not None or (root / args.name).exists():
        _print(f"A skill named {args.name!r} already exists. Pick another name.")
        return 1

    if not args.yes:
        _print(f"Will scaffold a probationary skill at {root / args.name}/SKILL.md")
        _print(f"  description: {description}")
        if brief:
            _print(f"  brief:\n    " + brief.replace("\n", "\n    "))
        if not _confirm("\nCreate it?"):
            _print("Aborted. Nothing created.")
            return 1

    path = authoring.scaffold(root, args.name, description, brief=brief)
    _print(f"\nCreated {path} — admitted as active (probationary).")
    _print(
        "\nHand off to skill-creator to write the instructions:\n"
        f"  Use the `skill-creator` skill to fill in {path}\n"
        f"  based on this brief:\n\n{brief or '  (describe the capability here)'}\n"
    )
    _print(f"Once it proves useful, run `qm graduate {args.name}`.")
    return 0


def cmd_graduate(args) -> int:
    reg = _load_registry(args)
    sk = reg.get(args.skill)
    if not sk:
        _print(f"No skill named {args.skill!r}.")
        return 2
    if not sk.probation:
        _print(f"{sk.name} is not on probation. Nothing to do.")
        return 0
    authoring.graduate(sk.name)
    _print(f"{sk.name} graduated from probation. It is now a full active skill.")
    return 0


def _transition_cmd(args, target: str, verb: str) -> int:
    reg = _load_registry(args)
    sk = reg.get(args.skill)
    if not sk:
        _print(f"No skill named {args.skill!r}. Run `qm status` to list skills.")
        return 2
    prev = transitions.set_state(sk, target, reason=f"manual {verb}")
    if prev == target:
        _print(f"{sk.name} is already {target}. Nothing changed.")
    else:
        _print(f"{sk.name}: {prev} → {target}.")
    return 0


def cmd_restore(args) -> int:
    return _transition_cmd(args, ACTIVE, "restore")


def cmd_activate(args) -> int:
    return _transition_cmd(args, ACTIVE, "activate")


def cmd_demote(args) -> int:
    return _transition_cmd(args, DEMOTED, "demote")


def cmd_hide(args) -> int:
    return _transition_cmd(args, HIDDEN, "hide")


def cmd_delete(args) -> int:
    reg = _load_registry(args)
    sk = reg.get(args.skill)
    if not sk:
        _print(f"No skill named {args.skill!r}.")
        return 2

    if sk.state != HIDDEN and not args.force:
        _print(
            f"Refusing to delete {sk.name}: it is {sk.state}, not hidden.\n"
            f"Deletion is only proposed for long-hidden skills. Hide it first\n"
            f"(`qm hide {sk.name}`), or pass --force if you are certain."
        )
        return 1

    if not args.yes:
        _print(
            f"This will permanently remove {sk.dir} from disk.\n"
            f"This is the ONLY destructive action Quartermaster performs.\n"
            f"Re-run with --yes to confirm."
        )
        return 1

    import shutil

    store.record_transition(
        sk.name, sk.state, "deleted", path=sk.path, actor="qm", reason="human-approved delete"
    )
    shutil.rmtree(sk.dir)
    _print(f"Deleted {sk.name} ({sk.dir}). Logged to the audit trail.")
    return 0


def cmd_log(args) -> int:
    entries = store.read_audit()
    if not entries:
        _print("Audit log is empty.")
        return 0
    for e in entries[-args.limit:] if args.limit else entries:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["ts"]))
        reason = f"  — {e['reason']}" if e.get("reason") else ""
        _print(f"  {ts}  {e['skill']}: {e['from']} → {e['to']}{reason}")
    return 0


# --- helpers -------------------------------------------------------------

def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("y", "yes")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qm",
        description="Quartermaster — non-destructive skill lifecycle manager.",
    )
    p.add_argument(
        "--skills-dir",
        dest="skills_dir",
        default=None,
        help="Directory of skills to manage (overrides QM_SKILLS_DIR).",
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("status", help="show all skills, states, and token cost")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("compile", help="build an active loadout from a project intent")
    sp.add_argument("intent", nargs="*", help="plain-language description of the project")
    sp.add_argument("--cap", type=int, default=compile_mod.DEFAULT_CAP, help="max active skills")
    sp.add_argument("--yes", action="store_true", help="apply without prompting")
    sp.add_argument("--dry-run", action="store_true", help="show plan only")
    sp.set_defaults(func=cmd_compile)

    sp = sub.add_parser("review", help="show & approve proposed transitions")
    sp.add_argument("--demote-after", type=int, default=policy.DEMOTE_AFTER_DAYS)
    sp.add_argument("--hide-after", type=int, default=policy.HIDE_AFTER_DAYS)
    sp.add_argument("--yes", action="store_true", help="approve all without prompting")
    sp.add_argument("--dry-run", action="store_true", help="show proposals only")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("gap", help="record a capability gap (a need with no matching skill)")
    sp.add_argument("text", nargs="*", help="what you needed and couldn't find")
    sp.add_argument("--context", default="", help="optional context (project, task)")
    sp.add_argument("--threshold", type=int, default=authoring.GAP_THRESHOLD)
    sp.set_defaults(func=cmd_gap)

    sp = sub.add_parser("gaps", help="show clustered gaps and authoring recommendations")
    sp.add_argument("--threshold", type=int, default=authoring.GAP_THRESHOLD)
    sp.set_defaults(func=cmd_gaps)

    sp = sub.add_parser("author", help="scaffold a probationary skill (hand off to skill-creator)")
    sp.add_argument("name", help="skill name (kebab-case)")
    sp.add_argument("--desc", default="", help="one-line description")
    sp.add_argument("--brief", default="", help="brief for skill-creator")
    sp.add_argument("--threshold", type=int, default=authoring.GAP_THRESHOLD)
    sp.add_argument("--yes", action="store_true", help="create without prompting")
    sp.set_defaults(func=cmd_author)

    sp = sub.add_parser("graduate", help="end a skill's probation (proven useful)")
    sp.add_argument("skill", help="skill name")
    sp.set_defaults(func=cmd_graduate)

    for name, fn, helptext in [
        ("restore", cmd_restore, "bring a skill back to active"),
        ("activate", cmd_activate, "alias of restore"),
        ("demote", cmd_demote, "make manual-only (out of auto-selection)"),
        ("hide", cmd_hide, "remove from context entirely"),
    ]:
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("skill", help="skill name")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("delete", help="human-gated removal from disk")
    sp.add_argument("skill", help="skill name")
    sp.add_argument("--yes", action="store_true", help="confirm the deletion")
    sp.add_argument("--force", action="store_true", help="allow deleting a non-hidden skill")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("log", help="print the audit trail")
    sp.add_argument("--limit", type=int, default=0, help="show only the last N entries")
    sp.set_defaults(func=cmd_log)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
