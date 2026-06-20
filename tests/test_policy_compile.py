import time

import pytest

from qm import policy
from qm.compile import compile_loadout
from qm.registry import ACTIVE, DEMOTED, HIDDEN, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    return skills


def test_propose_demotes_unused_active(env):
    make_skill(env, "stale")
    make_skill(env, "fresh")
    now = time.time()
    last_used = {"fresh": now - 1 * 86400, "stale": now - 40 * 86400}
    reg = Registry.load(skills_dir=env, last_used=last_used)
    proposals = policy.propose(reg, demote_after_days=14, now=now)
    actions = {(p.skill, p.action) for p in proposals}
    assert ("stale", "demote") in actions
    assert ("fresh", "demote") not in actions


def test_propose_promotes_used_demoted(env):
    make_skill(env, "comeback", extra="disable-model-invocation: true")
    now = time.time()
    reg = Registry.load(skills_dir=env, last_used={"comeback": now - 2 * 86400}, )
    proposals = policy.propose(reg, demote_after_days=14, now=now)
    assert any(p.skill == "comeback" and p.action == "promote" for p in proposals)


def test_propose_hides_long_unused_demoted(env):
    make_skill(env, "forgotten", extra="disable-model-invocation: true")
    now = time.time()
    reg = Registry.load(skills_dir=env, last_used={"forgotten": now - 60 * 86400})
    proposals = policy.propose(reg, demote_after_days=14, hide_after_days=30, now=now)
    assert any(p.skill == "forgotten" and p.action == "hide" for p in proposals)


def test_compile_keeps_matching_demotes_rest(env):
    make_skill(env, "rust-helper", description="rust cargo crate helper")
    make_skill(env, "python-helper", description="python pip helper")
    make_skill(env, "random", description="unrelated thing")
    reg = Registry.load(skills_dir=env)
    plan = compile_loadout(reg, "a rust cargo project", cap=30)
    kept = {s.skill.name for s in plan.keep}
    assert "rust-helper" in kept
    dropped = {s.skill.name for s in plan.drop}
    assert "random" in dropped


def test_compile_respects_cap(env):
    for i in range(5):
        make_skill(env, f"s{i}", description="rust cargo helper")
    reg = Registry.load(skills_dir=env)
    plan = compile_loadout(reg, "rust cargo", cap=2)
    assert len(plan.keep) == 2
    assert len(plan.drop) == 3
