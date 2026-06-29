import json

from benchmark import layered_eval
from qm.evaluation import evaluate
from qm.registry import Registry

from .helpers import make_skill


def test_evaluation_reports_guardrail_conflict_and_context_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "security",
        description="security guardrail",
        extra="qm-layer: guardrail\nqm-priority: 100",
    )
    make_skill(
        skills,
        "deploy-a",
        description="deploy service",
        extra="qm-layer: action\nqm-provides: deploy",
    )
    make_skill(
        skills,
        "deploy-b",
        description="deploy service",
        extra="qm-layer: action\nqm-provides: deploy",
    )

    reg = Registry.load(skills_dir=skills)
    result = evaluate(reg, "deploy service", cap=2)

    assert result.total_skills == 3
    assert result.kept == 2
    assert result.guardrails_total == 1
    assert result.guardrails_kept == 1
    assert result.guardrail_recall == 1.0
    assert result.conflict_count == 1
    assert result.context_tokens > 0


def test_layered_eval_script_outputs_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "rusty", description="rust cargo helper")

    assert layered_eval.main([str(skills), "--intent", "rust cargo"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["intent"] == "rust cargo"
    assert data["total_skills"] == 1
    assert data["kept"] == 1
