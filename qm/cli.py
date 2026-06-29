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
from pathlib import Path
from typing import List, Optional

from . import adapters
from . import archive as archive_mod
from . import authoring
from . import compile as compile_mod
from . import conflicts as conflicts_mod
from . import feedback as feedback_mod
from . import history
from . import intake
from . import policy, report, store, transitions
from .registry import ACTIVE, DEMOTED, HIDDEN, Registry


def _load_registry(args) -> Registry:
    return Registry.load(
        skills_dir=getattr(args, "skills_dir", None),
        last_used=store.last_used_map(),
        probation=store.read_probation(),
        runtime=getattr(args, "runtime", None),
        include_archived=getattr(args, "all", False),
    )


def _skills_root(args, reg: Registry) -> "object":
    """Best-effort target directory for newly authored skills."""
    from pathlib import Path

    explicit = getattr(args, "skills_dir", None)
    if explicit:
        return Path(explicit)
    adapter = adapters.get(getattr(args, "runtime", None))
    roots = adapters.resolve_roots(adapter=adapter)
    return roots[0] if roots else Path(".quartermaster/skills")


def _print(msg: str = "") -> None:
    print(msg)


# --- commands ------------------------------------------------------------

def cmd_status(args) -> int:
    reg = _load_registry(args)
    _print(report.render_status(reg, show_layers=getattr(args, "layers", False)))
    return 0


def cmd_archive(args) -> int:
    reg = _load_registry(args)
    sk = reg.get(args.skill)
    if not sk:
        _print(f"No skill named {args.skill!r}. Run `qm status` to list skills.")
        return 2
    if sk.state == "archived":
        _print(f"{sk.name} is already archived.")
        return 0
    if not args.yes and not _confirm(f"Archive {sk.name}?"):
        _print("Aborted. Nothing changed.")
        return 1
    entry = archive_mod.archive_skill(sk, reason="manual archive")
    _print(f"{sk.name}: {sk.state} → archived.")
    _print(f"Archive path: {entry['archive_path']}")
    _print("Restore with `qm restore {}`.".format(sk.name))
    return 0


def cmd_runtimes(args) -> int:
    active = adapters.get(getattr(args, "runtime", None)).name
    _print("Available runtimes:")
    for adapter in adapters.all_adapters():
        marker = "*" if adapter.name == active else " "
        roots = ", ".join(str(p) for p in adapter.default_roots)
        _print(f"  {marker} {adapter.name:<8} {adapter.description}")
        _print(f"      roots: {roots}")
    return 0


def cmd_runtime_setup(args) -> int:
    selected = adapters.all_adapters() if args.all else [adapters.get(args.runtime_name or getattr(args, "runtime", None))]
    for adapter in selected:
        paths = adapter.setup(root=args.root)
        _print(f"{adapter.name}: wrote {len(paths)} path(s)")
        for path in paths:
            _print(f"  {path}")
    return 0


def cmd_compile(args) -> int:
    reg = _load_registry(args)
    intent = " ".join(args.intent).strip()
    if not intent:
        _print("Provide a project intent, e.g.  qm compile \"a rust web API with sqlx\"")
        return 2
    plan = compile_mod.compile_loadout(reg, intent, cap=args.cap)

    # Safety: a too-vague intent (e.g. only stop-words) matches nothing and
    # would demote the whole shelf. Refuse rather than nuke the loadout.
    if len(reg) > 0 and not any(s.score > 0 for s in plan.scored):
        _print(
            f"Intent {intent!r} matched no skills, so this would demote all "
            f"{len(reg)} of them.\nRefusing — give a more specific intent "
            f"(mention languages, tools, or task types)."
        )
        return 1

    _print(f"Intent: {intent}")
    _print(f"Loadout cap: {plan.cap}\n")
    _print(f"Keep active ({len(plan.keep)}):")
    for layer, items in plan.by_layer.items():
        if not items:
            continue
        _print(f"  [{layer}]")
        for s in items:
            why = "; ".join(s.reasons) if s.reasons else "(kept to fill loadout)"
            _print(f"    ● {s.skill.name}  [score {s.score}, priority {s.priority}: {why}]")
    if plan.added_guardrails:
        _print("\nAdded guardrails:")
        for s in plan.added_guardrails:
            _print(f"  + {s.skill.name}  [priority {s.priority}]")
    if plan.blocked:
        _print("\nBlocked:")
        for item in plan.blocked:
            _print(f"  ! {item}")
    if plan.drop:
        _print(f"\nDemote ({len(plan.drop)}):")
        for s in plan.drop:
            reason = "cap" if s in plan.dropped_due_cap else "off-intent"
            _print(f"  ◐ {s.skill.name}  [{reason}, layer {s.layer}, priority {s.priority}]")

    if args.dry_run:
        _print("\n(dry run — nothing changed)")
        return 0
    if not args.yes and not _confirm("\nApply this loadout?"):
        _print("Aborted. Nothing changed.")
        return 1

    changed = 0
    for s in plan.keep:
        store.note_skill_selected(s.skill.name, intent=intent)
        sk = reg.get(s.skill.name)
        if sk and sk.state != ACTIVE:
            transitions.activate(sk, reason="compile: matched intent")
            changed += 1
    for s in plan.drop:
        sk = reg.get(s.skill.name)
        if sk and sk.state == ACTIVE:
            transitions.demote(sk, reason="compile: off-intent")
            changed += 1
    manifest = adapters.get(getattr(args, "runtime", None)).expose_loadout(plan, intent=intent)
    if manifest:
        _print(f"\nLoadout manifest: {manifest}")
    _print(f"\nApplied. {changed} transition(s). Run `qm status` to see the loadout.")
    return 0


def cmd_review(args) -> int:
    args.all = True
    reg = _load_registry(args)
    proposals = policy.propose(
        reg,
        demote_after_days=args.demote_after,
        hide_after_days=args.hide_after,
        archive_after_days=args.archive_after,
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
        elif p.action == "archive":
            archive_mod.archive_skill(sk, reason=f"review: {p.reason}")
        elif p.action == "restore" and p.from_state == "archived":
            archive_mod.restore_skill(p.skill, target_root=_skills_root(args, reg))
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


def cmd_feedback(args) -> int:
    reg = _load_registry(args)
    text = " ".join(args.text).strip()
    if not text:
        _print('Tell me what is off, e.g.  qm feedback "this isn\'t matching my code style"')
        return 2
    result = feedback_mod.ingest(text, reg)
    sig = result.signal
    _print(f"Classified as: {sig.kind}" + (f" ({sig.skill})" if sig.skill else ""))
    _print(f"→ {result.applied}")

    # Auto-apply only the safe, local levers; suggest the rest.
    if sig.kind in ("style", "capability"):
        if result.follow_up:
            _print(f"\nNext: {result.follow_up}")
        return 0

    if sig.kind in ("demote", "promote") and sig.skill:
        if args.apply:
            sk = reg.get(sig.skill)
            target = DEMOTED if sig.kind == "demote" else ACTIVE
            transitions.set_state(sk, target, reason=f"feedback: {text}")
            _print(f"Applied: {sig.skill} → {target}.")
        else:
            _print(f"\nSuggested: {result.follow_up}   (re-run with --apply to do it now)")
        return 0

    if result.follow_up:
        _print(f"\n{result.follow_up}")
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
    reg = _load_registry(args)
    if reg.get(args.skill) is None:
        root = _skills_root(args, reg)
        restored = archive_mod.restore_skill(args.skill, target_root=root)
        if restored:
            _print(f"{args.skill}: archived → active.")
            _print(f"Restored to {restored}.")
            return 0
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
        archived = archive_mod.read_index().get(args.skill)
        if archived:
            if not args.yes:
                _print(
                    f"This will permanently remove archived skill {args.skill} from disk.\n"
                    f"Re-run with --yes to confirm."
                )
                return 1
            if archive_mod.delete_archived(args.skill):
                _print(f"Deleted archived skill {args.skill}. Logged to the audit trail.")
                return 0
        _print(f"No skill named {args.skill!r}.")
        return 2

    if sk.state == "archived":
        if not args.yes:
            _print(
                f"This will permanently remove archived skill {sk.name} from disk.\n"
                f"Re-run with --yes to confirm."
            )
            return 1
        if archive_mod.delete_archived(sk.name):
            _print(f"Deleted archived skill {sk.name}. Logged to the audit trail.")
            return 0
        _print(f"No archived copy found for {sk.name!r}.")
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


def cmd_revert(args) -> int:
    reg = _load_registry(args)
    plans = history.plan_revert(reg, limit=args.n, skill=args.skill)
    if not plans:
        _print("Nothing to revert — the audit trail has no reversible changes.")
        return 0

    _print("Would revert:")
    actionable = [p for p in plans if p.target not in ("(blocked)", "(missing)")]
    for p in plans:
        flag = "" if p in actionable else "  [skipped]"
        _print(f"  {p.describe}{flag}")

    if not actionable:
        _print("\nNone of these can be auto-reverted (deletions/admissions are human-gated).")
        return 1
    if args.dry_run:
        _print("\n(dry run — nothing changed)")
        return 0
    if not args.yes and not _confirm("\nApply these reverts?"):
        _print("Aborted. Nothing changed.")
        return 1

    done = 0
    for p in actionable:
        if history.apply_revert(reg, p):
            done += 1
    _print(f"\nReverted {done} change(s).")
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


def cmd_history(args) -> int:
    entries = store.read_skill_history()
    entry = entries.get(args.skill)
    if not entry:
        _print(f"No history for skill {args.skill!r}.")
        return 2

    _print(f"History for {args.skill}:")
    for key in (
        "state",
        "path",
        "runtime",
        "first_seen",
        "last_seen",
        "last_used",
        "usage_count",
        "selected_count",
        "demoted_count",
        "hidden_count",
        "archive_count",
        "archive_path",
    ):
        value = entry.get(key)
        if key.endswith("_seen") or key == "last_used":
            value = _fmt_ts(value)
        _print(f"  {key}: {value if value not in (None, '') else '-'}")

    metadata = entry.get("metadata") or {}
    if metadata:
        _print("  metadata:")
        for key in ("layer", "priority", "tags", "risk", "provides", "requires", "requires_guardrails", "conflicts_with"):
            _print(f"    {key}: {metadata.get(key, '-')}")

    intents = entry.get("useful_intents") or []
    if intents:
        _print("  useful_intents:")
        for intent in intents:
            _print(f"    - {intent}")
    conflicts = entry.get("conflict_notes") or []
    if conflicts:
        _print("  conflict_notes:")
        for note in conflicts:
            _print(f"    - {note}")
    return 0


def cmd_conflicts(args) -> int:
    reg = _load_registry(args)
    found = conflicts_mod.registry_conflicts(reg)
    if not found:
        _print("No conflicts detected.")
        return 0
    _print(f"{len(found)} conflict(s):")
    for c in found:
        _print(f"  ! {c.left} ↔ {c.right}  — {c.reason}")
    return 1 if args.strict else 0


def cmd_sources(args) -> int:
    _print("Curated external skill sources:")
    for source in intake.curated_sources():
        _print(f"  {source.name} [{source.trust}]")
        _print(f"    {source.url}")
        _print(f"    {source.rationale}")
    _print("\nClone externally, inspect if desired, then run `qm intake <path> --dry-run`.")
    return 0


def cmd_intake(args) -> int:
    candidates = intake.scan(args.source)
    if not candidates:
        _print(f"No SKILL.md files found under {args.source}.")
        return 1

    accepted = [c for c in candidates if c.accepted]
    _print(f"Scanned {len(candidates)} candidate skill(s).")
    _print(f"Accepted by safety/value gate: {len(accepted)}\n")
    for c in candidates[: args.limit]:
        status = "accept" if c.accepted else "reject"
        risks = ", ".join(c.risk_flags) if c.risk_flags else "-"
        _print(
            f"  {status:<6} {c.name:<28} layer={c.layer:<9} "
            f"value={c.value_score:<2} risks={risks}"
        )

    if args.dry_run:
        _print("\n(dry run — nothing imported)")
        return 0
    if not args.yes:
        _print("\nRe-run with --yes to import accepted skills.")
        return 1

    root = args.import_to or _skills_root(args, Registry([]))
    copied = intake.import_candidates(candidates, root, limit=args.limit)
    _print(f"\nImported {len(copied)} skill(s) to {root}:")
    for path in copied:
        _print(f"  {path}")
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


def _fmt_ts(value) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))


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
    p.add_argument(
        "--runtime",
        choices=adapters.names(),
        default=None,
        help="Agent runtime adapter (default: QM_RUNTIME or claude).",
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("runtimes", help="list supported agent runtime adapters")
    sp.set_defaults(func=cmd_runtimes)

    sp = sub.add_parser("runtime-setup", help="write local setup files for a runtime adapter")
    sp.add_argument("runtime_name", nargs="?", choices=adapters.names(), help="runtime to set up")
    sp.add_argument("--all", action="store_true", help="set up every runtime adapter")
    sp.add_argument("--root", type=Path, default=Path("."), help="workspace root to write setup files into")
    sp.set_defaults(func=cmd_runtime_setup)

    sp = sub.add_parser("status", help="show all skills, states, and token cost")
    sp.add_argument("--layers", action="store_true", help="show metadata layer and priority")
    sp.add_argument("--all", action="store_true", help="include archived skills")
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
    sp.add_argument("--archive-after", type=int, default=policy.ARCHIVE_AFTER_DAYS)
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

    sp = sub.add_parser("feedback", help="route a plain-language complaint to the right lever")
    sp.add_argument("text", nargs="*", help="what's off, in plain language")
    sp.add_argument("--apply", action="store_true", help="apply a suggested promote/demote immediately")
    sp.set_defaults(func=cmd_feedback)

    for name, fn, helptext in [
        ("restore", cmd_restore, "bring a skill back to active"),
        ("activate", cmd_activate, "alias of restore"),
        ("demote", cmd_demote, "make manual-only (out of auto-selection)"),
        ("hide", cmd_hide, "remove from context entirely"),
    ]:
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("skill", help="skill name")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("archive", help="move a hidden/unused skill to reversible archive storage")
    sp.add_argument("skill", help="skill name")
    sp.add_argument("--yes", action="store_true", help="archive without prompting")
    sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("delete", help="human-gated removal from disk")
    sp.add_argument("skill", help="skill name")
    sp.add_argument("--yes", action="store_true", help="confirm the deletion")
    sp.add_argument("--force", action="store_true", help="allow deleting a non-hidden skill")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("revert", help="undo recent automatic changes (one-click revert)")
    sp.add_argument("-n", type=int, default=1, help="how many recent changes to revert")
    sp.add_argument("--skill", default=None, help="revert only this skill's most recent change")
    sp.add_argument("--yes", action="store_true", help="apply without prompting")
    sp.add_argument("--dry-run", action="store_true", help="show what would be reverted")
    sp.set_defaults(func=cmd_revert)

    sp = sub.add_parser("log", help="print the audit trail")
    sp.add_argument("--limit", type=int, default=0, help="show only the last N entries")
    sp.set_defaults(func=cmd_log)

    sp = sub.add_parser("history", help="show historical dictionary entry for a skill")
    sp.add_argument("skill", help="skill name")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("conflicts", help="report installed skill conflicts")
    sp.add_argument("--strict", action="store_true", help="exit non-zero when conflicts are found")
    sp.set_defaults(func=cmd_conflicts)

    sp = sub.add_parser("sources", help="list curated external skill source repositories")
    sp.set_defaults(func=cmd_sources)

    sp = sub.add_parser("intake", help="scan and optionally import safe, high-value external skills")
    sp.add_argument("source", type=Path, help="local repo/directory to scan")
    sp.add_argument("--limit", type=int, default=10, help="max candidates to show/import")
    sp.add_argument("--import-to", type=Path, default=None, help="target skill root for imports")
    sp.add_argument("--dry-run", action="store_true", help="scan only")
    sp.add_argument("--yes", action="store_true", help="import accepted skills")
    sp.set_defaults(func=cmd_intake)

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
