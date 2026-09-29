#!/usr/bin/env python3
"""
PreToolUse hook —— **在 `git commit` 之前自动跑凭据门**。

## 为什么要它（这不是"再提醒一次"，是补一个结构性缺口）

本仓规矩：「**提交前必跑 `scripts/check_secrets.sh`**」。

⚠️ **但它一直是【靠人记得】的** —— 而本仓有前科：
**8 个 PR 一次都没跑过 `/留痕-checks`**（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`），
结论是「**门挂在别处，就等于没有门**」。

📌 **Anthropic 官方说法一致**：「**CLAUDE.md is context, not enforcement.**
必须每次发生的事，该用 hook。」（`docs/规范/文档体系-外部依据.md` §1.5）

⇒ **本文件就是那个 hook。** 它把「记得跑」变成「跑不了就跑不成」。

## 行为

- 命中 `git commit` ⇒ **先跑 `scripts/check_secrets.sh`**
  - 通过 ⇒ 放行（exit 0），stderr 打一行「凭据门 ✅」
  - **不通过 ⇒ 【阻止本次提交】**（exit 2），把门的输出原样带出来
- 其它命令 ⇒ 直接放行（**不做任何事**）

## ⚠️ 三条设计上的克制

1. **只管 `git commit`** —— 不拦 `git add` / `git push`（那些不该被这里拦）
2. **门跑不起来时【不阻止】** —— 如果脚本不存在或执行失败，**只警告、放行**
   （否则 hook 坏了会把人锁死；而"门本身坏了"是另一个问题）
3. **不打印凭据值** —— 它只转述 `check_secrets.sh` 的输出，那个脚本本身已有脱敏逻辑
"""
import json
import os
import re
import subprocess
import sys

GIT_COMMIT = re.compile(r"\bgit\s+commit\b")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # 输入不是 JSON ⇒ 不是我们该管的，放行

    tool_input = data.get("tool_input") or {}
    cmd = tool_input.get("command") or ""
    if not GIT_COMMIT.search(cmd):
        return 0  # 不是 commit ⇒ 放行

    # 定位仓根：优先用 hook 给的 cwd，否则用本文件往上两级（.claude/hooks/x.py → 仓根）
    cwd = data.get("cwd") or os.getcwd()
    repo = cwd
    guard = os.path.join(repo, "scripts", "check_secrets.sh")
    if not os.path.exists(guard):
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(here))
        guard = os.path.join(repo, "scripts", "check_secrets.sh")

    if not os.path.exists(guard):
        print("⚠️ 凭据门脚本不在（scripts/check_secrets.sh）—— 本次【放行】，但请确认这不是异常。",
              file=sys.stderr)
        return 0

    try:
        r = subprocess.run(["bash", guard], cwd=repo, capture_output=True,
                           text=True, timeout=60)
    except Exception as e:
        print(f"⚠️ 凭据门跑不起来（{e}）—— 本次【放行】。", file=sys.stderr)
        return 0

    if r.returncode == 0:
        tail = (r.stdout or "").strip().splitlines()
        print(f"🔒 凭据门 ✅  {tail[-1] if tail else ''}", file=sys.stderr)
        return 0

    # 不通过 ⇒ 阻止
    print("", file=sys.stderr)
    print("⛔ 凭据门【未通过】—— 已阻止本次 commit。", file=sys.stderr)
    print("", file=sys.stderr)
    for line in (r.stdout or "").splitlines()[-25:]:
        print("   " + line, file=sys.stderr)
    for line in (r.stderr or "").splitlines()[-10:]:
        print("   " + line, file=sys.stderr)
    print("", file=sys.stderr)
    print("   这是 PUBLIC 仓 —— 凭据一旦进了历史就【改不掉】。", file=sys.stderr)
    print("   ⇒ 先处理命中项，再重新 commit。", file=sys.stderr)
    print("   （判据与处置见 docs/凭据轮换手册.md）", file=sys.stderr)
    return 2  # 2 = 阻止


if __name__ == "__main__":
    sys.exit(main())
