#!/usr/bin/env python3
"""PostToolUse hook：**改了路由文件就问一句「这条新路由有鉴权吗」**。

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

# 改了这些文件 ⇒ 跑检查。⚠️ 加新路由文件时**记得加到这儿**。
ROUTE_FILES = {"main.py", "api_v1.py", "api_v1_rag.py", "api_v1_agent.py"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # 拿不到输入就静默退出，⛔ 别给主流程添乱

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        return 0

    name = Path(fp).name
    # ⚠️ 路径判据要**只看文件名 + 必须在 api/ 下** ——
    #    否则 `docs/xx/api_v1.py.md` 之类也会命中
    if name not in ROUTE_FILES or "api" not in Path(fp).parts:
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
