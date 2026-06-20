# skill-quartermaster
Non-destructive skill manager — compiles the right skill loadout per project, then demotes and hides unused skills to keep your context window lean. Never deletes without your approval.

<h1 align="center">🎖️ Quartermaster</h1>

<p align="center">
  <strong>A non-destructive skill manager for Claude Code.</strong><br>
  Compiles the right skill <em>loadout</em> for your project, then quietly demotes and hides the skills you aren't using —<br>
  so your context window stays lean and your skill set stays relevant. <strong>Nothing is ever deleted without your yes.</strong>
</p>

<p align="center">
  <!-- Replace these with real badges once published -->
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="claude code" src="https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2">
</p>

---

## The problem

The skill ecosystem exploded. Mega-marketplaces ship hundreds of skills in one install; aggregators index tens of thousands of plugin repos. Two pains follow:

- **Context cost & noise.** A large installed set clutters the model's selection space and degrades tool-selection accuracy past a few dozen skills.
- **Curation burden.** You have to decide what to keep, what to drop, and when to write new skills — and today there isn't even a clean "turn this one off." The common workaround is to *rename `SKILL.md` to `_SKILL.md`* so the parser misses it.

People avoid cleanup tools because of one fear: **"what if it deletes the wrong thing?"** Quartermaster is built so that can't happen.

## What it does

```
200 skills installed  →  12 loaded for this project  →  ~8k tokens saved  →  0 deleted
```

Quartermaster manages the **lifecycle** of your skills instead of their content. It moves skills along a tiered ladder based on what you actually use — and keeps a human veto on anything irreversible.

| State | In context? | Auto-loadable? | You can invoke? | On disk? |
|---|:---:|:---:|:---:|:---:|
| **active** | ✅ indexed | ✅ | ✅ | ✅ |
| **demoted** | ✅ indexed | ❌ | ✅ manual | ✅ |
| **hidden** | ❌ | ❌ | ❌ | ✅ |
| **deleted** | ❌ | — | — | ❌ *(only after you approve)* |

Every transition is **logged and reversible**. Demote and hide happen automatically; **delete never does**.

## Quick start

```bash
# Add the marketplace
/plugin marketplace add <your-org>/skill-quartermaster

# Install
/plugin install quartermaster@skill-quartermaster
```

Then, in your project:

```bash
qm status          # show every skill, its state, and last-used date
qm compile         # build an active loadout for this project
qm review          # see proposed demotions/promotions and approve them
qm restore <skill> # bring anything back from demoted/hidden
```

> Quartermaster only ever *toggles states* and *proposes* changes. It will not remove a skill from disk unless you explicitly confirm.

## How it works

```mermaid
flowchart LR
    A[Project intent + style] --> B[Intent Compiler]
    B --> C[Active loadout ~30 skills]
    C --> D[Run tasks]
    D --> E[Usage telemetry + feedback]
    E --> F[Policy Engine - proposals only]
    F --> G[Human approval gate]
    G --> H[Update registry / state]
    H --> C
    F -. capability gap .-> I[Authoring arm]
    I --> H
```

1. **Registry** — an index of every skill on disk with its state, description embedding, and last-used timestamp.
2. **Intent compiler** — selects an initial active set from your project intent + style file, kept near the ~30-skill accuracy sweet spot.
3. **Telemetry** — logs which skills actually fire per task (via skill hooks). Local-only; nothing leaves your machine.
4. **Policy engine** — *proposes* demotions (unused for N days), promotions (you keep invoking a demoted skill), and authoring (repeated gaps with no matching skill).
5. **Human gate** — batched approvals; deletion only after long-demoted **and** explicit confirmation.
6. **Authoring arm** — hands genuine gaps to `skill-creator`, admitting new skills as `active, probationary`.

Under the hood these states map to existing Claude Code primitives — Quartermaster configures them, it doesn't reinvent them.

## Why non-destructive matters

You're trusting a tool to touch your skills. Quartermaster's entire design is built around that trust:

- **Demote, don't delete** — unused skills drop out of the model's attention and out of context, but stay fully on disk and recoverable.
- **One-command restore** — `qm restore` reverses any automatic change.
- **Human-gated deletion** — the only path to removal runs through an explicit approval.
- **Full audit log** — every state change is recorded and inspectable.

## Roadmap

| Phase | Scope |
|---|---|
| **v0** | Lifecycle core: registry, state toggles, `qm status` + token-saved report |
| **v0.2** | Usage telemetry + demote-if-unused proposals + batched approvals |
| **v0.3** | Intent compiler (loadout from project intent + style) |
| **v0.4** | Authoring arm (gap detection → `skill-creator` handoff) |
| **v0.5** | Natural-language feedback → lifecycle/authoring signals |
| **v1.0** | Audit log UI, one-click revert, dashboard, marketplace listing |

We ship the lifecycle half first on purpose — the compiler and authoring arm only earn their place once the simple half has users.

## Contributing

Contributions welcome — especially telemetry hooks, policy rules, and adapters for other harnesses (Cursor, Copilot, Zed) via the open Agent Skills standard. Please open an issue describing the change before large PRs.

## License

MIT — see [LICENSE](./LICENSE).

---

<p align="center"><sub>Quartermaster manages your skills. It never loses them.</sub></p>
