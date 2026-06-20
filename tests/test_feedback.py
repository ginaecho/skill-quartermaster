import pytest

from qm import feedback, store
from qm.registry import ACTIVE, DEMOTED, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    monkeypatch.setenv("QM_STYLE_FILE", str(tmp_path / "style.md"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def _reg(env):
    return Registry.load(skills_dir=env)


def test_classify_style(env):
    sig = feedback.classify("this isn't matching my code style and naming conventions", _reg(env))
    assert sig.kind == "style"


def test_classify_capability(env):
    sig = feedback.classify("I keep needing to convert HEIC and no skill handles it", _reg(env))
    assert sig.kind == "capability"


def test_classify_demote_named_skill(env):
    make_skill(env, "docx-writer", description="writes docx files")
    sig = feedback.classify("please stop suggesting the docx-writer skill, it's noisy", _reg(env))
    assert sig.kind == "demote"
    assert sig.skill == "docx-writer"


def test_classify_promote_named_skill(env):
    make_skill(env, "rust-helper", description="rust cargo helper")
    sig = feedback.classify("I keep using the rust-helper, bring it back to active", _reg(env))
    assert sig.kind == "promote"
    assert sig.skill == "rust-helper"


def test_classify_ambiguous(env):
    sig = feedback.classify("hello there", _reg(env))
    assert sig.kind == "ambiguous"


def test_capability_phrase_outweighs_incidental_style_word(env):
    # "lint" is a style-ish word, but "needed to ... no skill" is a clear
    # capability request — the explicit phrases must win the tie.
    sig = feedback.classify("needed to lint terraform and no skill handled it", _reg(env))
    assert sig.kind == "capability"


def test_find_named_skill_by_word(env):
    make_skill(env, "docx-writer", description="writes docx files")
    assert feedback.find_named_skill("the docx thing keeps firing", _reg(env)) == "docx-writer"


def test_ingest_style_writes_file(env):
    res = feedback.ingest("prefer concise comments and consistent formatting", _reg(env))
    assert res.signal.kind == "style"
    assert "concise comments" in store.read_style()


def test_ingest_capability_records_gap(env):
    res = feedback.ingest("I needed to lint terraform but nothing handles it", _reg(env))
    assert res.signal.kind == "capability"
    gaps = store.read_gaps()
    assert any("terraform" in g["text"] for g in gaps)


def test_ingest_demote_is_suggestion_only(env):
    make_skill(env, "docx-writer", description="writes docx files")
    res = feedback.ingest("stop suggesting docx-writer", _reg(env))
    assert res.signal.kind == "demote"
    # ingest does not move the skill itself
    assert Registry.load(skills_dir=env).get("docx-writer").state == ACTIVE
    assert "qm demote docx-writer" in res.follow_up
