---
description: Scaffold a new probationary skill for a recurring capability gap, then hand off to skill-creator.
argument-hint: <skill-name> [what it should do]
---

Use Quartermaster's authoring arm to create a new skill.

Arguments: $ARGUMENTS

First check whether Quartermaster already recommends a skill for an observed gap:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" gaps
```

Then scaffold the probationary stub (replace `<name>` and `<desc>`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" author <name> --desc "<one-line description>" --yes
```

The skill is admitted as **active, probationary** — usable immediately but on
trial. `qm author` writes only a stub. Now invoke the **`skill-creator`** skill
to write the real instructions into the generated `SKILL.md`, using the brief
Quartermaster printed.

Leave the skill probationary until the user confirms it works in practice, then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/qm" graduate <name>
```

Nothing is overwritten or deleted — authoring only adds a new skill directory.
