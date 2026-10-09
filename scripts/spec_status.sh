#!/usr/bin/env bash
#
# spec_status.sh —— **对账**：`app/` 的模块 ↔ **它自己目录下 `specs/` 里的** spec
# 🔴 2026-10-09（段 2）：spec 已**随模块搬进** `app/<组>/specs/`，⛔ 不再是集中的 `docs/specs/`。
#
# ## 它回答一个问题
#
# > **「有什么、没有什么、还缺什么模块？」**
#
# 本仓原先只有 `ROADMAP` 的**功能现状表**（按**功能**排），
# 但**没有一个地方能回答"这个模块做到哪了"** —— 要读代码才知道。
#
# ## 用法
#
#     bash scripts/spec_status.sh              # 只打对账结果
#     bash scripts/spec_status.sh --write      # 顺带【重写】app/specs/README.md 的模块表
#     bash scripts/spec_status.sh --missing    # 只列缺 spec 的（给 hook 用）
#     bash scripts/spec_status.sh --non-modules # 只列【不是模块】的（给 pre-commit 第 ④ 道门用）
#
# ## 判据
#
# * **模块** = `app/*.py` 里**非测试、非 conftest** 的（`test_*` / `conftest` 不算产品模块）
#   ⚠️ **再减掉 `NON_MODULE_FILES`** —— 那 3 个是**手动 / 离线脚本**，不是产品模块（见下表与理由）
# * **有 spec** = **该模块自己目录下的 `specs/<模块名>.md`** 存在
#   （`app/` 根的那几个模块 —— 如 `main.py` —— 落在 `app/specs/`）
#
# ## ⚠️ 三条设计说明
#
# 1. **本脚本【不判断"做完没有"】** —— 那在 spec 文件里（人工/agent 写的）。
#    脚本只做**对账**（谁有 spec、谁没有）。**这是有意的分工**：
#    能机械判的交给脚本，判不了的（"做到哪了"）留给人。
# 2. **`README.md` 的模块表是【生成的】** —— 别手改，跑 `--write`。
#    理由同 `list_endpoints.sh`：**手写的清单必然过期**。
# 3. **它不拦任何东西** —— 拦在 `pre-commit-gates.py`（第 ④ 道门）。**本脚本只管看。**
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="report"
for a in "$@"; do
  case "$a" in
    --write)       MODE="write" ;;
    --missing)     MODE="missing" ;;
    --non-modules) MODE="nonmodules" ;;
    --skip-dirs)   MODE="skipdirs" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

python3 - "${MODE}" <<'PY'
import io, os, re, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()
# ⚠️ 这个变量只用于**模板 README** 的读写；spec 的**查找**见下面那次递归（`have`）。
SPECS = os.path.join(REPO, "app", "specs")

# ── 0. 【不是模块的 .py】── 2026-10-07 加（乙单 · `裁单-清账与spec-20261007.md` §乙-3）
# 「模块 = app/*.py」还有第二个盲区：**手动脚本 / 离线脚本**也住在 `app/` 下 ——
# 它们**不参与服务路径**、**跑法是 `python xxx.py`**（docstring 自己写着）。
# ⚠️ **给它们建 spec = 为了让计数器归零而造文档** —— 与 README 那句
#    「`spec` 列写『🔴 缺』的 … **那本身就是信息**」**正好相反**
#    （把代码转录一遍，之后还得跟着改 ⇒ **转录即负债**）。
# ⇒ 从「产品模块」里**移出**，但 **⛔ 不藏起来**：第 5 节会**单独打一行**列出它们。
#    （本仓立场：**「静默放行 = 门不存在」** —— 悄悄消失与本来就没有，在机器痕迹上一样。）
#
# 🔴 **为什么是【白名单】而不是机械规则**（2026-10-07 实测 —— ⛔ 别"顺手改成自动判"）：
#    试过「**没人 import ⇒ 不是模块**」，**被证伪**：全仓零 import 的是 **5 个**，不是 3 个 ——
#      · `browser_tools.py`   **是模块**（两个导入点都被【注释掉】了，等 chromium ⇒ 停放的能力）
#      · `tools_with_cache.py` **是模块**（业务方 2026-10-07 裁：**⛔ 不删，要接回调用链**）
#    ⇒ 机械规则把「**脚本**」与「**模块，只是没接上**」混成一类 ⇒ 只能**逐条给理由**。
NON_MODULE_FILES = {
    # ⚠️ 2026-10-09（段 2）：`preprocess.py` **已删**（`DEC-125` §2.5 ⓒ）——
    #    它是 25 行硬编码 print 脚本、零函数零调用方；真功能 `DocumentPreprocessor`
    #    已在 `app/rag/document_preprocessor.py` 且被上传链路真调用。
    "plan_constraints":    "手动实验脚本：对比不同约束下的任务规划（**会真调 LLM**）",
    "evaluate_with_ragas": "RAGAS **离线**评测脚本（有 `__main__`，不在服务路径上）",
}

# ── 1. 扫模块 ──
# 🔴 2026-10-09（模块化重构）：模块已按组收进 `app/<组>/`（core · routing · access ·
#    billing · agent · rag · tools），另加 `app/eval/` 与 `app/tests/`。
#    ⚠️ 原先那句 `os.listdir(api)` **只看一层** ⇒ 重构后只能看到
#       `main.py` / `conftest.py` / `preprocess.py` —— **那 60 个模块一个都扫不到**。
#       而本脚本的输出形态是「🔴 缺失 N 个 / ✅ 全部有」⇒ **扫到 0 个会打印成"没什么可报的"**，
#       与"确实都没问题"**长得一样**（本仓原话：「**空跑 = 静默假通过**」）。
#    ⇒ 改成**递归**，并排掉【不是产品模块】的目录：
#       `tests/`（测试）· `specs/`（不是 .py）· `static/`（前端资源）·
#       `alembic/`（迁移脚本，重构前就扫不到）· 缓存目录
_API_SKIP_DIRS = {"tests", "specs", "static", "alembic", "__pycache__",
                  "logs", ".pytest_cache", ".ruff_cache"}

mods = []
nonmods = []
for _root, _dirs, _files in os.walk(os.path.join(REPO, "app")):
    _dirs[:] = sorted(d for d in _dirs if d not in _API_SKIP_DIRS)
    for f in sorted(_files):
        if not f.endswith(".py"):
            continue
        if f.startswith("test_") or f == "conftest.py":
            continue
        p = os.path.relpath(os.path.join(_root, f), REPO)
        n = sum(1 for _ in io.open(os.path.join(REPO, p), encoding="utf-8", errors="ignore"))
        if f[:-3] in NON_MODULE_FILES:
            nonmods.append((f[:-3], p, n))
            continue
        mods.append((f[:-3], p, n))

# 🔴 防空跑：递归口径再坏一次的话，这里当场红，⛔ 不许静默变成"没什么可报的"。
if len(mods) < 40:
    print(f"🔴 防空跑：只扫到 {len(mods)} 个产品模块（预期 ≥ 40）—— 枚举口径坏了，"
          f"⛔ 下面的对账结论**不可信**。")
    raise SystemExit(2)

# ── 2. 扫 spec ──
have = {}
# 🔴 2026-10-09（段 2）：递归扫 `app/**/specs/*.md` —— **spec 与它的模块同目录**。
#    ⛔ 别改回"只看一处目录"：那正是这次重构要消的"集中索引"。
for _r, _d, _fs in os.walk(os.path.join(REPO, "app")):
    _d[:] = [x for x in _d if x != "__pycache__"]
    if os.path.basename(_r) != "specs":
        continue
    for f in _fs:
        # ⚠️ 2026-10-09（段 3）：`specs/` 目录里**也有 `CLAUDE.md`**（那是该层的索引表）
        #    ⇒ ⛔ 不排除它会**被当成一份 spec**（报成「spec 有、代码没了」的假阳性）。
        if f.endswith(".md") and f not in ("README.md", "CLAUDE.md"):
            have[f[:-3]] = os.path.relpath(os.path.join(_r, f), REPO)
# 🔴 防空跑：一份都扫不到 ⇒ 当场红（「扫不到」与「都没问题」在输出上一模一样）
if not have:
    print("🔴 防空跑：一份 spec 都没扫到 —— 枚举口径又变了，⛔ 下面的对账结论不可信。")
    raise SystemExit(2)

# ── 2b. 【非 .py 的子系统】── 2026-10-06 加（`DEC-085` 段 1 第一刀）
# 上面那句「模块 = app/*.py」原先**默认每个子系统都有 .py 入口**。前端打破了这个默认：
# 它是本仓第一个**没有 .py 模块**的子系统（代码是 `app/static/` 下的 .js / .html）。
# ⚠️ 不加这张表的话，`static_frontend.md` 会掉进下面的 `extra`
#    ⇒ 报成「🗑 spec 有、代码没了」—— 而**代码在、且是本轮新建的**。
#    README 明写这一行「应为 0」⇒ 那是**一条假警报**，比不报还坏
#    （本仓立场：「从不命中」与「没人违规」在机器痕迹上一样）。
# 判据：这张表里的 spec 名，只要它指向的路径**真的存在**，就不算残留。
NON_PY_MODULES = {"static_frontend": "app/static"}

# ── 3. 对账 ──
missing = [(m, p, n) for m, p, n in mods if m not in have]
extra   = [
    k for k in have
    if k not in {m for m, _, _ in mods}
    and not (k in NON_PY_MODULES and os.path.exists(os.path.join(REPO, NON_PY_MODULES[k])))
]
ok      = [(m, p, n) for m, p, n in mods if m in have]

# ── 3b. 白名单【自检】── ⛔ 白名单不许静默过期
# ⚠️ **为什么必须有**：白名单是**手写的** ⇒ 它会烂，而且**烂起来是静默的**。
#    本仓为此栽过（`N10` 的 `ROUTE_FILES` 写死 ⇒ 改一次代码漂一次）。
# ⇒ 两条**机械可判**的自检（**都不拦**，只报 —— 本脚本按设计不拦任何东西）：
#    ① 表里的名字**必须还在** `app/` 下（文件没了 ⇒ 白名单烂了）
#    ② 表里的名字**不许有 spec**（有 ⇒ 有人给了它"模块"待遇，两边口径打架）
# ⚠️ 2026-10-09：原先按 `app/<名>.py` **一层**判"文件还在不在" ⇒ 重构后
#    那 3 个脚本全挪了位置（`plan_constraints` → `agent/`、`evaluate_with_ragas` → `eval/`）
#    ⇒ 一律被误报成"白名单过期"。改成**拿上面那次递归扫描的结果反查**，
#    ⛔ 不再自己拼路径（拼一次就多一个会漂的口径）。
_found_nonmod = {k for k, _, _ in nonmods}
nonmod_gone     = [k for k in NON_MODULE_FILES if k not in _found_nonmod]
nonmod_conflict = [k for k in NON_MODULE_FILES if k in have]

def spec_status(name):
    """从 spec 文件里读它自报的状态（第一张表的『状态』行）"""
    p = os.path.join(REPO, have.get(name, ""))
    if not have.get(name) or not os.path.exists(p):
        return "❓ 未知"
    try:
        txt = io.open(p, encoding="utf-8").read()
    except OSError:
        return "❓ 未知"
    m = re.search(r"\*\*状态\*\*\s*\|\s*([^|\n]+)", txt) or \
        re.search(r"^\|\s*\*\*状态\*\*\s*\|(.+?)\|", txt, re.M)
    return (m.group(1).strip() if m else "（未写）")

if MODE == "missing":
    for m, p, n in missing:
        print(f"{p}")
    sys.exit(0)

if MODE == "nonmodules":
    # 给 `pre-commit-gates.py` 第 ④ 道门用 —— 见本文件顶部 §0 与 `DEC-101`。
    # 只打【模块名】，一行一个（好让调用方 `splitlines()`）。
    for m, p, n in nonmods:
        print(m)
    sys.exit(0)

if MODE == "skipdirs":
    # 🔴 2026-10-09（B1 顺带修）：**同一件事的两处实现曾经不一致** ——
    #    本脚本 `_API_SKIP_DIRS` 里**早就排掉了 `alembic/`**（"迁移脚本，重构前就扫不到"），
    #    而 `pre-commit-gates.py` 第 ④ 道门那份**内联实现没排** ⇒
    #    新增一份 alembic 迁移会被**误判成"新增模块没有 spec"**并**硬拦提交**（实测踩到）。
    #    ⇒ 这里把它**吐出来**，让门跟着同一份名单走，⛔ 而不是在门里再抄一遍
    #      （理由同 `--non-modules`：抄一份必然分叉）。
    for d in sorted(_API_SKIP_DIRS):
        print(d)
    sys.exit(0)

# ── 4. 模块表（README 用）──
rows = []
for m, p, n in sorted(mods, key=lambda x: x[0]):
    if m in have:
        # 🔴 2026-10-09（段 2）：spec 已**分散**在 8 个 `specs/` 目录里
        #    ⇒ ⛔ 不能再拼 `./{m}.md`（那是"与 README 同级"的旧假设）。
        #    改成：**标签写真实仓内路径**（断链门按它核）+ **链接写相对本 README 的路径**。
        _rel = have[m]                                  # 如 app/tools/specs/browser_tools.md
        _link = os.path.relpath(os.path.join(REPO, _rel), SPECS)
        rows.append(f"| `{p}` | {n} | ✅ [`{_rel}`]({_link}) | {spec_status(m)} |")
    else:
        rows.append(f"| `{p}` | {n} | 🔴 **缺** | ❓ 未知 |")
table = "\n".join(rows)

if MODE == "write":
    out = os.path.join(SPECS, "README.md")
    B, E = "<!-- MODULE-TABLE-BEGIN -->", "<!-- MODULE-TABLE-END -->"
    old = io.open(out, encoding="utf-8").read() if os.path.exists(out) else ""
    if B not in old or E not in old:
        print(f"⛔ README.md 里找不到 {B} / {E} 标记 —— 不重写（防手写内容被冲掉）", file=sys.stderr)
        sys.exit(1)
    # ⚠️ **必须保留表【后面】的内容** ——
    #    早期版本只写 head + 表，把 tail 整段丢了（实测把 README 从 200+ 行截到 81 行）。
    head, rest = old.split(B, 1)
    _, tail = rest.split(E, 1)
    io.open(out, "w", encoding="utf-8").write(
        head
        + B + "\n"
        + f"<!-- 本表由 `bash scripts/spec_status.sh --write` 生成 —— ⛔ 别手改 -->\n\n"
        + f"| 模块 | 行数 | spec | 自报状态 |\n|---|---:|---|---|\n{table}\n"
        + E
        + tail
    )
    print(f"✅ 已重写 app/specs/README.md 的模块表（{len(mods)} 个模块）")
    sys.exit(0)

# ── 5. 报告 ──
print(f"📋 模块 spec 对账（{len(mods)} 个产品模块）")
print()
print(f"  ✅ 有 spec        {len(ok)}")
print(f"  🔴 没 spec        {len(missing)}   ← 别人【不知道它们存在】或【不知道做到哪】")
print(f"  🗑  spec 有、代码没了 {len(extra)}   ← 模块删了，spec 残留")
if extra:
    for k in extra:
        print(f"        {have[k]}")
# ⚠️ 这一行是【显示】的，不是"通过"的：非 .py 子系统**不在上面的 ok 里**（ok 由 app/*.py 推）
#    ⇒ 不打出来就等于它**哪一档都不占**，看起来像漏了一批。
nonpy = [k for k in have if k in NON_PY_MODULES
         and os.path.exists(os.path.join(REPO, NON_PY_MODULES[k]))]
if nonpy:
    print(f"  🧩 非 .py 子系统   {len(nonpy)}   ← 没有 app/*.py 模块，代码在别处（见脚本里的 NON_PY_MODULES）")
    for k in sorted(nonpy):
        print(f"        {have[k]}  →  {NON_PY_MODULES[k]}/")
# ⚠️ 同 `nonpy`：这几个**不在上面任何一档里**（不是产品模块 ⇒ 不进 `mods`）
#    ⇒ **打了才看得见**；不打就等于**悄悄消失**。
if nonmods:
    print(f"  🧩 非模块脚本     {len(nonmods)}   ← `app/` 下的**手动 / 离线脚本**，不是产品模块（见脚本里的 NON_MODULE_FILES）")
    for m, p, n in nonmods:
        print(f"        {p:38} {n:4} 行  {NON_MODULE_FILES[m]}")
# 🔴 自检结果（见脚本里的 §3b）—— 命中即为**真问题**，不是提示
if nonmod_gone:
    print()
    print(f"  🔴 白名单过期 {len(nonmod_gone)} 个：`app/<名>.py` 已不存在 ⇒ 更新 NON_MODULE_FILES")
    for k in nonmod_gone:
        print(f"        app/{k}.py")
if nonmod_conflict:
    print()
    print(f"  🔴 口径打架 {len(nonmod_conflict)} 个：既在 NON_MODULE_FILES、又有 spec ⇒ 二者只能留一个")
    for k in nonmod_conflict:
        print(f"        {have[k]}")
print()
if missing:
    print("没 spec 的（按行数降序，前 15）：")
    for m, p, n in sorted(missing, key=lambda x: -x[2])[:15]:
        print(f"  {p:38} {n:4} 行")
PY
