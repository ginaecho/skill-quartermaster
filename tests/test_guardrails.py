import time

from qm import policy
from qm.cli import main
from qm.compile import compile_loadout
from qm.registry import Registry

from .helpers import make_skill


def test_risky_action_without_required_guardrail_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "deploy",
        description="deploy production service",
        extra="qm-layer: action\nqm-risk: production\nqm-requires-guardrails: change-review",
    )

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "deploy production", cap=5)

    assert "deploy" not in {s.skill.name for s in plan.keep}
    assert any("missing guardrail" in item for item in plan.blocked)


def test_required_guardrail_is_auto_added_and_can_displace_lower_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "deploy",
        description="deploy production service",
        extra="qm-layer: action\nqm-risk: production\nqm-requires-guardrails: change-review",
    )
    make_skill(
        skills,
        "change-review",
        description="review changes",
        extra="qm-layer: guardrail\nqm-provides: change-review",
    )
    make_skill(skills, "helper", description="deploy production helper")

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "deploy production", cap=2)

    kept = {s.skill.name for s in plan.keep}
    assert "deploy" in kept
    assert "change-review" in kept
    assert len(plan.keep) == 2
    assert any(s.skill.name == "change-review" for s in plan.added_guardrails)


def test_compile_cli_reports_blocked_guardrail_gap(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(
        skills,
        "deploy",
        description="deploy production service",
        extra="qm-layer: action\nqm-risk: production\nqm-requires-guardrails: change-review",
    )

    assert main(["compile", "deploy production", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Blocked:" in out
    assert "missing guardrail" in out


def test_guardrail_policy_uses_longer_stale_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "normal", description="normal helper")
    make_skill(skills, "security", description="security helper", extra="qm-layer: guardrail")
    now = time.time()
    last_used = {
        "normal": now - 30 * 86400,
        "security": now - 30 * 86400,
    }

    reg = Registry.load(skills_dir=skills, last_used=last_used)
    proposals = policy.propose(reg, demote_after_days=14, now=now)
    actions = {(p.skill, p.action) for p in proposals}

    assert ("normal", "demote") in actions
    assert ("security", "demote") not in actions
