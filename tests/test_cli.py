import pytest

from qm import store
from qm.cli import main
from qm.registry import ACTIVE, DEMOTED, HIDDEN, Registry

from .helpers import make_skill


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    return skills


def test_status_runs(env, capsys):
    make_skill(env, "alpha")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "0 deleted" in out


def test_demote_then_restore_via_cli(env, capsys):
    make_skill(env, "alpha")
    assert main(["demote", "alpha"]) == 0
    assert Registry.load(skills_dir=env).get("alpha").state == DEMOTED
    assert main(["restore", "alpha"]) == 0
    assert Registry.load(skills_dir=env).get("alpha").state == ACTIVE


def test_demote_unknown_skill(env, capsys):
    assert main(["demote", "ghost"]) == 2
    assert "No skill named" in capsys.readouterr().out


def test_delete_refuses_non_hidden(env, capsys):
    make_skill(env, "alpha")
    rc = main(["delete", "alpha", "--yes"])
    assert rc == 1
    assert "Refusing to delete" in capsys.readouterr().out
    # still on disk
    assert (env / "alpha" / "SKILL.md").exists()


def test_delete_requires_yes_even_when_hidden(env, capsys):
    make_skill(env, "alpha")
    main(["hide", "alpha"])
    rc = main(["delete", "alpha"])
    assert rc == 1
    assert "Re-run with --yes" in capsys.readouterr().out
    assert (env / "alpha" / "SKILL.md").exists()


def test_delete_hidden_with_yes(env, capsys):
    make_skill(env, "alpha")
    main(["hide", "alpha"])
    rc = main(["delete", "alpha", "--yes"])
    assert rc == 0
    assert not (env / "alpha").exists()
    # logged
    assert any(e["to"] == "deleted" for e in store.read_audit())


def test_compile_dry_run_changes_nothing(env, capsys):
    make_skill(env, "rusty", description="rust cargo helper")
    make_skill(env, "weird", description="unrelated")
    rc = main(["compile", "rust cargo project", "--dry-run"])
    assert rc == 0
    assert Registry.load(skills_dir=env).get("weird").state == ACTIVE


def test_compile_apply_with_yes(env):
    make_skill(env, "rusty", description="rust cargo helper")
    make_skill(env, "weird", description="totally unrelated topic")
    assert main(["compile", "rust cargo project", "--yes"]) == 0
    reg = Registry.load(skills_dir=env)
    assert reg.get("rusty").state == ACTIVE
    assert reg.get("weird").state == DEMOTED


def test_review_dry_run(env, capsys):
    import time
    make_skill(env, "stale")
    store.record_usage("stale", ts=time.time() - 60 * 86400)
    rc = main(["review", "--dry-run"])
    assert rc == 0
    assert "demote" in capsys.readouterr().out


def test_log_command(env, capsys):
    make_skill(env, "alpha")
    main(["demote", "alpha"])
    assert main(["log"]) == 0
    assert "alpha" in capsys.readouterr().out


def test_gap_and_gaps_flow(env, capsys):
    main(["gap", "convert", "heic", "images", "to", "png"])
    main(["gap", "convert", "heic", "photo", "to", "png"])
    capsys.readouterr()
    assert main(["gaps"]) == 0
    out = capsys.readouterr().out
    assert "heic" in out
    assert "author" in out


def test_author_creates_probationary_skill(env, capsys):
    rc = main(["author", "heic-convert", "--desc", "convert heic to png", "--yes"])
    assert rc == 0
    assert (env / "heic-convert" / "SKILL.md").exists()
    out = capsys.readouterr().out
    assert "probationary" in out.lower()
    assert "skill-creator" in out
    # shows up as probation in status
    capsys.readouterr()
    main(["status"])
    assert "prob" in capsys.readouterr().out


def test_author_refuses_duplicate(env, capsys):
    make_skill(env, "exists")
    rc = main(["author", "exists", "--yes"])
    assert rc == 1
    assert "already exists" in capsys.readouterr().out


def test_graduate_via_cli(env, capsys):
    main(["author", "tryme", "--yes"])
    capsys.readouterr()
    assert main(["graduate", "tryme"]) == 0
    assert "graduated" in capsys.readouterr().out
    assert main(["graduate", "tryme"]) == 0  # idempotent
    assert "not on probation" in capsys.readouterr().out


def test_feedback_capability_records_gap(env, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("QM_STYLE_FILE", str(tmp_path / "style.md"))
    rc = main(["feedback", "I", "needed", "to", "lint", "terraform", "but", "no", "skill", "matched"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "capability" in out


def test_feedback_demote_suggestion_then_apply(env, capsys):
    make_skill(env, "docx-writer", description="writes docx files")
    # suggestion only
    assert main(["feedback", "stop", "suggesting", "docx-writer"]) == 0
    assert Registry.load(skills_dir=env).get("docx-writer").state == ACTIVE
    # with --apply it acts
    assert main(["feedback", "stop", "suggesting", "docx-writer", "--apply"]) == 0
    assert Registry.load(skills_dir=env).get("docx-writer").state == DEMOTED
