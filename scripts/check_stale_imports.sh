#!/usr/bin/env bash
#
# check_stale_imports.sh —— 过期导入门（`app/` **之外**的 .py 里，指向「已搬家的模块」的 import）
#
# ## 为什么有它（`N21` · 2026-10-09）
#
# 当天 `#123` 模块化重构把 60 个平铺模块拆进 7 个模块组（`api/` 还改名成了 `app/`），
# **静默打断了两个活工具**：
#
#     scripts/issue_api_key.py        from auth import …            ⇒ 现在是 access.auth
#     scripts/check_corpus_dedup.py   API_DIR = REPO_ROOT / "api"   ⇒ 现在是 app/
#                                     from chunker import …         ⇒ 现在是 rag.chunker
#
# 🔴 **两道防线都不管它**：
#   · **913 条 pytest 照不到** —— 脚本不在 `app/tests/` 采集范围里；
#   · **CI 的 `compileall` 照不到** —— 它**只查语法**，而这是**导入期**错。
#
# ⚠️ **其中一个是【发凭据】的那把工具** —— 它坏了等于"进不去系统"。
# 📄 复盘 ⇒ `docs/复盘/2026-10-09-测试全绿而活路径坏了两次.md`
#
# ## 判据
#
# 对 `app/` 之外的每个 `.py`，解出它的 `import`：
#   * 裸名 `X` **还在 `app/` 根** ⇒ 正常
#   * 裸名 `X` 是**模块组名**（`rag` / `core` / `access` …） ⇒ 正常
#   * 裸名 `X` **搬到了某一组下面**（且 `app/` 根下已无 `X.py`） ⇒ 🔴 **过期**
#
# ## 三态（照本仓惯例）
#
#     0 = 没有过期导入 · 1 = **有** · **2 = 判不了**（⛔ 不算通过）
#
# ⚠️ **判不了必须与「干净」分开** —— 本仓为此栽过（`check_dep_vulns.sh` 曾把"网络超时"
#    报成"有已知漏洞"）。这里判不了的情形：拿不到 git / `app/` 不在 / 一个模块组都找不出来。
#
# ## 扫描范围
#
# 🔴 **只看【入库了】的 `.py`** —— 走 `git ls-files`，与**断链门 / 孤儿门同一口径**
# （「那才是**克隆者拿得到什么**」）。⇒ `venv/` · `venv-ragas/` · `node_modules/` ·
# `.claude/worktrees/` **自动全排除**（它们本来就不入库）。
#
# ⚠️ **2026-10-09 实测教训**：本门初稿按**目录名**跳过，结果**漏了 `venv-ragas/`**
#    （本仓有**第二个**虚拟环境）⇒ 扫了 **7870** 个文件而不是 13 个。
#    **「按目录名列举」永远会漏** —— 这就是改用索引的理由。
#
# **仍要显式豁免的两类**（它们在索引里，但**确实可以烂着**）：
#   · `archive/`      —— 归档 = 留痕，⛔ 不改（同 `docs/` 那三条「原始记录不改写」）
#   · 文件名含「探针」 —— 探针是一次性的（`fastapi-rag-agent-TODO待办/CLAUDE.md`），⛔ 不维护
#
# ## ⚠️ 它【不覆盖】什么（⛔ 别读成"搬家的坑都堵了"）
#
# * **只查 `import`，不查字符串里的路径** —— 同一次重构还留下过
#   `API_DIR = REPO_ROOT / "api"`（`api/` 已改名 `app/`）那种**路径**陈旧。
#   那种要另一条判据（拿字符串猜路径**误报太高**，本门**故意不猜**）。
# * **只查 `app/` 之外的 `.py`** —— `app/` 内部的过期导入由 `ruff`（`E9`/`F`）与 pytest 兜。
#
# ## 用法
#
#     bash scripts/check_stale_imports.sh        # 跑门（0 / 1 / 2）
#     bash scripts/test_check_stale_imports.sh   # 自测（7 条，含"判不了必须是 2"的正例）
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO}/venv/bin/python"
[ -x "${PY}" ] || PY="$(command -v python3)"

# ⚠️ heredoc **必须加引号**（`<<'PY'`）—— 不加引号时正文里的反引号会被 shell **真执行**
#    （本仓 2026-10-05 / 2026-10-09 两次栽过，见 `~/.claude` 记忆与 `docs/复盘/`）。
"${PY}" - "${REPO}" <<'PY'
import ast, pathlib, subprocess, sys

SKIP_TOP_DIRS = {"app", "archive"}     # 理由见脚本头 —— ⛔ 加一条就要写清为什么
SKIP_NAME_CONTAINS = ("探针",)

repo = pathlib.Path(sys.argv[1]).resolve()
app = repo / "app"

if not app.is_dir():
    print(f"⛔ 过期导入门: **无法判定** —— 找不到 {app}", file=sys.stderr)
    raise SystemExit(2)

groups = {d.name for d in app.iterdir() if d.is_dir() and d.name.isidentifier()}
if not groups:
    print("⛔ 过期导入门: **无法判定** —— app/ 下一个模块组都没找到", file=sys.stderr)
    raise SystemExit(2)

moved: dict = {}
for g in sorted(groups):
    for p in (app / g).glob("*.py"):
        if p.stem != "__init__":
            moved.setdefault(p.stem, []).append(f"{g}.{p.stem}")

app_root = {p.stem for p in app.glob("*.py")}
app_root.discard("__init__")


def bare_imports(path: pathlib.Path):
    """解出该文件里的【裸名】导入（`from X import` / `import X`）。

    ⚠️ 用 `ast` ⛔ 不用正则 —— 正则会把**注释与 docstring 里**的同一行也算进去。
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add((a.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:      # ⛔ 跳过相对导入
                out.add((node.module.split(".")[0], node.lineno))
    return out


ls = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=repo, capture_output=True)
if ls.returncode != 0:
    print("⛔ 过期导入门: **无法判定** —— `git ls-files` 失败"
          f"（exit {ls.returncode}）：{ls.stderr.decode(errors='replace')[:200]}", file=sys.stderr)
    raise SystemExit(2)

findings, scanned, unparsed = [], 0, []
for raw in ls.stdout.decode(errors="replace").split("\0"):
    if not raw:
        continue
    rel = pathlib.Path(raw)
    if rel.parts[0] in SKIP_TOP_DIRS:
        continue
    if any(s in rel.name for s in SKIP_NAME_CONTAINS):
        continue
    scanned += 1
    try:
        imports = bare_imports(repo / rel)
    except SyntaxError:
        unparsed.append(str(rel))
        continue
    for name, lineno in sorted(imports, key=lambda t: t[1]):
        if name in app_root or name in groups:
            continue                        # 还在 app/ 根 / 本来就是组名 ⇒ 正常
        if name in moved:
            findings.append((rel, lineno, name, moved[name]))

print("[过期导入] 扫【入库的】app/ 之外的 .py"
      "（清单来自 `git ls-files`；跳过 archive / 探针 —— 理由见脚本头）…")
if unparsed:
    print(f"  ⚠️ 有 {len(unparsed)} 个文件 **解析不了**（语法错），已跳过 ⇢ {', '.join(unparsed[:3])}")

if not findings:
    print(f"✅ 过期导入门通过 —— 扫了 {scanned} 个文件，没有【模块搬家了但导入没改】的。")
    raise SystemExit(0)

print(f"\n🔴 发现 {len(findings)} 处【模块搬家了但导入没改】——"
      "**它们一跑就 ImportError**（而 pytest 与 compileall 都照不到）：\n")
for rel, lineno, name, new in findings:
    hint = new[0] if len(new) == 1 else f"（⚠️ 多处同名：{', '.join(new)}）"
    print(f"  {rel}:{lineno}   from {name} import …   ⇒ 现在在 {hint}")
print("\n📌 修法：把 import 改成**新的绝对形式**（根是 `app/`），"
      "并在那一行附近写清「⛔ 别用 pytest 当这条的凭证」。")
print("📄 背景 ⇒ docs/复盘/2026-10-09-测试全绿而活路径坏了两次.md")
raise SystemExit(1)
PY
