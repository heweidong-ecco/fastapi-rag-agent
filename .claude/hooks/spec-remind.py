#!/usr/bin/env python3
"""
PostToolUse hook —— **写完 `app/*.py` 之后，提醒更新它的 spec**。

## 为什么要有它

`docs/specs/` 是**模块视角**的规格（这个模块做到哪、**看代码会误判什么**）。
但 **spec 是人/agent 写的 ⇒ 它会过期**。

`pre-commit-gates.py` 的**第 ④ 道门**只能拦**"新增模块没 spec"**（能机械判）；
**"改了已有模块要不要更新 spec"是【判断】，机械判不了** ⇒ **只能提醒**。

⇒ **本 hook 就干这一件事：动完 `app/X.py`，提醒你 `docs/specs/X.md` 可能要更新。**

## 行为

* 命中 `Edit` / `Write` / `NotebookEdit`，且 `file_path` 在 `app/` 下、是 `.py`、**不是测试** ⇒
  **打一行提醒**（**不阻止**，`exit 0`）
* **已有 spec 的** ⇒ 「记得更新它」
* **还没有 spec 的** ⇒ 「这个模块还没有 spec」（**比"记得更新"更值得说**）
* 其它 ⇒ 静默放行

## ⚠️ 三条克制

1. ⛔ **不阻止** —— `PostToolUse` 阻止不了已经发生的编辑；而且写代码过程中会频繁触发，
   真拦会把人烦死。
2. **只在 `app/` 下、非测试的 `.py`** —— 改文档、改测试、改 `scripts/` 都不提醒。
3. **每次只打一行** —— 不写小作文。

## 📌 为什么不用 `$CLAUDE_PROJECT_DIR` 找仓根

那份《多项目 + 多 worktree》文档实测过：**它在"会话中途进 worktree"时会停在主检出**
⇒ **用 stdin 的 `cwd`**（两种情况都对）。本仓不用 worktree，但**照这个写更稳**。
"""
import json
import os
import sys

TEST_PREFIX = "test_"
SKIP_NAMES = {"conftest.py"}


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name") or ""
    if tool not in ("Edit", "Write", "NotebookEdit"):
        return 0

    fp = (data.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return 0

    cwd = data.get("cwd") or os.getcwd()
    # 一律先转成相对仓根的路径（file_path 可能是绝对的）
    try:
        rel = os.path.relpath(os.path.abspath(fp), os.path.abspath(cwd))
    except ValueError:
        return 0
    rel = rel.replace(os.sep, "/")

    if not (rel.startswith("app/") and rel.endswith(".py")):
        return 0
    base = os.path.basename(rel)
    if base.startswith(TEST_PREFIX) or base in SKIP_NAMES:
        return 0                       # 测试/配置不算产品模块

    mod = base[:-3]
    spec_rel = f"docs/specs/{mod}.md"
    spec_abs = os.path.join(cwd, "docs", "specs", f"{mod}.md")

    if os.path.exists(spec_abs):
        print(f"📋 你动了 `{rel}` —— 记得更新 `{spec_rel}`"
              f"（⭐ 关键节：「看代码会误判的地方」）", file=sys.stderr)
    else:
        print(f"📋 你动了 `{rel}` —— ⚠️ **它还没有 spec**（`{spec_rel}`）。"
              f"做完记得建一份，模板见 `docs/specs/README.md`", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
