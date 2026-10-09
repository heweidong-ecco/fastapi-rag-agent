# `.claude/agents/tmp/` — retired subagent archive

> **What this is**: the resting place for **retired ephemeral subagent definitions**.
> See the policy: [`../subagent-lifecycle.md`](../subagent-lifecycle.md) §5.
>
> **Rule**: a definition lands here when its task ends — **succeeded, abandoned, or superseded**.
> It is a `git mv`, not a note. Nothing here is an active subagent.

---

## Layout

```
.claude/agents/tmp/
├── README.md              ← this index
└── <task_category>/       ← refactor | audit | migration | docs | verification | other
    └── <name>.md          ← the retired definition (frontmatter stamped, §5.2)
```

## Index

> One line per retired definition, appended at retirement (§5.3).
> Format: `<task_category> | <name> | <retired> | <outcome> | <permanent_candidate?>`

_（空 —— 还没有退休的 subagent）_

---

## ⚠️ One thing to verify before relying on this

Claude Code discovers project subagents from `.claude/agents/*.md`. **Whether it scans
`tmp/` subdirectories too is not confirmed** (2026-10-09, docs not reachable to check).

- If it does **not** scan recursively → retired definitions are correctly invisible.
  ✅ Everything in `../subagent-lifecycle.md` works as written.
- If it **does** scan recursively → a retired definition would still be offered, which
  defeats §5.4. In that case, move the archive outside the scan path
  (e.g. `.claude/agents-retired/`) and update §5.1 of the policy.

**How to check**: `claude` → `/agents` (or `/status`) and look for whether any name under
`tmp/` shows up in the available-subagent list. ⬜ **Not yet checked.**
