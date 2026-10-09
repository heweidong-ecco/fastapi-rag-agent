# Subagent Lifecycle & Authorization Policy

> **Scope**: every subagent created in this repository, by any session or any agent.
> **Status**: in force.
> **Language note**: this repo's documents are written in Chinese; this one is in English
> by explicit instruction (2026-10-09). Keep it in English.

---

## 0. The one-sentence rule

> **A subagent exists for exactly one task. When that task ends, the subagent is retired.
> Nothing is standing unless a human said so.**

Everything below is the mechanics of that sentence.

---

## 1. Vocabulary (so the rest is unambiguous)

| Term | Meaning |
|---|---|
| **Ephemeral subagent** | A subagent definition whose lifetime is bounded by **one task**. The default and normal case. |
| **Standing subagent** | A subagent definition that persists across sessions and is reused by unrelated tasks. **Requires human approval.** |
| **Task** | A single deliverable with a stated **stop condition**. "Refactor the repo" is not a task; it is many tasks. |
| **Retire** | Move the definition out of the active directory so it is no longer offered as an option. A **file move**, not a note (§6). |

---

## 2. Decision ladder — try the cheapest rung first

Before spawning anything, walk down this list and stop at the first rung that works:

| # | Rung | Use when |
|---|---|---|
| 1 | **Do it in the main session** | The default. Always try this first. |
| 2 | **`settings.json` / `commands/` / `hooks/` / a shell or Python script** | The work is *repeatable* and *mechanical*. A script is cheaper, testable, and leaves a trace. |
| 3 | **Ephemeral subagent** (§3) | The work is **long-running**, **separable**, and keeping it in the main session would **exhaust context** on a task that can run to a stated stop condition. |
| 4 | **Standing subagent** (§5) | A human has explicitly approved it. |

⛔ **Do not skip to rung 3 because it is convenient.** The justification for rung 3 must be
"this is long and separable", not "I would rather not do it sequentially".

⚠️ Rung 2 exists because subagents are **expensive**: they duplicate context, they cannot ask
the human anything mid-flight, and their work has to be re-verified anyway. A script you can
read in ten lines beats an agent you cannot read at all.

---

## 3. Creating an ephemeral subagent

### 3.1 The definition must exist **before** the subagent is spawned

Write `.claude/agents/<name>.md` first, then spawn. Not the other way round —
otherwise the ephemeral rule has no machine trace.

### 3.2 Required frontmatter

```yaml
---
name: <lowercase-english-kebab-case>          # ⛔ never CJK — see 3.3
description: <one line: when a caller should use this>
tools: <comma-separated tool list>
ephemeral: true                                # always true for rung 3
task_category: refactor | audit | migration | docs | verification | other
task_scope: <the ONE task this definition exists for, in one sentence>
stop_condition: <the observable state that means this task is finished>
created: <YYYY-MM-DD>
---
```

Then the body: what the subagent must do, what it must **not** do, and what it returns.

### 3.3 Naming

- **English, lowercase, kebab-case.** e.g. `import-rewriter`, `doc-link-fixer`, `spec-migrator`.
- ⛔ **No Chinese characters in the filename.** Two concrete reasons:
  1. Tooling that derives identifiers from paths (Claude Code's own project-directory
     encoding, `git ls-tree` output, many CI steps) collapses non-ASCII characters and can
     then **collide two distinct names into one**.
  2. The subagent `name:` is an **address** used to resume it later. An address that cannot
     be typed on a US keyboard is not an address.

### 3.4 Hard limits on an ephemeral subagent

| Rule | Why |
|---|---|
| **One task only.** | It is defined by its `task_scope`. A second task means a second definition. |
| **Must not spawn its own subagents.** | Otherwise the retirement rule (§4) cannot reach the grandchildren, and the tree outlives the task. |
| **Must have a stop condition.** | A subagent without one cannot be retired, because "done" is undefined. |
| **Must not perform outward-facing or irreversible actions** (push, PR, deploy, delete outside the repo workspace). | Those stay in the main session, where the human's approval is in scope. |
| **Must not be used to route around a denial.** | If a permission was denied in the main session, delegating it to a subagent is a bypass, not a solution. |

---

## 4. Retirement — **mandatory**, at task end

Retirement happens when the task ends, whether it **succeeded, was abandoned, or was superseded**.

### 4.1 Move the definition

```bash
git mv .claude/agents/<name>.md .claude/agents/tmp/<task_category>/<name>.md
```

Grouping by `<task_category>` is what makes the archive navigable later:
*"what did we use for the last migration?"* is answerable; a flat pile of names is not.

### 4.2 Stamp it as retired

Add to the frontmatter of the moved file:

```yaml
retired: <YYYY-MM-DD>
outcome: done | abandoned | superseded
permanent_candidate: true | false
notes: <one line: what worked, what did not — optional but valuable>
```

### 4.3 Register it

Append one line to `.claude/agents/tmp/README.md` (the archive index):

```
- <task_category> | <name> | <retired date> | <outcome> | <permanent_candidate?>
```

### 4.4 The rule that makes this a rule

> ⛔ **An ephemeral definition left in `.claude/agents/` after its task is a defect.**
> It will be offered to future sessions as if it were generally applicable,
> and nobody will remember that its scope ended.

---

## 5. Promotion to standing (human approval required)

If a retired subagent has `permanent_candidate: true`, or a session believes a definition
should become standing, then:

1. **Ask the human.** Present: the name, what task it was built for, what evidence exists
   that it is reusable, and what the cost is if it turns out not to be.
2. **On approval** → move it to `.claude/agents/<name>.md` and set:
   ```yaml
   ephemeral: false
   approved_by: <who>
   approved_at: <YYYY-MM-DD>
   ```
3. **On refusal** → leave it in `tmp/`. The refusal is not a defect; the archive is the
   correct resting place for a useful-but-not-standing definition.

⛔ **Never promote silently.** Promoting is the one action in this policy that changes what
future sessions will do without anyone asking.

---

## 6. Why retirement is a **file move** and not a note

This repository has learned the same lesson repeatedly, in its own words:

> **「门挂在别处，就等于没有门」** — *a gate that lives somewhere else does not exist.*
> **「只有文字就漏，结构才执行」** — *prose leaks; structure executes.*

A "retired" marker written inside the file leaves the file **in the active directory**.
The filesystem is what makes a definition available; therefore the filesystem is what must
change. A note cannot do that; a move can.

---

## 7. Edge cases

| Situation | Ruling |
|---|---|
| The task is abandoned halfway | **Still retire**, `outcome: abandoned`. A half-used definition is the most likely one to be accidentally reused. |
| Two sessions create the same subagent name | Names collide by design. The second session must retire the first (§4) or pick a different name. There is no "override". |
| The task turns out to be trivial | Retire immediately. The definition's existence is not itself a commitment to use it. |
| A retired definition is needed again | **Recreate it as a new ephemeral definition** (§3), copying from the archive. Do not un-retire in place — that would erase the record of its first run. |
| The definition duplicates an existing standing subagent | Do not create it. Use the standing one. |

---

## 8. Enforcement — ⬜ **prose-only today** (known weakness)

Right now this policy is **not machine-enforced**. Consistent with §6, that means it is weak.

The natural enforcement, when it is built, is a `PreToolUse` hook:

- **Matcher**: the `Agent` tool.
- **Check**: the requested `subagent_type` resolves to a definition under `.claude/agents/`
  that either (a) has `ephemeral: true` **and** a `task_scope`, or (b) has
  `ephemeral: false` **and** an `approved_by`. Anything else ⇒ **ask**, printing the
  definition's frontmatter to the approval prompt.
- **Why ask and not block**: an unrecognised name is sometimes the harness's own built-in
  agent set, which this policy does not govern. Blocking those would break unrelated work.
- ⚠️ **Follow this repo's existing rule for hooks**: a gate must be able to **prove it can
  go red** before it is trusted. See `.claude/README.md` for the shape of the existing gates,
  and the self-test convention in `scripts/test_*.sh`.

⬜ **Not built.** Recorded here so that "we have a policy" is not mistaken for "we have a gate".

---

## 9. Quick checklist

**Before spawning**: does a cheaper rung work? → is this long and separable? → does the
definition exist with `ephemeral: true`, a `task_scope`, and a `stop_condition`?

**At task end**: `git mv` to `tmp/<task_category>/` → stamp `retired` / `outcome` /
`permanent_candidate` → add the index line → if it deserves to be standing, **ask**.
