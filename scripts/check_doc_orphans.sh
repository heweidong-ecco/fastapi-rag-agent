#!/usr/bin/env bash
#
# check_doc_orphans.sh —— 查「孤儿文档」：**建了，但没人指向它**
#
# ## 为什么要它（这不是"再查一遍链接"，是查另一个东西）
#
# `check_doc_links.sh` 查的是「**指向别人的链接对不对**」；
# 本脚本查的是「**有没有人指向我**」—— **方向相反**。
#
# 🔴 立它的直接原因（2026-09-29）：
#   **`docs/文档地图.md` 建好了，但 `README` / `ROADMAP` / `CLAUDE` 三个入口【都没指向它】。**
#   ⇒ **索引挂在没人经过的地方 = 不存在。**
#   ⇒ 复盘：`docs/复盘/2026-09-29-用我做过了当别人找得到.md`（规则 2）
#
# ⭐ 本仓对这件事有**明文纪律**：「**门挂在别处，就等于没有门**」
#   （`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）——
#   ⚠️ **而那条纪律一直写在 `CLAUDE.md` 里，每遍都读，还是犯了。**
#   ⇒ **所以这条要【做成命令】，不能只写在文档里。**
#
# ## 用法
#
#     bash scripts/check_doc_orphans.sh            # 报告孤儿（有则退出码 1）
#     bash scripts/check_doc_orphans.sh --quiet    # 只给总数
#
# ## 判据
#
# **「应该被找到」的文档**（`docs/` 下的 契约/说明/原理/规范 四层 + 根级入口文件）
# **至少要在另一个 `.md` 里出现过**（按文件名匹配）。
#
# ⚠️ **不检查 `docs/decisions/` `docs/复盘/` `docs/历史/`** ——
# 那三层是**按集合引用**的（"36 份 DEC"），逐条要求被指向不现实。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="default"
[ "${1:-}" = "--quiet" ] && MODE="quiet"

python3 - "${MODE}" <<'PY'
import os, re, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "venv",
             "venv-ragas", ".venv", "archive"}

# ── 1. 收集全部 .md ──
docs = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if f.endswith(".md"):
            docs.append(os.path.relpath(os.path.join(root, f), REPO))

# ── 2. 「应该被找到」的 = docs/ 下四层 + 根级入口 ──
LAYERS = ("docs/契约/", "docs/说明/", "docs/原理/", "docs/规范/")
# ⚠️ 不查这三层（按集合引用）：见脚本头注释
EXEMPT_DIRS = ("docs/decisions/", "docs/复盘/", "docs/历史/",
               "fastapi-rag-agent-TODO待办/归档/")

def must_be_found(d):
    if d.startswith(EXEMPT_DIRS):
        return False
    if d.startswith(LAYERS):
        return True
    # 根级入口文件
    if "/" not in d and d not in ("CLAUDE.md", "README.md", "ROADMAP.md",
                                  "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md"):
        return False
    return d in ("CONTRIBUTING.md", "SECURITY.md", "docs/文档地图.md")

KEY_TARGETS = ["docs/文档地图.md", "ROADMAP.md", "CLAUDE.md"]

# ⚠️ 索引要覆盖【候选 + 关键入口】两类目标 ——
#    早期版本只用 candidates 建索引，导致 ROADMAP/CLAUDE 永远"没人指向"（**假阳性**）。
WATCH = sorted(set([d for d in docs if must_be_found(d)]) | set(KEY_TARGETS))
candidates = [d for d in WATCH if must_be_found(d)]

# ── 3. 建「谁被提到了」索引（键 = 文件名）──
mentioned = defaultdict(set)     # basename -> {引用了它的文件}
entried = set()
for d in docs:
    if d.startswith("fastapi-rag-agent-TODO待办/归档/"):
        continue                  # 归档不参与（冻结）
    try:
        txt = open(d, encoding="utf-8", errors="ignore").read()
    except OSError:
        continue
    entried.add(d)
    for other in WATCH:
        if other == d:
            continue
        base = os.path.basename(other)
        if base in txt:
            mentioned[base].add(d)

# ── 4. 报告孤儿 ──
orphans = [d for d in candidates if not mentioned.get(os.path.basename(d))]

print(f"扫描 {len(docs)} 份 .md（其中「应该被找到」的 {len(candidates)} 份）")

# 额外：几个【关键入口】必须被指向（这一条最要紧）
ENTRIES = ["README.md", "CLAUDE.md", "ROADMAP.md"]
key_problems = []
for k in KEY_TARGETS:
    base = os.path.basename(k)                 # ⚠️ 索引的键是【文件名】，不是路径
    if not mentioned.get(base):
        key_problems.append(f"{k} —— 【没有任何文档指向它】")
    elif k == "docs/文档地图.md":
        pointing = mentioned[base] & set(ENTRIES)
        if len(pointing) < 2:
            key_problems.append(
                f"docs/文档地图.md —— 只有 {sorted(pointing) or '无'} 指向它"
                f"（要求 3 个入口里至少 2 个）")

if key_problems:
    print("\n🔴 【关键入口】没被指向（这些最要紧）：")
    for p in key_problems:
        print(f"   {p}")

if orphans:
    print(f"\n🟡 孤儿文档（{len(orphans)} 份 —— 没有别的 .md 提到它）：")
    if MODE != "quiet":
        for d in sorted(orphans):
            print(f"   {d}")
else:
    print("\n✅ 没有孤儿文档。")

if orphans or key_problems:
    print("\n📌 处置：把它加进 `docs/文档地图.md`（那是索引），或确认它确实不需要被找到。")
    print("   判据与理由见 docs/规范/开发规范.md §3.1 / §3.2 规则 2")
    sys.exit(1)

print("✅ 全部有归属。")
PY
