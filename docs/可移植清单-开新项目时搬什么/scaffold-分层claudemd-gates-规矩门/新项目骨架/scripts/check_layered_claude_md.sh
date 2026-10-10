#!/usr/bin/env bash
#
# check_layered_claude_md.sh —— **第 ⑧ 道门 · 「分层 CLAUDE.md」机制的门**
#
# ## 为什么要有它（这不是"再提醒一次"，是补一个结构性缺口）
#
# 本仓 2026-10-09 起用「**每层目录一份 `CLAUDE.md`**」这套机制
# （机制说明：见本文件头的「判据」那段）。
# 🔴 **它一直是【靠自觉】的** —— 全仓 7 道门里**没有一道管目录层**：
#    · 第 ④ 道门管的是「新增 **`.py` 模块** ⇒ 必须有 spec」，⛔ **不管目录**
#    · 第 ③ 道（孤儿门）管的是「**`.md` 文档**必须被指向」，⛔ **也不管目录**
# ⇒ 后果：**新加一个目录、忘了写 `CLAUDE.md`，不会有任何信号** ——
#    下一次 agent 进到那层**什么都读不到**，而**所有门都不会红**。
#
# 本仓立场（就写在根 `CLAUDE.md` 里）：
#   · **「门挂在别处，就等于没有门」**
#   · **「只有文字就漏，结构才执行」** —— 规范 §六 在补这道门之前**只有文字**
#
# ## 判据（一句话）
#
# **每一个【直接含有 tracked 文件】的目录，除豁免名单外，都必须有 tracked 的 `CLAUDE.md`。**
#
# ⚠️ **口径问的是 git，⛔ 不是磁盘** —— 同断链门（`DEC-076 §2.9`）：
#    要的是「**克隆者拿得到什么**」，而不是"我这台机器上有没有"。
#
# ## 退出码（**三态，别读成两态**）
#
#   0 ⇒ 通过（该有的都有）
#   1 ⇒ **有缺**（列出是哪些目录）
#   3 ⇒ **没跑**（不是 git 仓 / git 读不到 ⇒ ⛔ 与"干净"分开）
#       ⚠️ 这一条是给第 ⑧ 道门用的：hook 把 3 显示成 **⏭ 未跑** 而**不锁死人**；
#          CI 那边**任何非 0 都算失败** ⇒ 兜底成立（同第 ⑥/⑦ 道门的约定）。
#
# ## 用法
#
#     bash scripts/check_layered_claude_md.sh              # 查本仓
#     bash scripts/check_layered_claude_md.sh --repo <dir> # 查指定仓（自测用）
#     bash scripts/check_layered_claude_md.sh --self-test  # **自带正反例**（temp 仓里跑）
#
# ## ⚠️ 豁免名单为什么是这一份
#
# **直接抄自规范 §六**（"不建 `CLAUDE.md` 的目录"），⛔ **不在本脚本里另造一份** ——
# 本仓明文教训：**一个名单两个来源必然漂移，而漂移是静默的**（`DEC-051`）。
# ⚠️ 改规范那条 ⇒ **同批改这里**；两边不一致的表现是"门放行了规范不许放的东西"（或反之），**不报错**。

set -uo pipefail   # ⚠️ 不开 -e：下面的分支要能"故意失败"而不中断

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO="$(cd "${SELF_DIR}/.." && pwd)"

REPO="${DEFAULT_REPO}"
SELF_TEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 3 ;;
  esac
done

# ── 查一个仓 ────────────────────────────────────────────────────────────────
check() {
  python3 - "$1" <<'PY'
import os, subprocess, sys
from collections import defaultdict

repo = sys.argv[1]

# ⚠️ `-z` + 按 NUL 切 —— 本仓有大量中文路径，`git ls-files` 不加 `-z` 会**加引号并转义八进制**
#    ⇒ 目录名被包在 `"` 里 ⇒ 匹配/输出全错（实测踩过：`"docs/\345\216\206..."`）。
r = subprocess.run(["git", "-C", repo, "ls-files", "-z"],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("⚠️ git 读不到这个仓 ⇒ 本门【未跑】")
    sys.exit(3)

files = [f for f in r.stdout.split("\0") if f]
if not files:
    print("⚠️ 没有 tracked 文件 ⇒ 本门【未跑】")
    sys.exit(3)

# ── 豁免规则 —— **与规范 §六 的「不建 `CLAUDE.md` 的目录」逐条对应** ──
# ⚠️ 规范那份列的是**目录名**（`venv/` `logs/` `archive/` …），所以这里**按【名字】匹配**，
#    ⛔ 不是按某个具体路径 —— 否则 `app/logs` 与根 `logs` 会一个豁免一个不豁免（**静默不一致**）。
NAME_EXEMPT = {
    "venv", "venv-ragas",                 # 依赖
    "tmp", "logs", "archive", "screenshots", "self-prompt",   # 被 .gitignore 的
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".mem0",
    "node_modules",                       # 缓存 / 生成物
}
# 多段路径按【前缀】豁免（规范 §六 里那两条本来就是路径）
PATH_EXEMPT = (".claude/worktrees",)   # 🔴 开新项目：本目录下若有"整份不建 CLAUDE.md"的路径，加在这里


def exempt(d):
    """这个目录该不该有 `CLAUDE.md`？"""
    if NAME_EXEMPT & set(d.split("/")):
        return True
    return any(d == p or d.startswith(p + "/") for p in PATH_EXEMPT)

has_claude, per_dir = set(), defaultdict(int)
for f in files:
    d = os.path.dirname(f)
    if d:
        per_dir[d] += 1
    if os.path.basename(f) == "CLAUDE.md":
        has_claude.add(d)

missing = sorted(d for d in per_dir
                 if d not in has_claude and not exempt(d))

total = len([d for d in per_dir if not exempt(d)])
print(f"扫描 {len(files)} 个 tracked 文件 · {total} 个目录层（已排除豁免）")
if missing:
    print(f"\n🔴 缺 CLAUDE.md 的目录（{len(missing)} 个）：")
    for d in missing:
        print(f"   {d}   （含 {per_dir[d]} 个 tracked 文件）")
    print("\n📌 处置：给每个目录加一份 `CLAUDE.md`（它是那一层的【索引表 + 主要内容】）；")
    print("   若它确实【不该有】（比如整目录 gitignore），**去改规范那份豁免名单**，⛔ 别在本脚本里绕。")
    sys.exit(1)

print("✅ 每个目录层都有 CLAUDE.md。")
sys.exit(0)
PY
}

# ── 自测：**必须能测出「不成立」** ───────────────────────────────────────────
# 本仓立场：「**一条测不出「不成立」的守卫 = 没有守卫**」（`DEC-061`）。
# ⇒ 正例（该绿）与反例（该红）**都要有**，且反例必须真的让它红。
self_test() {
  local pass=0 fail=0 tmp

  # 🔴🔴 先摘掉**继承来的** git 定向变量 —— **`GIT_DIR` 盖过 `git -C`**。
  #    只要外面 export 了 `GIT_DIR`（本地"复现 CI"的脚本常这么干，为的是让别的门
  #    能在临时副本里跑到真仓的提交范围），夹具里的 `git init/add` 就会打到**外面那个仓**上，
  #    而下面 `check "${tmp}"` 读到的也是**那个仓** ⇒
  #    **反例永远红、正例"绿得没意义"**（它验的不是夹具）。
  #    📌 **为什么必须由本脚本自己摘**：夹具的自测**天生要造真 git 仓** ——
  #       这件事的性质决定了它不能指望调用方给一个干净的环境。
  #       ⛔ 别改到调用方去（在外面写 `env -u GIT_DIR …`）—— 那会让这条性质消失。
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' RETURN

  mk() {  # mk <子目录> <文件数> [CLAUDE.md?]
    mkdir -p "${tmp}/$1"
    for i in $(seq 1 "$2"); do : > "${tmp}/$1/f${i}.py"; done
    [ "${3:-no}" = "yes" ] && : > "${tmp}/$1/CLAUDE.md"
    return 0
  }

  # 造一个干净的仓：每层都有 CLAUDE.md
  mk "a" 2 yes
  mk "a/b" 2 yes
  mk "top" 1 yes
  : > "${tmp}/README.md"
  mk "archive" 1 no          # ← 豁免名单里的，⛔ 不该红

  git -C "${tmp}" init -q >/dev/null 2>&1
  # 🔴 夹具仓**必须真的建起来** —— 被继承的 `GIT_DIR` 下 `git init` 会**返回 0 却什么都不建**。
  #    不钉这一条，下面五条会"全绿"而**验的根本不是夹具** ——
  #    那正是本门最恨的那种「空跑 = 静默假通过」。
  [ -d "${tmp}/.git" ] || { echo "⛔ 夹具仓没建起来：${tmp}/.git 不存在（GIT_DIR 被继承了？）" >&2; exit 2; }
  git -C "${tmp}" add -A >/dev/null 2>&1

  # T1 正例：全都有 ⇒ 必须 exit 0
  if check "${tmp}" >/dev/null 2>&1; then
    echo "  ✅ T1 每层都有 CLAUDE.md ⇒ 绿"; pass=$((pass+1))
  else
    echo "  🔴 T1 期望绿，实际红"; fail=$((fail+1))
  fi

  # T2 反例：加一个**有内容、没 CLAUDE.md** 的目录 ⇒ 必须 exit 1，且**指名到它**
  mk "a/c" 2 no
  git -C "${tmp}" add -A >/dev/null 2>&1
  out="$(check "${tmp}" 2>&1)"; rc=$?
  if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q "a/c"; then
    echo "  ✅ T2 有内容却没 CLAUDE.md ⇒ 红，且指名 a/c"; pass=$((pass+1))
  else
    echo "  🔴 T2 期望红并指名 a/c，实际 rc=${rc}：${out}"; fail=$((fail+1))
  fi

  # T3 反例的**反面**：补上 CLAUDE.md ⇒ 必须回到绿（证明 T2 钉的真是那一件）
  mk "a/c" 0 yes
  git -C "${tmp}" add -A >/dev/null 2>&1
  if check "${tmp}" >/dev/null 2>&1; then
    echo "  ✅ T3 补上后 ⇒ 回绿（证明 T2 钉的是它）"; pass=$((pass+1))
  else
    echo "  🔴 T3 补上后仍红"; fail=$((fail+1))
  fi

  # T4 豁免：archive/ 有内容、没 CLAUDE.md ⇒ **不该红**（否则门会天天误报）
  out="$(check "${tmp}" 2>&1)"; rc=$?
  if [ "${rc}" -eq 0 ] && ! printf '%s' "${out}" | grep -q "archive"; then
    echo "  ✅ T4 豁免目录（archive/）不报"; pass=$((pass+1))
  else
    echo "  🔴 T4 豁免目录被报了：rc=${rc}：${out}"; fail=$((fail+1))
  fi

  # T5 没跑态：不是 git 仓 ⇒ exit 3（⛔ 不是 0，也不是 1）
  local nogit="${tmp}-nogit"; mkdir -p "${nogit}/x"; : > "${nogit}/x/f.py"
  rc=0; check "${nogit}" >/dev/null 2>&1 || rc=$?
  rm -rf "${nogit}"
  if [ "${rc}" -eq 3 ]; then
    echo "  ✅ T5 不是 git 仓 ⇒ 3（未跑，⛔ 不是 0）"; pass=$((pass+1))
  else
    echo "  🔴 T5 期望 3，实际 ${rc}"; fail=$((fail+1))
  fi

  echo
  echo "结果: ${pass} 通过 / ${fail} 失败"
  [ "${fail}" -eq 0 ]
}

if [ "${SELF_TEST}" -eq 1 ]; then
  self_test
  exit $?
fi

check "${REPO}"
