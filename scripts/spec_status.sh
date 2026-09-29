#!/usr/bin/env bash
#
# spec_status.sh —— **对账**：`api/` 的模块 ↔ `docs/specs/` 的 spec
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
#     bash scripts/spec_status.sh --write      # 顺带【重写】docs/specs/README.md 的模块表
#     bash scripts/spec_status.sh --missing    # 只列缺 spec 的（给 hook 用）
#
# ## 判据
#
# * **模块** = `api/*.py` 里**非测试、非 conftest** 的（`test_*` / `conftest` 不算产品模块）
# * **有 spec** = `docs/specs/<模块名>.md` 存在
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
    --write)   MODE="write" ;;
    --missing) MODE="missing" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

python3 - "${MODE}" <<'PY'
import io, os, re, sys
from collections import defaultdict

MODE = sys.argv[1]
REPO = os.getcwd()
SPECS = os.path.join(REPO, "docs", "specs")

# ── 1. 扫模块 ──
mods = []
for f in sorted(os.listdir(os.path.join(REPO, "api"))):
    if not f.endswith(".py"):
        continue
    if f.startswith("test_") or f == "conftest.py":
        continue
    p = os.path.join("api", f)
    n = sum(1 for _ in io.open(os.path.join(REPO, p), encoding="utf-8", errors="ignore"))
    mods.append((f[:-3], p, n))

# ── 2. 扫 spec ──
have = {}
if os.path.isdir(SPECS):
    for f in os.listdir(SPECS):
        if f.endswith(".md") and f != "README.md":
            have[f[:-3]] = f

# ── 3. 对账 ──
missing = [(m, p, n) for m, p, n in mods if m not in have]
extra   = [k for k in have if k not in {m for m, _, _ in mods}]
ok      = [(m, p, n) for m, p, n in mods if m in have]

def spec_status(name):
    """从 spec 文件里读它自报的状态（第一张表的『状态』行）"""
    p = os.path.join(SPECS, have.get(name, ""))
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

# ── 4. 模块表（README 用）──
rows = []
for m, p, n in sorted(mods, key=lambda x: x[0]):
    if m in have:
        rows.append(f"| `{p}` | {n} | ✅ [`specs/{m}.md`](./{m}.md) | {spec_status(m)} |")
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
    print(f"✅ 已重写 docs/specs/README.md 的模块表（{len(mods)} 个模块）")
    sys.exit(0)

# ── 5. 报告 ──
print(f"📋 模块 spec 对账（{len(mods)} 个产品模块）")
print()
print(f"  ✅ 有 spec        {len(ok)}")
print(f"  🔴 没 spec        {len(missing)}   ← 别人【不知道它们存在】或【不知道做到哪】")
print(f"  🗑  spec 有、代码没了 {len(extra)}   ← 模块删了，spec 残留")
if extra:
    for k in extra:
        print(f"        docs/specs/{have[k]}")
print()
if missing:
    print("没 spec 的（按行数降序，前 15）：")
    for m, p, n in sorted(missing, key=lambda x: -x[2])[:15]:
        print(f"  {p:38} {n:4} 行")
PY
