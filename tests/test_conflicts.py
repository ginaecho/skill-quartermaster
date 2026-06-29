from qm import conflicts
from qm.cli import main
from qm.compile import compile_loadout
from qm.registry import Registry

from .helpers import make_skill


def test_explicit_conflict_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "safe", extra="qm-conflicts-with: unsafe")
    make_skill(skills, "unsafe")

    reg = Registry.load(skills_dir=skills)
    found = conflicts.registry_conflicts(reg)

    assert len(found) == 1
    assert found[0].left == "safe"
    assert found[0].right == "unsafe"


def test_inferred_action_provider_conflict_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "deploy-a", extra="qm-layer: action\nqm-provides: deploy")
    make_skill(skills, "deploy-b", extra="qm-layer: action\nqm-provides: deploy")

    reg = Registry.load(skills_dir=skills)
    found = conflicts.registry_conflicts(reg)

    assert any("both provide deploy" in c.reason for c in found)


def test_compile_drops_lower_priority_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "deploy-a",
        description="deploy service",
        extra="qm-layer: action\nqm-provides: deploy\nqm-priority: 50",
    )
    make_skill(
        skills,
        "deploy-b",
        description="deploy service",
        extra="qm-layer: action\nqm-provides: deploy",
    )

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "deploy service", cap=5)

    assert "deploy-a" in {s.skill.name for s in plan.keep}
    assert "deploy-b" not in {s.skill.name for s in plan.keep}
    assert any("deploy-b dropped due to conflict" in item for item in plan.blocked)


def test_guardrail_conflict_blocks_both_for_user_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "policy-a",
        description="security policy",
        extra="qm-layer: guardrail\nqm-priority: 100\nqm-conflicts-with: policy-b",
    )
    make_skill(
        skills,
        "policy-b",
        description="security policy",
        extra="qm-layer: guardrail\nqm-priority: 90",
    )

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "security policy", cap=5)

    kept = {s.skill.name for s in plan.keep}
    assert "policy-a" not in kept
    assert "policy-b" not in kept
    assert any("guardrail conflict needs user decision" in item for item in plan.blocked)


def test_conflicts_command_reports_conflicts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(skills, "safe", extra="qm-conflicts-with: unsafe")
    make_skill(skills, "unsafe")

    assert main(["conflicts"]) == 0

    out = capsys.readouterr().out
    assert "conflict(s)" in out
    assert "safe" in out
    assert "unsafe" in out
