# SKILL.md & slash-command formatting constraints

**Context:** Discovered while authoring the Phase-1 harness (`game-master`, `combat-sub-agent`,
`ignarok` SKILLs and the `/stats /mochila /mapa /salvar` commands) for the gamebook engine.
**Date:** 2026-06-21
**Future intent:** Reuse as the checklist for every new SKILL or command added to this repo.

---

## Mental Model: description = activation trigger

A SKILL's **`description` is not documentation — it is the activation signal.** Claude Code
reads it to decide *when* to load the skill. So descriptions must be written in **third
person and trigger-oriented** ("Use this when…", "Activate at the start of…"), naming the
situations that should pull the skill in. A vague description = a skill that never fires.

| Element | Where | Rule |
|---|---|---|
| `name` | SKILL frontmatter | lowercase-with-hyphens; **matches the folder name** (`ignarok/SKILL.md` → `name: ignarok`) |
| `description` | SKILL frontmatter | third person, trigger-oriented (when to activate), front-loaded with the most distinctive triggers |
| Command file | `.claude/commands/<name>.md` | the file name is the `/command` |
| `description` | command frontmatter (optional) | one line shown in the command menu |
| `argument-hint` | command frontmatter (optional) | hints expected args, e.g. `[slot name, optional]` |
| `$ARGUMENTS` | command body | placeholder for user-typed args |

---

## Examples for the gamebook engine

### 1. Trigger-oriented SKILL description

`game-master` describes activation ("Activate at the start of any play session and for every
story turn…") rather than just "the narrator". `combat-sub-agent` names the delegation
trigger ("The Game Master delegates a fight to this…"). This is what makes auto-activation
work.

### 2. Command honoring real state

Each command file is the uniform pipeline *trigger → read/write MCP → print → return*, with
frontmatter `description` + (where relevant) `argument-hint`, and `/salvar`/`/mochila` reading
`$ARGUMENTS` for an optional slot/item.

---

## Relation to ADRs and next steps

- **ADR-003** — adventure-as-SKILL format (name must match folder).
- **ADR-004** — slash-command design pattern.
- Next step: when adding `/diario` etc., copy the command frontmatter + pipeline pattern.
