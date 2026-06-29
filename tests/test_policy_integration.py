import time

import pytest

from qm import archive, policy, store
from qm.cli import main
from qm.registry import ARCHIVED, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def test_policy_proposes_archive_for_long_hidden_skill(env):
    make_skill(env, "old", extra="disable-model-invocation: true\nuser-invocable: false")
    now = time.time()
    reg = Registry.load(skills_dir=env, last_used={"old": now - 120 * 86400})

    proposals = policy.propose(reg, archive_after_days=90, now=now)

    assert any(p.skill == "old" and p.action == "archive" for p in proposals)


def test_policy_proposes_restore_for_recently_used_archived_skill(env):
    make_skill(env, "old")
    main(["archive", "old", "--yes"])
    now = time.time()
    reg = Registry.load(
        skills_dir=env,
        last_used={"old": now - 1 * 86400},
        include_archived=True,
    )

    proposals = policy.propose(reg, demote_after_days=14, now=now)

    assert any(p.skill == "old" and p.action == "restore" for p in proposals)


def test_review_dry_run_reports_archive_proposal(env, capsys):
    make_skill(env, "old", extra="disable-model-invocation: true\nuser-invocable: false")
    store.record_usage("old", ts=time.time() - 120 * 86400)

    assert main(["review", "--archive-after", "90", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "archive" in out
    assert "old" in out


def test_review_yes_applies_archive_proposal(env):
    make_skill(env, "old", extra="disable-model-invocation: true\nuser-invocable: false")
    store.record_usage("old", ts=time.time() - 120 * 86400)

    assert main(["review", "--archive-after", "90", "--yes"]) == 0

    assert not (env / "old").exists()
    assert archive.read_index().get("old")
    hist = store.read_skill_history()["old"]
    assert hist["state"] == ARCHIVED
