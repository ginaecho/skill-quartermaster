import pytest

from qm import authoring, history, store, transitions
from qm.registry import ACTIVE, DEMOTED, HIDDEN, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def _reg(env):
    return Registry.load(skills_dir=env, probation=store.read_probation())


def test_revert_undoes_last_transition(env):
    make_skill(env, "a")
    transitions.demote(_reg(env).get("a"))
    assert _reg(env).get("a").state == DEMOTED

    plans = history.plan_revert(_reg(env), limit=1)
    assert len(plans) == 1 and plans[0].target == ACTIVE
    assert history.apply_revert(_reg(env), plans[0]) is True
    assert _reg(env).get("a").state == ACTIVE


def test_revert_is_itself_logged_and_not_re_reverted(env):
    make_skill(env, "a")
    transitions.demote(_reg(env).get("a"))
    history.apply_revert(_reg(env), history.plan_revert(_reg(env))[0])
    # The revert entry must not become a revert target itself.
    plans = history.plan_revert(_reg(env), limit=5)
    targets = [p for p in plans if p.target not in ("(blocked)", "(missing)")]
    # Only the original demote remains reversible (now it's active again, so
    # reverting it would set demoted) — but the revert entry is skipped.
    assert all(not str(p.entry.get("reason", "")).startswith("revert of") for p in plans)


def test_revert_skips_deletion(env):
    make_skill(env, "a")
    sk = _reg(env).get("a")
    transitions.hide(sk)
    store.record_transition("a", HIDDEN, "deleted", reason="human-approved delete")
    import shutil
    shutil.rmtree(sk.dir)

    plans = history.plan_revert(_reg(env), limit=1)
    assert plans[0].target == "(blocked)"
    assert history.apply_revert(_reg(env), plans[0]) is False


def test_revert_blocks_admission(env):
    authoring.scaffold(env, "newbie", "x")  # logs (absent) -> probationary
    plans = history.plan_revert(_reg(env), limit=1)
    assert plans[0].target == "(blocked)"


def test_revert_by_skill(env):
    make_skill(env, "a")
    make_skill(env, "b")
    transitions.demote(_reg(env).get("a"))
    transitions.demote(_reg(env).get("b"))
    plans = history.plan_revert(_reg(env), limit=1, skill="a")
    assert plans[0].skill == "a"
    history.apply_revert(_reg(env), plans[0])
    assert _reg(env).get("a").state == ACTIVE
    assert _reg(env).get("b").state == DEMOTED  # untouched


def test_demote_clears_probation_overlay(env):
    authoring.scaffold(env, "p", "x")
    assert _reg(env).get("p").probation is True
    transitions.demote(_reg(env).get("p"))
    # failed probation -> overlay cleared, reads as a plain demoted skill
    assert "p" not in store.read_probation()
    sk = _reg(env).get("p")
    assert sk.state == DEMOTED
    assert sk.probation is False
