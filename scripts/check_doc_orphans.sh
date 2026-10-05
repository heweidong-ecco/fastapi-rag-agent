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
# ──────────────────────────────────────────────────────────────────
# 🔴 2026-10-05（批 4 · `DEC-076` §5.2 第 2 / 4 条 · `DEC-080`）：**口径与断链门对齐**
#
# **改前**：本门用**裸 `os.walk`** 遍历磁盘，不加任何剪枝 ⇒ 两个后果：
#
#   ① **会把 `.claude/worktrees/` 下的整仓副本当成自己的文档** ——
#      `git worktree add` 出来的每份副本都是**一整棵树**；主检出扫自己时把它们也扫了。
#      （断链门 2026-10-01 就因为这个栽过：副本里的旧路径被报成 🔴，**门永远非 0**，
#        而 `pre-commit-gates.py` 会 `return 2` ⇒ **拦住全仓任何 commit**。）
#      ⇒ 本门当时**没跟着修**（它只是"多算了"，不像断链门那样当场拦人 ⇒ 没人发现）。
#   ② **会把「只有本机有、没入库」的 .md 当数据源** ⇒ **同一份仓，两台机器给两个结论**
#      —— 正是 `DEC-076` §2.9 给断链门定性的那个形状。
#
# **改后**：与 `check_doc_links.sh` **逐条同构**：
#   · 「存在 / 算不算数」的口径 = **`git ls-files`（问"克隆者拿得到什么"），⛔ 不是问磁盘**；
#   · `.claude/worktrees/` 按**路径前缀**剪枝（⛔ 不是往 `SKIP_DIRS` 里塞 `worktrees` ——
#     那是**按目录名**匹配，会连带排掉仓里任何叫 worktrees 的真目录）；
#   · **拿不到 git ⇒ `exit 2`【不得当作通过】**（⛔ 不许把"没能判定"压成"没有孤儿"）。
#
# 📌 判据（可打印）：`bash scripts/test_check_doc_orphans.sh`（**6 条**）
#    —— 其中 T2「未入库的目标不算数」与 T4「拿不到 git ⇒ exit 2」就是本轮新增的两条口径。
# ──────────────────────────────────────────────────────────────────
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="default"
[ "${1:-}" = "--quiet" ] && MODE="quiet"

python3 - "${MODE}" <<'PY'
import os, subprocess, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "venv",
             "venv-ragas", ".venv", "archive"}

# ---------- 0. 「算不算数」的口径 = 【会不会随 clone 一起下来】 ----------
# 与 `check_doc_links.sh` 同一口径、同一写法（见本文件头部 2026-10-05 那段）。
_GIT = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
if _GIT.returncode != 0:
    print("⛔ 孤儿门: **无法判定** —— `git ls-files` 失败(exit %d)" % _GIT.returncode)
    print("   ⇒ 【不得当作通过】。⚠️ 本门判「这份文档算不算数」的口径是")
    print("     【会不会随 clone 一起下来】，那需要 git；拿不到 git ⇒ 拿不到判据")
    print("     （⛔ 不是「没有孤儿」）。")
    print("     常见原因：当前目录不是 git 仓 —— 例：ci-local 复制出来的树没带 .git")
    print("     （那边靠 GIT_DIR/GIT_WORK_TREE 把 git 指回主检出，见 `DEC-076` §2.8）。")
    sys.exit(2)
TRACKED = set(_GIT.stdout.decode("utf-8", "surrogateescape").split("\0"))
TRACKED.discard("")


def tracked(path):
    """这个路径**会不会随 clone 一起下来** —— ⛔ 不是「磁盘上有没有」。"""
    rel = os.path.relpath(path, REPO)
    return (not rel.startswith("..")) and (rel.replace(os.sep, "/") in TRACKED)


# `.claude/worktrees/` = `git worktree add` 出来的整仓副本 ⇒ 必须按【路径前缀】排掉。
# ⚠️ 排的是 `.claude/worktrees/` 这个前缀，⛔ 不是整个 `.claude/`（`.claude/README.md` 等
#    是**已入库、该继续查**的）。也不能往 SKIP_DIRS 里塞 "worktrees"（那是按目录名匹配）。
WORKTREES_DIR = os.path.join(REPO, ".claude", "worktrees")


def prune(dirs, root):
    """给 `os.walk` 用的目录剪枝 —— **两处 walk 必须共用它**（漏一处就是半修）。"""
    out = []
    for d in dirs:
        if d in SKIP_DIRS:
            continue
        full = os.path.join(root, d)
        if full == WORKTREES_DIR or full.startswith(WORKTREES_DIR + os.sep):
            continue
        out.append(d)
    return out


# ── 1. 收集全部【入了库的】.md ──
docs = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = prune(dirs, root)
    for f in files:
        if f.endswith(".md") and tracked(os.path.join(root, f)):
            docs.append(os.path.relpath(os.path.join(root, f), REPO))
docs.sort()

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
