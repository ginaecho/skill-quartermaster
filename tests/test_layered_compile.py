import json

import pytest

from qm import store
from qm.cli import main
from qm.compile import compile_loadout
from qm.registry import Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def test_layered_compile_reserves_guardrail_before_domain_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "security-review",
        description="security guardrail",
        extra="qm-layer: guardrail\nqm-priority: 100",
    )
    for i in range(4):
        make_skill(skills, f"rust-{i}", description="rust cargo helper")

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "rust cargo project", cap=3)

    kept = {s.skill.name for s in plan.keep}
    assert "security-review" in kept
    assert len(plan.keep) == 3
    assert plan.by_layer["guardrail"][0].skill.name == "security-review"
    assert plan.added_guardrails[0].skill.name == "security-review"


def test_layered_compile_uses_metadata_and_history_in_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "plain", description="rust cargo helper")
    make_skill(skills, "favored", description="rust cargo helper", extra="qm-priority: 20")
    store.record_usage("plain")
    store.record_usage("plain")

    reg = Registry.load(skills_dir=skills)
    plan = compile_loadout(reg, "rust cargo", cap=2)

    assert plan.keep[0].skill.name == "favored"
    assert plan.keep[0].priority > plan.keep[1].priority


def test_compile_dry_run_explains_layers(env, capsys):
    make_skill(env, "security-review", description="security helper", extra="qm-layer: guardrail\nqm-priority: 100")
    make_skill(env, "rusty", description="rust cargo helper")

    assert main(["compile", "rust cargo", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "[guardrail]" in out
    assert "priority" in out
    assert "Added guardrails" in out


def test_compile_apply_exports_runtime_manifest(env, tmp_path, monkeypatch, capsys):
    make_skill(env, "rusty", description="rust cargo helper")

    assert main(["--runtime", "generic", "compile", "rust cargo", "--yes"]) == 0

    out = capsys.readouterr().out
    assert "Loadout manifest:" in out
    manifests = list((tmp_path / "qmhome" / "loadouts").glob("*.json"))
    assert manifests
    data = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert data["runtime"] == "generic"
    assert data["keep"][0]["name"] == "rusty"
