import time

import pytest

from qm import authoring, policy, store
from qm.registry import ACTIVE, DEMOTED, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def test_slugify():
    assert authoring.slugify("convert HEIC images to png") == "convert-heic-images-png"
    assert authoring.slugify("") == "new-skill"


def test_cluster_groups_similar_gaps(env):
    gaps = [
        {"text": "needed to convert heic images to png"},
        {"text": "convert heic photo into png format"},
        {"text": "tune a slow sql query"},
    ]
    reg = Registry.load(skills_dir=env)
    clusters = authoring.cluster_gaps(gaps, reg)
    # The two heic gaps should land together; sql on its own.
    assert any(c.count == 2 for c in clusters)
    assert any(c.count == 1 for c in clusters)


def test_propose_authoring_respects_threshold_and_existing(env):
    # An existing skill already covers sql tuning.
    make_skill(env, "sql-tuner", description="tune slow sql query performance")
    reg = Registry.load(skills_dir=env)
    gaps = [
        {"text": "convert heic images to png"},
        {"text": "convert heic photo to png"},
        {"text": "tune slow sql query"},
        {"text": "tune slow sql query again"},
    ]
    proposals = authoring.propose_authoring(reg, gaps, threshold=2)
    names = {p.cluster.key for p in proposals}
    # heic gap proposed (no skill covers it); sql gap suppressed (covered).
    assert any("heic" in k for k in names)
    assert not any("sql" in k for k in names)


def test_propose_authoring_below_threshold_is_silent(env):
    reg = Registry.load(skills_dir=env)
    gaps = [{"text": "convert heic to png"}]
    assert authoring.propose_authoring(reg, gaps, threshold=2) == []


def test_scaffold_creates_probationary_skill(env):
    path = authoring.scaffold(env, "heic-convert", "convert heic to png", brief="users need heic->png")
    assert path.exists()
    text = path.read_text()
    assert "name: heic-convert" in text
    assert "Probationary skill" in text
    # registered as probation in the overlay
    prob = store.read_probation()
    assert "heic-convert" in prob
    # appears as probationary in the registry
    reg = Registry.load(skills_dir=env, probation=store.read_probation())
    sk = reg.get("heic-convert")
    assert sk.state == ACTIVE
    assert sk.probation is True
    # admission logged
    assert any(e["to"] == "probationary" for e in store.read_audit())


def test_scaffold_refuses_duplicate(env):
    authoring.scaffold(env, "dup", "x")
    with pytest.raises(FileExistsError):
        authoring.scaffold(env, "dup", "x")


def test_graduate_clears_probation(env):
    authoring.scaffold(env, "newbie", "x")
    assert authoring.graduate("newbie") is True
    assert "newbie" not in store.read_probation()
    assert authoring.graduate("newbie") is False  # already cleared


def test_policy_graduates_used_probationary(env):
    now = time.time()
    authoring.scaffold(env, "tryme", "x", brief="b")
    store.set_probation("tryme", brief="b", ts=now)  # admitted at `now`
    store.record_usage("tryme", ts=now + 3600)       # used an hour later
    reg = Registry.load(skills_dir=env, last_used=store.last_used_map(), probation=store.read_probation())
    proposals = policy.propose(reg, now=now + 7200)
    assert any(p.skill == "tryme" and p.action == "graduate" for p in proposals)


def test_policy_demotes_expired_probationary(env):
    now = time.time()
    authoring.scaffold(env, "neglected", "x")
    # never used; backdate admission well past the probation window
    store.set_probation("neglected", ts=now - 30 * 86400)
    reg = Registry.load(skills_dir=env, probation=store.read_probation())
    proposals = policy.propose(reg, probation_days=14, now=now)
    assert any(p.skill == "neglected" and p.action == "demote" for p in proposals)
