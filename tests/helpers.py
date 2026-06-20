from pathlib import Path


def make_skill(root: Path, name: str, description: str = "does a thing", extra: str = "") -> Path:
    """Create a SKILL.md under root/<name>/ and return its path."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    fm = [f"name: {name}", f"description: {description}"]
    if extra:
        fm.append(extra.strip())
    text = "---\n" + "\n".join(fm) + "\n---\n\n# " + name + "\n\nBody.\n"
    p = d / "SKILL.md"
    p.write_text(text, encoding="utf-8")
    return p
