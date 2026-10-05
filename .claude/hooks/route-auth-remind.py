#!/usr/bin/env python3
r"""PostToolUse hook：**改了路由文件就问一句「这条新路由有鉴权吗」**。

## 为什么是 hook（2026-09-30）

**起因**：核 `api_v1.py` 时手工扫"哪些路由没鉴权"，**第一版扫出 0 条** ——
因为 `FastAPI 0.141` 起 `include_router` 的结果被包成 `_IncludedRouter`。

🔴 **那个坑【仓里早就写着】**（`api/test_public_paths.py:17-20`）——
**知识在，但挂在一个谁都不会去读的地方**（一个测试文件的 docstring 里）。

⇒ 所以**不是再写一条规矩**，是**把它挪到"我一定会撞上"的位置**：
**改路由文件 ⇒ 自动跑一次检查**。（本仓复盘结论：「规矩写了三条，当天犯了五次」）

## 设计（为什么这样）

| 决策 | 理由 |
|---|---|
| **挂在 `PostToolUse`（Edit\|Write）** | Claude Code 的 hook **只按【工具名】匹配、拿不到文件路径** ⇒ **脚本自己判断** |
| ✅ **先判路径，不是路由文件就【立刻退出】** | 全量扫描要 **9–13 秒**（实测，已关遥测）。每次编辑都跑不起 ⇒ **只在相关时付这个代价** |
| ⛔ **不阻断**（exit 0） | `PostToolUse` 本来就拦不住（编辑已发生）—— 它的价值是**把话说到眼前**，不是拦 |
| **只报「比基线【变多】」** | 现有 10 条是**已知的债**（`docs/待办总表.md` 🅗 的 `S1`/`S2`/`S14`）⇒ 天天报只会让人不看（本仓栽过：**太宽的 grep 会刷出 40 处噪音**） |

⚠️ **为什么是 `.py` 不是 `.sh`**：要解析 hook 传进来的 JSON（拿 `tool_input.file_path`），
Python 标准库一句话的事，`.sh` 要引 `jq`。**与同目录已有的 `spec-remind.py` 保持一致。**
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def looks_like_route_file(p: Path) -> bool:
    """这个文件**像不像**生产路由文件 —— 按【形状】判，⛔ 不是按文件名清单。

    🔴 2026-10-05（批 4 · `N10`）**把清单换成形状**。改前是：
        ROUTE_FILES = {"main.py", "api_v1.py", "api_v1_rag.py", "api_v1_agent.py"}
    那是个**形状盲区**：新建第 5 个路由文件（`api_v1_admin.py` 之类）时，
    本钩子会**静默不跑** —— 而"静默不跑"与"跑过了没发现问题"在机器痕迹上**完全一样**
    （本仓 `DEC-061`）。⚠️ 清单式判据**天生**会随仓的生长而失效，且失效时不报警。

    ⇒ 判据改成**问文件内容**：`api/` 下的 .py，只要出现 `APIRouter(` / `@router.` / `@app.`
       就算路由文件。**新建文件自动被覆盖**，⛔ 不需要谁记得改清单。
    ⚠️ 三个判据都是**便宜**的（读一个文件），而它挡在后面的是 **9–13 秒**的全量扫描 ——
       ⇒ 宁可多跑几次，也别漏（多跑只是慢，漏跑是**假绿**）。
    ⚠️ 排除 `test_*.py` 与 `tests/` 下：测试里也会 `APIRouter()`，但它们不是**生产路由**；
       不排除的话，每次改测试都要付 10 秒（TDD 时尤其难受）。
    """
    if p.suffix != ".py":
        return False
    if "api" not in p.parts:              # ⚠️ 只看 `api/` 下 —— 否则 docs 里的示例也会命中
        return False
    if p.name.startswith("test_") or "tests" in p.parts:
        return False
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return ("APIRouter(" in text) or ("@router." in text) or ("@app." in text)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # 拿不到输入就静默退出，⛔ 别给主流程添乱

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        return 0

    # ⚠️ 路径判据要**只看文件名 + 必须在 api/ 下** ——
    #    否则 `docs/xx/api_v1.py.md` 之类也会命中（那个 checks 在 looks_like_route_file 里）
    if not looks_like_route_file(Path(fp)):
        return 0                                   # ← 绝大多数编辑走到这里，0.0x 秒

    script = REPO / "scripts" / "check_route_auth.py"
    if not script.exists():
        return 0

    py = REPO / "venv" / "bin" / "python"
    exe = str(py) if py.exists() else sys.executable

    try:
        r = subprocess.run(
            [exe, str(script), "--baseline"],
            capture_output=True, text=True, timeout=55, cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        print(f"⚠️ 路由鉴权检查超时（>55s）—— 手工跑：`python3 scripts/check_route_auth.py`")
        return 0

    if r.returncode != 0:
        print("🔴 路由鉴权检查：**新引入了没有鉴权依赖的路由**\n")
        print(r.stdout.strip()[:1500])
        print("\n📌 见 `docs/待办总表.md` 🅗（S1/S2/S14）与 `docs/规范/开发规范.md` §1.5")

    return 0


if __name__ == "__main__":
    sys.exit(main())
