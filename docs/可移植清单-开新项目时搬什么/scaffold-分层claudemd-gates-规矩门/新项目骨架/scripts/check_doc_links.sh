#!/usr/bin/env bash
#
# check_doc_links.sh —— 检查全仓 .md 里【反引号包起来的文件路径】是否真的存在
#
# ## 为什么要它
#
# **2026-09-29 一天里，"引用对不上"这一类错误犯了 4 次**：
#   ① 三处指向一份**改过名**的复盘（`没核schema…` vs 实际 `结果为空…`）
#   ② ROADMAP 里写 `归档/X.md`，但 ROADMAP 在**仓根** ⇒ 相对路径不对
#   ③ 同一处写成 `归档/待办登记-…md`（**缩写**）⇒ 点不开也核不了
#   ④ 引用了 `现状与差距.md`，而它刚被归档
#   ⇒ 复盘：`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
#
# ⛔ **靠"下次记得"解决不了** —— 这类错误**不会让任何测试变红**，
#    而且**改一处漏一处**（同一份名字写在三个文档里）。要的是**一条能跑的命令**。
#
# ## 用法
#
#     bash scripts/check_doc_links.sh            # 报 🔴 真断链（有则退出码 1）
#     bash scripts/check_doc_links.sh --all      # 四类全列
#     bash scripts/check_doc_links.sh --quiet    # 只给总数
#
# 📌 **扫描范围 = 本脚本所在的仓**（脚本按自身位置定位仓根，**换目录运行也一样**）。
#    这是**有意为之** —— 它是仓级检查器，跟着仓走，不跟着 cwd 走。
#
# ## 四类结果
#
#   ✅ 可解析   —— 目标存在
#   🟡 已归档   —— 目标**已移进归档夹** ⇒ 属预期（旧路径→新位置对照表见 `归档/README.md`）
#   ⚫ 外部/已删 —— 命中 `scripts/doc-links-ignore.txt` 的豁免（**另一个仓 / 上级仓 / 已删目录 / 历史简写**）
#   🔴 真断链   —— 以上都不是 ⇒ **要修**
#
# ## ⚠️ 两类"故意不改"，别当 bug 去修
#
#   1. **原始记录不改写** —— `CHANGELOG.md` / `docs/复盘/*` / `docs/decisions/DEC-*` 里的旧路径
#      是**历史事实** ⇒ 进 🟡 或 ⚫，**属预期**。
#   2. **豁免清单是给人审阅的** —— 加一条前先想清楚"它为什么不算缺陷"（见该文件头注释）。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="default"
for a in "$@"; do
  case "$a" in
    --all)   MODE="all" ;;
    --quiet) MODE="quiet" ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

python3 - "${MODE}" <<'PY'
import os, re, subprocess, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()

# ---------- 0. 「存在」的口径 = 【会不会随 clone 一起下来】 ----------
# 🔴 2026-10-05（`DEC-076` §2.9）：这里原先是 `os.path.exists()` —— 那是在**问磁盘**。
#    磁盘上有**没入库的东西**（`archive/`、`GIT_CHECKLIST.md` 都被 `.gitignore` 有意排除，
#    `DEC-022` 还明文写过「有意设计」）⇒ **同一个仓在两台机器上给出两个结论**：
#    本机报「✅ 没有真断链」，CI 报 **10 处**。
#    📌 实测出处：把本门接进 `ci.yml` 后**第一次跑就红了**，10 处全是"指向有意 gitignore 的内容"。
#    ⇒ 判据改成 **`git ls-files`（索引）**：那才是「克隆者拿得到什么」。
#    ⚠️ 为什么用索引而不是 HEAD：pre-commit 时刚 `git add` 的新文件**就在索引里**
#       ⇒ 新加的文件不会被误判成"不存在"。
_GIT = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
if _GIT.returncode != 0:
    print("⛔ 断链门: **无法判定** —— `git ls-files` 失败(exit %d)" % _GIT.returncode)
    print("   ⇒ 【不得当作通过】。⚠️ 本门判「存在」的口径是【会不会随 clone 一起下来】，")
    print("     那需要 git；拿不到 git ⇒ 就是拿不到判据（⛔ 不是「没有断链」）。")
    print("     常见原因：当前目录不是 git 仓 —— 例：ci-local 复制出来的树没带 .git")
    print("     （那边靠 GIT_DIR/GIT_WORK_TREE 把 git 指回主检出，见 `DEC-076` §2.8）。")
    sys.exit(2)
TRACKED = set(_GIT.stdout.decode("utf-8", "surrogateescape").split("\0"))
TRACKED.discard("")

def tracked(path):
    """这个路径**会不会随 clone 一起下来** —— ⛔ 不是「磁盘上有没有」。"""
    rel = os.path.relpath(path, REPO)
    return (not rel.startswith("..")) and (rel.replace(os.sep, "/") in TRACKED)

# ---------- 1. 收集 .md ----------
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "venv",
             "venv-ragas", ".venv", ".mypy_cache", "htmlcov"}

# 🔴 2026-10-01：**必须再按【路径前缀】排掉 `.claude/worktrees/`**。
#    worktree(`git worktree add`)是**整仓的一份副本** —— 不排掉的话,主检出扫自己时
#    会把这 141 份副本当成自己的文档,后果是**两个方向都错**：
#      · 副本里那些**旧路径**被报成 🔴 真断链（实测 7 条,**全部**来自副本）
#        ⇒ 门永远非 0 ⇒ `pre-commit-gates.py` 的钩子 `return 2` ⇒ **拦住全仓任何 commit**;
#      · 副本还会把文件名灌进下面的 `alive` 索引 ⇒ **反过来掩盖真问题**
#        （正是本文件 :73 那条警告说的失败模式 —— 索引被副本稀释）。
#    ⚠️ **排的是 `.claude/worktrees/` 这个前缀,⛔ 不是整个 `.claude/`** ——
#       `.claude/README.md` · `.claude/commands/handoff.md` · `commands/specs.md`
#       是**已入库、该继续查**的（共 3 份）。⚠️ 也不能往 `SKIP_DIRS` 里塞 `"worktrees"`
#       —— 那是**按目录名**匹配,会连带排掉仓里任何叫 worktrees 的真目录。
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


docs = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = prune(dirs, root)
    for f in files:
        # ⚠️ 只扫【入了库】的 .md —— 与下面的存在性口径保持一致（见 §0）。
        #    否则本机会去扫那些"只有本机有"的文档（`archive/` 等）⇒ 又是一种口径不一致。
        if f.endswith(".md") and tracked(os.path.join(root, f)):
            docs.append(os.path.join(root, f))
docs.sort()

# ---------- 2. 文件名索引 ----------
ARCHIVE_DIRNAMES = {"归档", "archive"}
# ⚠️ 通用文件名不做 basename 匹配 —— 否则 `归档/README.md` 会被错误地"解析"到
#    根 `archive/README.md`，**反而掩盖了真问题**（2026-09-29 实测踩过）。
GENERIC_NAMES = {"README.md", "readme.md", "index.md", "CLAUDE.md", "LICENSE.md"}

archived = {}      # basename -> 归档夹里的路径（🟡）
alive = {}         # basename -> 仓里任何位置的路径（⚫ 名字提及，非路径）
for root, dirs, files in os.walk(REPO):
    dirs[:] = prune(dirs, root)
    in_archive = os.path.basename(root) in ARCHIVE_DIRNAMES
    for f in files:
        if not f.endswith(".md") or f in GENERIC_NAMES:
            continue
        full = os.path.join(root, f)
        # ⚠️ 索引同样只收【入了库】的 —— 否则"名字提及"那一档会被**本机独有的文件**喂饱，
        #    反过来掩盖真问题（与 §0 同一条理由）。
        if not tracked(full):
            continue
        if in_archive:
            archived.setdefault(f, full)
        else:
            alive.setdefault(f, full)

# ---------- 3. 读豁免清单 ----------
# 两种写法：
#   普通正则          → 匹配【候选路径】
#   `@file:正则`      → 匹配【来源文件】⇒ 整份豁免（用于纯历史记录）
IGNORE_FILE = os.path.join(REPO, "scripts", "doc-links-ignore.txt")
cand_pats, file_pats = [], []
if os.path.exists(IGNORE_FILE):
    with open(IGNORE_FILE, encoding="utf-8") as fh:
        for ln in fh:
            # ⚠️ 顺序要紧：**先跳过整行注释，再去行尾注释**。
            #   （2026-09-29 实测踩过：把这两步搞反了 ⇒ 注释行被当成正则编译，
            #     里面一个 `**` 就触发 `re.PatternError: multiple repeat`，**整份检查器挂掉**。）
            if ln.lstrip().startswith("#"):
                continue
            ln = re.sub(r"\s+#.*$", "", ln).strip()   # 行尾注释
            if not ln:
                continue
            try:
                pat = (file_pats if ln.startswith("@file:") else cand_pats)
                pat.append(re.compile(ln[len("@file:"):] if ln.startswith("@file:") else ln))
            except re.error as e:
                print(f"❌ 豁免清单里有条正则写错了，跳过：{ln!r} → {e}", file=sys.stderr)
else:
    print(f"⚠️  没找到豁免清单 {IGNORE_FILE} —— 外部引用会全部落进 🔴", file=sys.stderr)

def is_ignored(cand, src_rel):
    return (any(p.search(cand) for p in cand_pats)
            or any(p.search(src_rel) for p in file_pats))

# ---------- 4. 扫描 ----------
SPAN = re.compile(r"`([^`\n]+)`")
# 宽松匹配：任何不含空白/反引号/引号/括号/中文标点的串，以 .md 结尾
# （⚠️ 要紧的是**别漏** `第①②步.md` 这种带全角数字的 —— 早期版本用 CJK 范围限定，漏了它）
CAND = re.compile(r"""[^\s`"'|<>()\[\]，。、；：*]+?\.md""")
TAIL = re.compile(r"^(.*?\.md)(?::\d+)?(?:\s*§.*)?$")

buckets = defaultdict(list)

for d in docs:
    rel_self = os.path.relpath(d, REPO)
    try:
        with open(d, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        continue

    for lineno, line in enumerate(lines, 1):
        for span in SPAN.findall(line):
            if ".md" not in span:
                continue
            for raw in CAND.findall(span):
                m = TAIL.match(raw)
                cand = (m.group(1) if m else raw).strip()
                if not cand:
                    continue

                p_local = os.path.normpath(os.path.join(os.path.dirname(d), cand))
                p_root = os.path.normpath(os.path.join(REPO, cand))
                p_strip = None
                if cand.startswith("fastapi-rag-agent/"):
                    p_strip = os.path.normpath(os.path.join(REPO, cand.split("/", 1)[1]))

                hit = next((p for p in (p_local, p_root, p_strip)
                            if p and tracked(p)), None)
                base = os.path.basename(cand)
                if hit:
                    buckets["ok"].append((rel_self, lineno, cand, ""))
                elif base in archived:
                    buckets["archived"].append((rel_self, lineno, cand, archived[base]))
                elif base in alive:
                    # ⭐ **文件名在仓里存在，只是没写全路径** ⇒ 这是「**名字提及**」，不是断链。
                    #    例：「原来在仓根（`deploy.md`）」「（`接口契约.md` · `运维.md`）」
                    #    ⚠️ **判据**：读者**按名字能搜到** ⇒ 不是"点开是空的"。
                    buckets["nameref"].append((rel_self, lineno, cand, alive[base]))
                elif is_ignored(cand, rel_self):
                    buckets["external"].append((rel_self, lineno, cand, ""))
                else:
                    buckets["broken"].append((rel_self, lineno, cand, ""))

ok, arch, nameref, ext, bad = (buckets["ok"], buckets["archived"],
                               buckets["nameref"], buckets["external"],
                               buckets["broken"])

def show(title, items, with_target=False):
    if not items:
        return
    print(f"\n{title}（{len(items)}）")
    seen = set()
    for f, ln, cand, extra in items:
        key = (f, cand)
        if key in seen:
            continue
        seen.add(key)
        suffix = f"  ⇒ {os.path.relpath(extra, REPO)}" if (with_target and extra) else ""
        print(f"   {f}:{ln}  `{cand}`{suffix}")

print(f"扫描 {len(docs)} 份 .md")
print(f"  ✅ 可解析     {len(ok)}")
print(f"  🟡 已归档     {len(arch)}   （目标在归档夹 ⇒ 属预期）")
print(f"  ⚪ 名字提及   {len(nameref)}   （只写了文件名，但**该名字在仓里存在** ⇒ 搜得到）")
print(f"  ⚫ 外部/已删  {len(ext)}   （豁免清单：另一个仓 / 上级仓 / 已删目录 / 历史简写）")
print(f"  🔴 真断链     {len(bad)}")

if MODE == "all":
    show("🟡 已归档（**属预期，不用改**）", arch, with_target=True)
    show("⚪ 名字提及（**不是缺陷** —— 名字搜得到，只是没写全路径）", nameref, with_target=True)
    show("⚫ 外部/已删（豁免清单命中）", ext)
    show("✅ 可解析", ok)
elif MODE != "quiet":
    show("🟡 已归档（**属预期**）", arch, with_target=True)

if bad:
    show("🔴 真断链（**这些要修**）", bad)

    # 🔴 把【最常见的**那一类**】单独点出来 —— 它已经**连栽 4 次**（都在同一个仓里）。
    #
    #    这类"断链"**不是路径写错了**，而是把 **markdown 的简写 / 通配**写进了反引号：
    #      `{a,b}` = 二选一 · `<组>` = 占位 · `…` = 省写 —— **读的人一眼懂**，
    #      而**本门只会拿它去 `stat()`** ⇒ 必然找不到 ⇒ 报成「真断链」。
    #
    #    ⚠️ 为什么把提示放在**这里**而不是写进某份规范：那些仓的原话「**只有文字就漏**」。
    #       这行会出现在**每一次**这类红的现场；写在文档里等人去翻，就是第 5 次的开始。
    #    ⛔ 也**别**去动 `doc-links-ignore.txt` —— 那不是"已知的债"，是**这次真的写错了**。
    SHORTHAND = re.compile(r"[{}<>*|]|\.\.\.|…")
    sh = [(f, ln, cand) for (f, ln, cand, _extra) in bad if SHORTHAND.search(cand)]
    if sh:
        print(f"\n⚠️ 上面有 {len(sh)} 条**看着像「路径不存在」，其实是【markdown 简写/通配】被当成路径了**：")
        for f, ln, cand in sh[:6]:
            print(f"   {f}:{ln}  `{cand}`")
        print('   ⇒ 读的人一眼懂（`{a,b}` = 二选一 · `<组>` = 占位 · `…` = 省写），')
        print('     而本门只会拿它去 `stat()` ⇒ 必然找不到。')
        print('   ⇒ **修法：拆成【一条一条列出来】**，或改用【文字】描述。')

    print(f"\n❌ 有 {len(bad)} 处真断链。")
    sys.exit(1)

print("\n✅ 没有真断链。")
PY
