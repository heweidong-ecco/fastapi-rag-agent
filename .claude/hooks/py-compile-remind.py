#!/usr/bin/env python3
r"""PostToolUse hook：**改完一个 .py 就当场编译一次** —— ⛔ 别等到提交前。

## 为什么（`docs/复盘/2026-09-20-docstring里嵌三引号截断了字符串.md`）

那次我在一个 docstring 里**嵌了三个双引号**，**把字符串从中间截断了**。
> 😅 **2026-10-05 本文件自己踩了同一个坑**：初稿的这段注释里真写了那三个引号
> ⇒ 整个文件 `SyntaxError`（`invalid character '，'`）。**是自测 T1 抓出来的**，
> ⇒ 也说明这条自测**不是摆设**：它确实能证伪。
> ⚠️ 所以本文件里**不许出现连续三个双引号**（注释里也不行）。
改完之后我**没跑任何东西** —— 直到提交前 `compileall` 才报出来。
⇒ **错误在"写下去"和"被发现"之间躺了很久**，而这段时间里它看起来已经做完了。

本仓对这件事的立场（`docs/规范/开发规范.md` §3.2 规则 4）：
**「我这一批改了 N 处」⇒ 那 N 处【各自】要能被验。**
而"这个文件还是合法 Python 吗"是**最便宜的那一条验法**（一次 `py_compile` ≈ 几十毫秒）。

## 设计（为什么这样）

| 决策 | 理由 |
|---|---|
| **挂在 `PostToolUse`（Edit\|Write）** | 与 `spec-remind.py` / `route-auth-remind.py` 同一挂法；`PostToolUse` 拿得到 `tool_input` |
| ✅ **只编译【刚改的那一个文件】** | 全仓 `compileall` 要几秒；单文件几十毫秒 ⇒ 每次编辑都付得起 |
| ⛔ **不阻断**（exit 0） | `PostToolUse` 本来就拦不住（编辑已发生）。它的价值是**把错误说到眼前**，不是拦 |
| ⚠️ **用 `py_compile` 而不是 `compileall`** | 同一件事的单文件版本（`compileall` 是它对整棵树）；待办总表 §五·4 要的是"每次编辑后"这个**时机** |
| ⛔ **不碰 `venv/` / `worktrees/`** | 那些不是本仓的源码（`worktrees` 是按**路径前缀**排的，见 `check_doc_orphans.sh` 同一处踩坑） |
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKIP_DIR_PARTS = {"venv", "venv-ragas", ".venv", "node_modules", "__pycache__", ".git"}


def should_check(p: Path) -> bool:
    if p.suffix != ".py" or not p.is_file():
        return False
    parts = set(p.parts)
    if parts & SKIP_DIR_PARTS:
        return False
    # `.claude/worktrees/` 是整仓副本（`.gitignore:59` 有意排除）⇒ 不编译它。
    # ⚠️ 判据用**两个目录名同时在场**，⛔ 不用「路径前缀」——
    #    前缀比较要先 `resolve()`，而 `/var` 在 macOS 上是 `/private/var` 的软链
    #    ⇒ 漏 resolve 会让这条豁免**静默失效**（2026-10-05 实测，见 `claim-evidence-remind.py`
    #    同名函数上的那段记录）。按 parts 判**与软链无关**。
    # ⚠️ 但 `.claude/hooks/*.py` **要编译** —— 它们就是 Python，且本文件初稿的
    #    `SyntaxError` 正是这类检查该抓的东西。
    if ".claude" in p.parts and "worktrees" in p.parts:
        return False
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # 拿不到输入就静默退出，⛔ 别给主流程添乱

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        return 0

    p = Path(fp)
    if not should_check(p):
        return 0                                   # ← 绝大多数编辑走到这里

    exe = REPO / "venv" / "bin" / "python"
    if not exe.exists():
        exe = Path(sys.executable)

    try:
        r = subprocess.run([str(exe), "-m", "py_compile", str(p)],
                           capture_output=True, text=True, timeout=20, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        print(f"⚠️ 编译检查超时（>20s）：{fp} —— 手工跑 `python3 -m py_compile {fp}`")
        return 0

    if r.returncode != 0:
        # ⚠️ 只打印**错误本身**（SyntaxError 那几行），⛔ 不打印整篇 traceback ——
        #    这段会直接进上下文，越长越容易被略读。
        err = (r.stderr or "").strip()
        print(f"🔴 **编译不过**：{os.path.relpath(fp, REPO)} —— 这个文件现在不是合法 Python。")
        print()
        print("\n".join(err.splitlines()[-12:]))
        print()
        print("📌 本仓纪律：**「我写进去了」≠「它能用」** —— 判据是【跑一次】，⛔ 不是【我改了】。")
        print("   出处：`docs/复盘/2026-09-20-docstring里嵌三引号截断了字符串.md` · 开发规范 §3.2 规则 4")

    return 0


if __name__ == "__main__":
    sys.exit(main())
