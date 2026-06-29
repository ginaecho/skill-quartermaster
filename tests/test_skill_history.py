import time

import pytest

from qm import store
from qm.cli import main
from qm.registry import Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def test_registry_load_records_skill_seen(env):
    make_skill(env, "alpha", description="security helper", extra="qm-layer: guardrail")

    Registry.load(skills_dir=env)
    hist = store.read_skill_history()["alpha"]

    assert hist["path"].endswith("alpha/SKILL.md")
    assert hist["runtime"] == "claude"
    assert hist["state"] == "active"
    assert hist["metadata"]["layer"] == "guardrail"
    assert hist["first_seen"] <= hist["last_seen"]


def test_usage_updates_historical_dictionary(env):
    make_skill(env, "alpha")
    Registry.load(skills_dir=env)
    store.record_usage("alpha", ts=time.time())
    store.record_usage("alpha", ts=time.time() + 1)

    hist = store.read_skill_history()["alpha"]

    assert hist["usage_count"] == 2
    assert hist["last_used"] is not None


def test_transition_updates_counts_and_state(env):
    make_skill(env, "alpha")
    main(["demote", "alpha"])
    main(["hide", "alpha"])

    hist = store.read_skill_history()["alpha"]

    assert hist["state"] == "hidden"
    assert hist["demoted_count"] == 1
    assert hist["hidden_count"] == 1


def test_compile_records_selected_intent(env):
    make_skill(env, "rusty", description="rust cargo helper")
    make_skill(env, "other", description="unrelated topic")

    assert main(["compile", "rust cargo project", "--yes"]) == 0
    hist = store.read_skill_history()["rusty"]

    assert hist["selected_count"] == 1
    assert "rust cargo project" in hist["useful_intents"]


def test_history_command_prints_entry(env, capsys):
    make_skill(env, "alpha", extra="qm-layer: action\nqm-priority: 10")
    Registry.load(skills_dir=env)

    assert main(["history", "alpha"]) == 0

    out = capsys.readouterr().out
    assert "History for alpha" in out
    assert "selected_count" in out
    assert "metadata" in out
    assert "action" in out


def test_history_command_unknown_skill(env, capsys):
    assert main(["history", "ghost"]) == 2
    assert "No history" in capsys.readouterr().out
