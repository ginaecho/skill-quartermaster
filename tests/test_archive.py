import pytest
from pathlib import Path

from qm import archive, store
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


def test_archive_moves_skill_and_records_manifest(env):
    make_skill(env, "alpha")
    before = archive.checksum_dir(env / "alpha")

    assert main(["archive", "alpha", "--yes"]) == 0

    idx = archive.read_index()
    assert "alpha" in idx
    assert not (env / "alpha").exists()
    assert idx["alpha"]["checksum"] == before
    assert idx["alpha"]["archive_path"]
    assert any(e["to"] == ARCHIVED for e in store.read_audit())


def test_restore_from_archive_is_byte_identical(env):
    make_skill(env, "alpha")
    before = archive.checksum_dir(env / "alpha")
    main(["archive", "alpha", "--yes"])

    assert main(["restore", "alpha"]) == 0

    assert (env / "alpha" / "SKILL.md").exists()
    assert archive.checksum_dir(env / "alpha") == before
    assert "alpha" not in archive.read_index()


def test_status_all_includes_archived_skill(env, capsys):
    make_skill(env, "alpha")
    main(["archive", "alpha", "--yes"])
    capsys.readouterr()

    assert main(["status", "--all"]) == 0

    out = capsys.readouterr().out
    assert "alpha" in out
    assert "archived" in out


def test_delete_archived_requires_yes(env, capsys):
    make_skill(env, "alpha")
    main(["archive", "alpha", "--yes"])
    capsys.readouterr()

    assert main(["delete", "alpha"]) == 1
    assert "Re-run with --yes" in capsys.readouterr().out
    assert archive.read_index().get("alpha")


def test_delete_archived_with_yes_removes_archive(env):
    make_skill(env, "alpha")
    main(["archive", "alpha", "--yes"])
    archived_path = archive.read_index()["alpha"]["archive_path"]

    assert main(["delete", "alpha", "--yes"]) == 0

    assert not archive.read_index().get("alpha")
    assert not Path(archived_path).exists()
    assert any(e["to"] == "deleted" for e in store.read_audit())


def test_archived_history_survives_hidden_from_active_roots(env):
    make_skill(env, "alpha", extra="qm-layer: action")
    Registry.load(skills_dir=env)
    main(["archive", "alpha", "--yes"])

    hist = store.read_skill_history()["alpha"]

    assert hist["state"] == ARCHIVED
    assert hist["archive_path"]
    assert hist["metadata"]["layer"] == "action"
