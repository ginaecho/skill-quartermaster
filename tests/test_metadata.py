from qm import frontmatter, metadata
from qm.cli import main
from qm.registry import Registry

from .helpers import make_skill


def test_parse_explicit_metadata_fields():
    fm = frontmatter.parse(
        "---\n"
        "name: deployer\n"
        "description: deploys services\n"
        "qm-layer: action\n"
        "qm-priority: 25\n"
        "qm-tags: deploy, production\n"
        "qm-risk: [network, secrets]\n"
        "qm-provides: deploy\n"
        "qm-requires: docker\n"
        "qm-requires-guardrails: secret-handling, security-review\n"
        "qm-conflicts-with: unsafe-deploy\n"
        "---\n"
        "body\n"
    )

    meta = metadata.parse(fm, name="deployer", description="deploys services")

    assert meta.layer == metadata.ACTION
    assert meta.explicit_layer is True
    assert meta.priority == 25
    assert meta.tags == ["deploy", "production"]
    assert meta.risk == ["network", "secrets"]
    assert meta.provides == ["deploy"]
    assert meta.requires == ["docker"]
    assert meta.requires_guardrails == ["secret-handling", "security-review"]
    assert meta.conflicts_with == ["unsafe-deploy"]


def test_malformed_priority_defaults_to_zero_and_invalid_layer_is_inferred():
    fm = frontmatter.parse(
        "---\n"
        "name: secure-api\n"
        "description: security hardening for APIs\n"
        "qm-layer: nonsense\n"
        "qm-priority: urgent\n"
        "---\n"
        "body\n"
    )

    meta = metadata.parse(fm, name="secure-api", description="security hardening for APIs")

    assert meta.layer == metadata.GUARDRAIL
    assert meta.explicit_layer is False
    assert meta.priority == 0


def test_existing_skill_without_metadata_gets_safe_defaults(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "fastapi-helper", description="FastAPI endpoint helper")

    reg = Registry.load(skills_dir=skills)
    skill = reg.get("fastapi-helper")

    assert skill.metadata.layer == metadata.DOMAIN
    assert skill.metadata.priority == 0
    assert skill.metadata.tags == []


def test_layer_inference_uses_name_description_and_tags():
    fm = frontmatter.parse(
        "---\n"
        "name: release-helper\n"
        "description: publish a package\n"
        "qm-tags: production\n"
        "---\n"
        "body\n"
    )

    meta = metadata.parse(fm, name="release-helper", description="publish a package")

    assert meta.layer == metadata.ACTION


def test_registry_attaches_metadata_from_frontmatter(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(
        skills,
        "secret-check",
        description="detect leaked secrets",
        extra="qm-layer: guardrail\nqm-priority: 100\nqm-risk: secrets",
    )

    reg = Registry.load(skills_dir=skills)
    skill = reg.get("secret-check")

    assert skill.metadata.layer == metadata.GUARDRAIL
    assert skill.metadata.priority == 100
    assert skill.metadata.risk == ["secrets"]


def test_status_layers_prints_layer_and_priority(tmp_path, monkeypatch, capsys):
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("QM_HOME", str(tmp_path / "qmhome"))
    monkeypatch.setenv("QM_SKILLS_DIR", str(skills))
    make_skill(
        skills,
        "secret-check",
        description="detect leaked secrets",
        extra="qm-layer: guardrail\nqm-priority: 100",
    )

    assert main(["status", "--layers"]) == 0

    out = capsys.readouterr().out
    assert "LAYER" in out
    assert "PRI" in out
    assert "guardrail" in out
    assert "100" in out
