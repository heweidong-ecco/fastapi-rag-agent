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
import os, re, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()

# ---------- 1. 收集 .md ----------
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "venv",
             "venv-ragas", ".venv", ".mypy_cache", "htmlcov"}
docs = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if f.endswith(".md"):
            docs.append(os.path.join(root, f))
docs.sort()

# ---------- 2. 已归档文件索引：basename -> 路径 ----------
ARCHIVE_DIRNAMES = {"归档", "archive"}
# ⚠️ 通用文件名不做 basename 匹配 —— 否则 `归档/README.md` 会被错误地"解析"到
#    根 `archive/README.md`，**反而掩盖了真问题**（2026-09-29 实测踩过）。
GENERIC_NAMES = {"README.md", "readme.md", "index.md", "CLAUDE.md", "LICENSE.md"}
archived = {}
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    if os.path.basename(root) in ARCHIVE_DIRNAMES:
        for f in files:
            if f not in GENERIC_NAMES:
                archived.setdefault(f, os.path.join(root, f))

# ---------- 3. 读豁免清单 ----------
# 两种写法：
#   普通正则          → 匹配【候选路径】
#   `@file:正则`      → 匹配【来源文件】⇒ 整份豁免（用于纯历史记录）
IGNORE_FILE = os.path.join(REPO, "scripts", "doc-links-ignore.txt")
cand_pats, file_pats = [], []
if os.path.exists(IGNORE_FILE):
    with open(IGNORE_FILE, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if ln.startswith("@file:"):
                file_pats.append(re.compile(ln[len("@file:"):]))
            else:
                cand_pats.append(re.compile(ln))
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
                            if p and os.path.exists(p)), None)
                if hit:
                    buckets["ok"].append((rel_self, lineno, cand, ""))
                elif os.path.basename(cand) in archived:
                    buckets["archived"].append((rel_self, lineno, cand,
                                                archived[os.path.basename(cand)]))
                elif is_ignored(cand, rel_self):
                    buckets["external"].append((rel_self, lineno, cand, ""))
                else:
                    buckets["broken"].append((rel_self, lineno, cand, ""))

ok, arch, ext, bad = (buckets["ok"], buckets["archived"],
                      buckets["external"], buckets["broken"])

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
print(f"  ⚫ 外部/已删  {len(ext)}   （豁免清单：另一个仓 / 上级仓 / 已删目录 / 历史简写）")
print(f"  🔴 真断链     {len(bad)}")

if MODE == "all":
    show("🟡 已归档（**属预期，不用改**）", arch, with_target=True)
    show("⚫ 外部/已删（豁免清单命中）", ext)
    show("✅ 可解析", ok)
elif MODE != "quiet":
    show("🟡 已归档（**属预期**）", arch, with_target=True)

if bad:
    show("🔴 真断链（**这些要修**）", bad)
    print(f"\n❌ 有 {len(bad)} 处真断链。")
    sys.exit(1)

print("\n✅ 没有真断链。")
PY
