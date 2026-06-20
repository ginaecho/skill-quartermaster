import time

import pytest

from qm import frontmatter, store, transitions
from qm.registry import ACTIVE, DEMOTED, HIDDEN, Registry, derive_state

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    return skills


def test_derive_state_from_flags(env):
    make_skill(env, "a")
    make_skill(env, "b", extra="disable-model-invocation: true")
    make_skill(env, "c", extra="disable-model-invocation: true\nuser-invocable: false")
    reg = Registry.load(skills_dir=env)
    assert reg.get("a").state == ACTIVE
    assert reg.get("b").state == DEMOTED
    assert reg.get("c").state == HIDDEN


def test_demote_hide_restore_roundtrip(env):
    make_skill(env, "a")
    reg = Registry.load(skills_dir=env)
    sk = reg.get("a")

    assert transitions.demote(sk) == ACTIVE
    fm = frontmatter.parse(sk.path.read_text())
    assert derive_state(fm) == DEMOTED
    assert fm.get("description") == "does a thing"  # untouched

    transitions.hide(sk)
    assert derive_state(frontmatter.parse(sk.path.read_text())) == HIDDEN

    transitions.restore(sk)
    fm = frontmatter.parse(sk.path.read_text())
    assert derive_state(fm) == ACTIVE
    assert fm.get("disable-model-invocation") is None
    assert fm.get("user-invocable") is None


def test_transition_is_logged(env):
    make_skill(env, "a")
    reg = Registry.load(skills_dir=env)
    transitions.demote(reg.get("a"), reason="testing")
    log = store.read_audit()
    assert len(log) == 1
    assert log[0]["skill"] == "a"
    assert log[0]["from"] == ACTIVE
    assert log[0]["to"] == DEMOTED
    assert log[0]["reason"] == "testing"


def test_noop_transition_writes_nothing(env):
    make_skill(env, "a")
    reg = Registry.load(skills_dir=env)
    sk = reg.get("a")
    assert transitions.activate(sk) == ACTIVE  # already active
    assert store.read_audit() == []


def test_registry_picks_first_root_on_name_clash(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    make_skill(r1, "dup", description="from r1")
    make_skill(r2, "dup", description="from r2")
    monkeypatch.setenv("QM_SKILLS_DIR", f"{r1}:{r2}")
    reg = Registry.load()
    assert reg.get("dup").description == "from r1"


def test_index_tokens_and_indexed_flag(env):
    make_skill(env, "a")
    make_skill(env, "b", extra="disable-model-invocation: true\nuser-invocable: false")
    reg = Registry.load(skills_dir=env)
    assert reg.get("a").indexed is True
    assert reg.get("b").indexed is False
    assert reg.get("a").index_tokens > 0
