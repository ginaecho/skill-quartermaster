import pytest

from qm import adapters
from qm.cli import main
from qm.registry import DEMOTED, HIDDEN, Registry

from .helpers import make_skill


def test_default_runtime_is_claude():
    assert adapters.get().name == "claude"


def test_unknown_runtime_is_rejected():
    with pytest.raises(adapters.AdapterError):
        adapters.get("ghost")


def test_registry_uses_runtime_from_environment(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_RUNTIME", "generic")
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(skills, "parked", extra="qm-state: hidden")

    reg = Registry.load()

    assert reg.get("parked").runtime == "generic"
    assert reg.get("parked").state == HIDDEN


def test_generic_transition_writes_qm_state(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(skills, "alpha")

    assert main(["--runtime", "generic", "demote", "alpha"]) == 0

    text = (skills / "alpha" / "SKILL.md").read_text(encoding="utf-8")
    reg = Registry.load(skills_dir=skills, runtime="generic")
    assert "qm-state: demoted" in text
    assert "disable-model-invocation" not in text
    assert reg.get("alpha").state == DEMOTED


def test_generic_restore_writes_explicit_active_state(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(skills, "alpha", extra="qm-state: demoted")

    assert main(["--runtime", "generic", "restore", "alpha"]) == 0

    text = (skills / "alpha" / "SKILL.md").read_text(encoding="utf-8")
    reg = Registry.load(skills_dir=skills, runtime="generic")
    assert "qm-state: active" in text
    assert reg.get("alpha").state == "active"


def test_claude_runtime_keeps_existing_frontmatter_flags(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(skills, "alpha")

    assert main(["demote", "alpha"]) == 0

    text = (skills / "alpha" / "SKILL.md").read_text(encoding="utf-8")
    reg = Registry.load(skills_dir=skills)
    assert "disable-model-invocation: true" in text
    assert "qm-state" not in text
    assert reg.get("alpha").state == DEMOTED


def test_runtimes_command_lists_supported_adapters(capsys):
    assert main(["runtimes"]) == 0
    out = capsys.readouterr().out
    for name in ("claude", "codex", "copilot", "generic", "vscode"):
        assert name in out


def test_runtime_setup_writes_codex_files(tmp_path):
    assert main(["runtime-setup", "codex", "--root", str(tmp_path)]) == 0

    assert (tmp_path / ".codex" / "quartermaster.md").exists()
    assert (tmp_path / ".quartermaster" / "codex-runtime.json").exists()
    assert (tmp_path / ".codex" / "skills").is_dir()
    text = (tmp_path / ".codex" / "quartermaster.md").read_text(encoding="utf-8")
    assert "qm --runtime codex" in text


def test_runtime_setup_all_writes_each_runtime(capsys, tmp_path):
    assert main(["runtime-setup", "--all", "--root", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    for name in ("claude", "codex", "copilot", "generic", "vscode"):
        assert f"{name}: wrote" in out
    assert (tmp_path / ".vscode" / "quartermaster.instructions.md").exists()
    assert (tmp_path / ".github" / "copilot" / "quartermaster.md").exists()
