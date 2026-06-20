from qm import frontmatter


def test_parse_and_roundtrip_preserves_body():
    text = "---\nname: foo\ndescription: bar\n---\n# Heading\n\nBody line.\n"
    fm = frontmatter.parse(text)
    assert fm.has_fence
    assert fm.get("name") == "foo"
    assert fm.get("description") == "bar"
    assert fm.render() == text


def test_set_updates_existing_and_appends_new():
    fm = frontmatter.parse("---\nname: foo\ndescription: bar\n---\nbody\n")
    fm.set("description", "baz")
    fm.set("disable-model-invocation", "true")
    assert fm.get("description") == "baz"
    assert fm.get_bool("disable-model-invocation") is True
    # body preserved
    assert fm.render().endswith("body\n")


def test_remove_key():
    fm = frontmatter.parse(
        "---\nname: foo\ndisable-model-invocation: true\n---\nbody\n"
    )
    assert fm.remove("disable-model-invocation") is True
    assert fm.get("disable-model-invocation") is None
    assert fm.remove("nonexistent") is False


def test_description_with_colon_is_preserved():
    fm = frontmatter.parse("---\nname: foo\ndescription: a: b: c\n---\nx\n")
    assert fm.get("description") == "a: b: c"


def test_no_frontmatter():
    fm = frontmatter.parse("# just a doc\n")
    assert fm.has_fence is False
    assert fm.render() == "# just a doc\n"


def test_get_bool_variants():
    fm = frontmatter.parse("---\na: true\nb: false\nc: yes\n---\n\n")
    assert fm.get_bool("a") is True
    assert fm.get_bool("b") is False
    assert fm.get_bool("c") is True
    assert fm.get_bool("missing", default=True) is True
