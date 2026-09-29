#!/usr/bin/env python3
"""
PreToolUse hook —— **`git commit` 之前，自动跑本仓的三道门**。

## 为什么要它（这不是"再提醒一次"，是补一个结构性缺口）

本仓的规矩一直写着「提交前跑这几道门」，**但它们全靠人记得**。
而本仓有前科：**8 个 PR 一次都没跑过 `/留痕-checks`** ——
结论「**门挂在别处，就等于没有门**」（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）。

📌 **Anthropic 官方说法一致**：「**CLAUDE.md is context, not enforcement.**
必须每次发生的事，该用 hook。」（`docs/规范/文档体系-外部依据.md` §1.5）

📌 **2026-09-29 扩到三道**，依据是**当天实际犯的错**：
* 改完文档**没跑链接检查**（一路靠"我记得"）
* 新建文档**没登记 `docs/文档地图.md`**（脚本有了，但没人跑它）

## 三道门

| # | 门 | 脚本 | 拦住什么 |
|---|---|---|---|
| ① | **凭据门** | `scripts/check_secrets.sh` | PUBLIC 仓里混进明文凭据（**进了历史就改不掉**） |
| ② | **链接检查** | `scripts/check_doc_links.sh` | 文档里指向不存在的路径（**当天已犯 4 次**） |
| ③ | **孤儿检查** | `scripts/check_doc_orphans.sh` | 建了文档**但没人指向它**（索引挂空） |

⚠️ **三道都会【跳过本次提交】吗** —— 不是，见下面「克制」。

## 行为

```
命中 git commit
  → 依次跑 ①②③（任一不通过 ⇒ 【阻止提交】exit 2，把输出带出来）
  → 全通过 ⇒ 放行（exit 0），stderr 打一行汇总
其它命令 ⇒ 直接放行（不做任何事）
```

## ⚠️ 四条克制（别把它改成"什么都要拦"）

1. **只管 `git commit`** —— 不拦 `add` / `push` / `status`
2. **门跑不起来时【不阻止】** —— 脚本不存在或执行异常 ⇒ **只警告、放行**
   （否则 hook 坏了会把人**锁死**；"门本身坏了"是另一个问题，不该由这里表现出来）
3. **不打印凭据值** —— 它只**转述** `check_secrets.sh` 的输出，那个脚本本身已有脱敏逻辑
4. **⛔ 不用 `jq`** —— 本机**没装**（用它读 stdin 会**静默读空**，见 `DEC` 里那份工作树文档 §四）
"""
import json
import os
import re
import subprocess
import sys

GIT_COMMIT = re.compile(r"\bgit\s+commit\b")

# (显示名, 脚本相对路径)
GATES = [
    ("凭据门", "scripts/check_secrets.sh"),
    ("链接检查", "scripts/check_doc_links.sh"),
    ("孤儿检查", "scripts/check_doc_orphans.sh"),
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # 输入不是 JSON ⇒ 不是我们该管的

    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT.search(cmd):
        return 0  # 不是 commit ⇒ 放行

    # 定位仓根：优先 hook 给的 cwd；否则从本文件往上两级（.claude/hooks/x.py → 仓根）
    repo = data.get("cwd") or os.getcwd()
    if not os.path.exists(os.path.join(repo, "scripts", "check_secrets.sh")):
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(here))

    passed, failed, skipped = [], [], []

    for name, rel in GATES:
        path = os.path.join(repo, rel)
        if not os.path.exists(path):
            skipped.append(name)
            continue
        try:
            r = subprocess.run(["bash", path], cwd=repo, capture_output=True,
                               text=True, timeout=120)
        except Exception as e:
            skipped.append(f"{name}（跑不起来：{e}）")
            continue
        if r.returncode == 0:
            passed.append(name)
        else:
            failed.append((name, r))

    # ── 有门没过 ⇒ 阻止 ──
    if failed:
        print("", file=sys.stderr)
        print("⛔ 提交前的门【未通过】—— 已阻止本次 commit。", file=sys.stderr)
        for name, r in failed:
            print("", file=sys.stderr)
            print(f"──── {name} ────", file=sys.stderr)
            for line in (r.stdout or "").splitlines()[-25:]:
                print("   " + line, file=sys.stderr)
            for line in (r.stderr or "").splitlines()[-10:]:
                print("   " + line, file=sys.stderr)
        print("", file=sys.stderr)
        print("   ⇒ 先处理上面的命中项，再重新 commit。", file=sys.stderr)
        print("   （门的判据见 docs/规范/开发规范.md §2.4 · 处置见 docs/凭据轮换手册.md）",
              file=sys.stderr)
        return 2

    # ── 全过（或跳过）⇒ 放行 ──
    parts = [f"{n} ✅" for n in passed]
    if skipped:
        parts.append("⚠️ 跳过：" + " · ".join(skipped))
    print(f"🔒 提交前三道门：{' ｜ '.join(parts) or '（无门可跑）'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
