#!/usr/bin/env python3
r"""PostToolUse hook：**写「X 不存在 / X 是唯一的 / 从来没有」之前，先出一条命令**。

## 为什么（`docs/待办总表.md` §五·1 · 出处 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`）

那天我调 `POST /rag/search`，响应里 `answer` 字段是空的 ⇒ **据此写下了三句全称否定**：
① `/rag/ask` **不存在** ② `/rag/search` **不生成答案** ③ `/rag/stream_search` 是**唯一**能生成答案的端点。
🔴 **三句全错**，而且**写进了 4 处**（`ROADMAP` 第一屏、一份 `DEC`、施工单、**git 提交信息**）。

> **结论：「X 不存在」是一个【结论】，不是一个【观察】。**

**同一天又犯了三次**（同一族）：用 `grep -oE '^[A-Z_]+='` 数键名 ⇒ 0 命中 ⇒ 写下「`.env.example` 缺 4 个键」
（⭐ **grep 的模式不匹配注释行**，而那 4 个键恰好是注释形式）……

⇒ **不是"下次注意"能解决的** —— 本仓对该族的立场：**这类规矩要【做成命令】，不能只写在文档里**
（`docs/规范/开发规范.md` §3.2 末尾那句原话）。

## 设计（为什么这样）

| 决策 | 理由 |
|---|---|
| **判据分成两半：① 有没有全称否定 ② 有了 ⇒ 附近有没有命令** | ① **只能**靠穷举证明 ⇒ **必须是一条命令**；② 命令**必须出现在写入的那段文本里**（或该文件里），⛔ 不是"我记得我查过" |
| **命令只认【代码块 / 行内代码里的】** | ⛔ 不认"我 grep 过了"这种散文 —— 那正是本族错误的原始形态 |
| ⛔ **不阻断**（exit 0） | `PostToolUse` 拦不住（写入已发生）。它的价值是**在结论落地前把话说到眼前** |
| **文件名里带 `remind` 而不是 `gate`** | 它是**提醒**不是门 —— ⛔ 别把它读成"过了它就对了"（本仓纪律：**一条测不出「不成立」的守卫 = 没有守卫**） |
| ⚠️ **专用旁路：文本里出现「全称否定」四个字 ⇒ 静默** | 复盘 / DEC / 规范**本来就要引用这些错误的原话**；⛔ 否则每写一次复盘就被提醒一次，很快就没人看了（本仓栽过：**太宽的 grep 会刷出 40 处噪音**） |
| ⛔ **不管 `docs/复盘/` · `CHANGELOG.md` · `.claude/`** | 前两者是**历史记录、明文不改写**（开发规范 §四·4）；`.claude/` 里这些 hook 的正文**就是这条规则本身** |
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ⚠️ 刻意**窄**：只收录 `docs/复盘/2026-09-29` 那条规则点名的全称否定形态。
#    ⛔ 别加 `找不到` / `没有` 这类 —— 它们在正常叙述里出现得太频繁，会把提醒冲成噪音。
CLAIM_RES = (
    re.compile(r"不存在"),
    re.compile(r"从来没有"),
    re.compile(r"没有任何"),
    re.compile(r"都没有"),
    re.compile(r"是唯一的"),
    re.compile(r"唯一一[个处条次]"),
    re.compile(r"从未"),
)

# 「命令」= 出现在**代码块或行内代码**里的这些词。⛔ 散文里的"我查过了"不算。
CMD_WORDS = (
    "grep", "rg ", "rg -", "ls ", "ls -", "find ", "curl", "git ", "git-",
    "wc ", "cat ", "head ", "tail ", "sed ", "awk ", "jq ", "diff ",
    "pytest", "python", "npm ", "docker ", "sqlite3", "psql",
)
CODE_SPAN_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)

BYPASS = "全称否定"          # ← 文本里带上这四个字即静默（复盘 / DEC 引用原话时用）

SKIP_PARTS = {".git", "venv", ".venv", "venv-ragas", "node_modules", "__pycache__"}


def relpath_of(p: Path) -> str:
    """把路径化成**相对本仓**的形式；化不了就原样返回（⛔ 绝不抛异常）。

    🔴 **两侧都要 `resolve()`** —— 2026-10-05 实测：
      `mktemp -d` 给出 `/var/folders/...`，而 `Path(__file__).resolve()` 给的是
      `/private/var/folders/...`（macOS 上 `/var` **是指向 `/private/var` 的软链**）
      ⇒ 不 resolve 的话 `relative_to` 抛 `ValueError` ⇒ 走到 `return str(p)`
      ⇒ 下面那几条**按路径前缀的豁免（`docs/复盘/` · `CHANGELOG.md`）会【静默失效】**。
      ⚠️ 那正是本仓最讨厌的失败形态：**不报错，只是不再生效**。
      ⚠️ 副本里 T9 红、真仓里 T9 绿 —— 差别就是这条软链。**两边都 resolve 才一致。**

    ⛔ 别退回成裸 `p.relative_to(REPO)`：路径**可能在仓外**（`/tmp/...`）⇒ `ValueError`
      ⇒ **整个 hook 崩掉、退出码 1**（实测：自测 T1–T8 全报 `退出码 1`，就是这个根因）。
    ⚠️ 提醒型 hook 的失败方式里**不许有"把主流程搞挂"**这一种。"""
    try:
        return str(p.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(p)


def should_check(p: Path) -> bool:
    if p.suffix not in (".md", ".py"):
        return False
    if set(p.parts) & SKIP_PARTS:
        return False
    if ".claude" in p.parts:                       # 见 docstring 末行
        return False
    rel = relpath_of(p)
    if rel.startswith("docs/复盘/") or p.name == "CHANGELOG.md":
        return False                               # 历史记录：明文不改写，提醒无意义
    if rel.startswith(".claude/worktrees/"):
        return False
    return True


def has_evidence(text: str) -> bool:
    """文本里有没有**一条能打印出来的命令** —— 只在代码块 / 行内代码里找。"""
    for m in CODE_SPAN_RE.finditer(text):
        span = m.group(0)
        if any(w in span for w in CMD_WORDS):
            return True
    return False


def claims_in(text: str) -> list:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if any(r.search(line) for r in CLAIM_RES):
            hits.append((i, line.strip()[:100]))
    return hits


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # 拿不到输入就静默退出，⛔ 别给主流程添乱

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        return 0

    # 这次【新写进去】的那段文本 —— Edit 给 new_string，Write 给 content。
    new_text = ti.get("new_string") or ti.get("content") or ""
    if not new_text:
        return 0

    p = Path(fp)
    if not should_check(p):
        return 0
    if BYPASS in new_text:                         # ← 专用旁路，见 docstring
        return 0

    hits = claims_in(new_text)
    if not hits:
        return 0                                   # ← 绝大多数编辑走到这里

    # 证据可以在这段里，也可以在该文件的别处（编辑往往只给一小段）。
    evidence = has_evidence(new_text)
    if not evidence:
        try:
            evidence = has_evidence(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            evidence = False
    if evidence:
        return 0

    rel = relpath_of(p)
    print(f"🟡 **规则 1 提醒** —— `{rel}` 这次写入里有 **{len(hits)} 处全称否定**，"
          f"但**没看到任何命令**：\n")
    for ln, txt in hits[:3]:
        print(f"   · 第 {ln} 行：{txt}")
    if len(hits) > 3:
        print(f"   · …另有 {len(hits) - 3} 处")
    print()
    print("   ⇒ 全称否定**没法用「我看到过」证明**，只能靠**穷举** ——"
          "判据是**一条能打印出来的命令**（`grep -n` / `ls` / `curl`），**把输出贴进结论里**。")
    print("   ⇒ ⚠️ 若这句是在【引用 / 讨论】这条规则 ⇒ 在文本里带上「全称否定」四个字即静默。")
    print("   📄 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md` §二 规则 1 ·"
          " `docs/规范/开发规范.md` §3.2 规则 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
