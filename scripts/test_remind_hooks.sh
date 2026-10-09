#!/usr/bin/env bash
# 自测：`.claude/hooks/` 下四个 hook ——
#   · `py-compile-remind.py` · `claim-evidence-remind.py`（判据逻辑，2026-10-05 建）
#   · 🆕 `spec-remind.py` · `route-auth-remind.py`（**路径判据**，2026-10-09 补 —— 见文件末 §路径判据）
#
# ── 为什么要有这个文件 ──────────────────────────────────────────────
# 本仓纪律：**「门挂在别处，就等于没有门」**（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）。
# 这两个 hook 是 2026-10-05（批 4）为 `docs/待办总表.md` §五·1 / §五·4 建的 ——
# ⚠️ **而"它到底会不会说话"没有任何东西证明过**。
# 一个**永远不会说话**的提醒，与"说话了但没问题"在机器痕迹上**完全一样**（`DEC-061`）
# ⇒ 所以下面每一条**都必须能打印出一个可判的退出码 + 一句能 grep 的输出**。
#
# ── 判据（可打印） ──────────────────────────────────────────────────
#   bash scripts/test_remind_hooks.sh        ⇒ 期望末行 `22 通过 / 0 失败`
#
# ── 🔴 还要在【副本里】跑一遍（本仓真踩过） ──────────────────────────
#   ROOT=$(mktemp -d); mkdir -p "$ROOT/.claude/hooks" "$ROOT/scripts"
#   cp .claude/hooks/*.py "$ROOT/.claude/hooks/"; cp scripts/test_remind_hooks.sh "$ROOT/scripts/"
#   bash "$ROOT/scripts/test_remind_hooks.sh"       # ⇒ 也必须 22 通过
#   ⚠️ **为什么**：macOS 上 `/var` 是 `/private/var` 的**软链**，而 `mktemp -d` 给的正是 `/var/...`
#      ⇒ 钩子里的 `Path(__file__).resolve()` 与调用方给的路径**两边形式不一致**
#      ⇒ **T9 在真仓绿、在副本红**（实测 2026-10-05）。两边都跑才照得出来。
#      ⇒ 这**不是**"副本环境不一样所以忽略"：那个差异会让**按路径前缀的豁免静默失效**。
#   ⛔ **别空跑**：这两个 hook 都**只从 stdin 读 hook JSON**，没有输入时**静默 exit 0**
#      —— 直接 `python3 x.py` 会"全绿"，那是**静默假通过**（本仓 `pre-commit-gates.py` 的前科）。
#      ⇒ 本文件**每条用例都喂真 JSON**。
#
# ── 变异自证（改坏它，这几条必须红） ────────────────────────────────
#   · 把 `claim-evidence-remind.py` 的 `has_evidence()` 改成恒 `return True`
#       ⇒ **T6** 必红（有否定、无命令，本该说话却哑了）—— 证明"找命令"那一半是**承重的**
#   · 把 `py-compile-remind.py` 里 `r.returncode != 0` 改成 `== 0`
#       ⇒ **T2** 必红 —— 证明它真的读了解释器的结论，⛔ 不是"跑了就算"
#   · 把 `should_check` 的 `.py` 判据删掉 ⇒ **T4**（.md）必红
#   ⚠️ 诚实控制组：**T1/T3/T8** 本来就是"静默"，⛔ **不能**用来证上面三条
#      —— 静默既可能来自"判据正确"，也可能来自"根本没跑"。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS="${REPO}/.claude/hooks"
PY=python3

command -v "$PY" >/dev/null || { echo "⛔ 找不到 python3" >&2; exit 2; }
[ -f "${HOOKS}/py-compile-remind.py" ] || { echo "⛔ 缺 hook：py-compile-remind.py" >&2; exit 2; }
[ -f "${HOOKS}/claim-evidence-remind.py" ] || { echo "⛔ 缺 hook：claim-evidence-remind.py" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

PASS=0
FAIL=0

# mkjson <file_path> <text> [new_string|content]
mkjson() {
  FIELD="${3:-new_string}" "$PY" -c '
import json, os, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1], os.environ["FIELD"]: sys.argv[2]}}))
' "$1" "$2"
}

# t <名> <期望 出话|静默> <hook 文件名> <JSON>
t() {
  local name="$1" want="$2" hook="$3" json="$4"
  local out rc
  out="$(printf '%s' "${json}" | "$PY" "${HOOKS}/${hook}" 2>&1)"
  rc=$?

  # 第一条钉子：hook **恒 exit 0** —— ⛔ 它的失败方式里不许有"把主流程搞挂"这一种
  if [ "${rc}" -ne 0 ]; then
    printf '  ❌ %s —— 退出码 %s（提醒型 hook 必须恒 0）\n' "${name}" "${rc}"
    FAIL=$((FAIL + 1)); return
  fi

  case "${want}" in
    出话)
      if [ -n "${out}" ]; then
        printf '  ✅ %s\n' "${name}"; PASS=$((PASS + 1))
      else
        printf '  ❌ %s —— 该说话却【完全没有输出】（= 与"没问题"无法区分）\n' "${name}"
        FAIL=$((FAIL + 1))
      fi ;;
    静默)
      if [ -z "${out}" ]; then
        printf '  ✅ %s\n' "${name}"; PASS=$((PASS + 1))
      else
        printf '  ❌ %s —— 本该静默却出话了：%s\n' "${name}" "${out%%$'\n'*}"
        FAIL=$((FAIL + 1))
      fi ;;
  esac
}

# ── 夹具 ────────────────────────────────────────────────────────────
GOOD="${TMP}/good.py"
printf 'def f():\n    return 1\n' > "${GOOD}"

BAD="${TMP}/bad.py"                                   # 🔴 故意：三引号从中间截断（2026-09-20 那个真事故的形状）
printf 'def f():\n    """文档\n    return "x"\n' > "${BAD}"

DOC="${TMP}/note.md"
printf '# 记事\n' > "${DOC}"

CLAIM_FILE="${TMP}/spec_like.md"
printf '# 某模块\n' > "${CLAIM_FILE}"

echo "提醒型 hook 自测 —— 2 个 hook · 10 条用例"
echo "hook 目录：${HOOKS}"
echo

# ── py-compile-remind.py（§五·4） ───────────────────────────────────
t "T1 合法 .py ⇒ 静默（不误报）"        静默  py-compile-remind.py  "$(mkjson "${GOOD}" "" content)"
t "T2 语法错的 .py ⇒ 出话"              出话  py-compile-remind.py  "$(mkjson "${BAD}"  "" content)"
t "T3 .md ⇒ 静默（不是 Python 就不管）"  静默  py-compile-remind.py  "$(mkjson "${DOC}"  "# 随便" content)"
t "T4 不存在的路径 ⇒ 静默（⛔ 不炸）"    静默  py-compile-remind.py  "$(mkjson "${TMP}/nope.py" "" content)"
t "T4b worktrees 下的 .py ⇒ 静默"       静默  py-compile-remind.py \
  "$(mkjson "${REPO}/.claude/worktrees/foo/bar.py" "" content)"

# ── claim-evidence-remind.py（§五·1） ───────────────────────────────
t "T5 无全称否定 ⇒ 静默"                静默  claim-evidence-remind.py \
  "$(mkjson "${CLAIM_FILE}" '这个端点返回 3 条结果。')"

t "T6 「X 不存在」且无命令 ⇒ 出话"       出话  claim-evidence-remind.py \
  "$(mkjson "${CLAIM_FILE}" '`/rag/ask` 不存在，`/rag/search` 也不生成答案。')"

t "T7 有全称否定 + 行内命令 ⇒ 静默"      静默  claim-evidence-remind.py \
  "$(mkjson "${CLAIM_FILE}" '`/rag/ask` 不存在 —— 判据：`grep -n "rag/ask" app/*.py` ⇒ 0 行。')"

t "T8 「全称否定」旁路 ⇒ 静默"           静默  claim-evidence-remind.py \
  "$(mkjson "${CLAIM_FILE}" '复盘里那句「全称否定」（X 不存在）是我写错的。')"

t "T9 docs/复盘/ ⇒ 静默（历史不改写）"   静默  claim-evidence-remind.py \
  "$(mkjson "${REPO}/docs/复盘/2026-09-29-结果为空就断言能力不存在.md" '$X$ 不存在，且是唯一的。')"


# ═══════════════════════════════════════════════════════════════════════
# §路径判据 —— 🆕 2026-10-09（模块化重构）补
# ═══════════════════════════════════════════════════════════════════════
#
# 🔴 **为什么补这一段**：`spec-remind` 与 `route-auth-remind` **此前从没有自测** ——
#    而它们的判据**全部按路径**（`app/` 下 + 文件名 + `docs/specs/<名>.md`），
#    正是模块化重构**最容易弄瞎**的那一类。
#    本仓纪律：「**门必须能测出自己会红**」（`DEC-061` / `DEC-066`）——
#    一个永远不出声的提醒，与"出声了但没问题"在机器痕迹上**完全一样**。
#    ⚠️ 2026-10-09 实测过：重构后这两个 hook **仍然正确**（此前"部分失明"是**读代码的推断，
#       不是实测** ⇒ 那条推断是错的）。补自测是为了**以后**再重构时能立刻知道。

# spec-remind 需要 `tool_name` 与 `cwd`（原 `mkjson` 只给 file_path ⇒ 它会静默退出）
mkjson_edit() {
  "$PY" -c '
import json, sys
print(json.dumps({"tool_name": sys.argv[2], "cwd": sys.argv[3],
                  "tool_input": {"file_path": sys.argv[1]}}))
' "$1" "${2:-Edit}" "${REPO}"
}

t "T10 组目录里的模块（有 spec）⇒ 出话"   出话  spec-remind.py "$(mkjson_edit "${REPO}/app/core/config.py")"
t "T11 另一个组 + 有 spec）⇒ 出话"       出话  spec-remind.py "$(mkjson_edit "${REPO}/app/rag/chunker.py")"
t "T12 app/ 根的 main.py（有 spec）⇒ 出话" 出话 spec-remind.py "$(mkjson_edit "${REPO}/app/main.py")"
t "T13 app/tests/ 下的测试 ⇒ 静默"        静默  spec-remind.py "$(mkjson_edit "${REPO}/app/tests/test_main.py")"
t "T14 .md ⇒ 静默"                       静默  spec-remind.py "$(mkjson_edit "${REPO}/docs/待办总表.md")"
# ⚠️ 用 `Read` 而不是空串：bash 的 `${2:-Edit}` 在**空串**时**也会**取默认值
#    （`:-` 的语义是"未设**或为空**就用默认"）⇒ 传空串**根本测不到**这一支。2026-10-09 实测踩过。
t "T14b 非 Edit/Write（Read）⇒ 静默"      静默  spec-remind.py "$(mkjson_edit "${REPO}/app/core/config.py" Read)"
# 🔴 `T14c` 专测 `app/` **前缀**那一支 —— 2026-10-09 变异自证发现：
#    上面 T13 是被 `test_` 基线名挡下的、T14 是被 `.md` 挡下的，
#    ⇒ **拿掉 `app/` 前缀判据后它们全绿**（用例对这个判据**没有牙齿**）。
#    本仓原话：「**门的靶子要定准**」。
t "T14c 仓外 .py（scripts/）⇒ 静默（只认 app/ 下）" 静默  spec-remind.py "$(mkjson_edit "${REPO}/scripts/issue_api_key.py")"

# ── route-auth-remind：真正按路径判的是 `looks_like_route_file()` ──
# ⚠️ **不测它的"出话"** —— 它只在「**新引入了没鉴权的路由**」时才出声，
#    而那要求先造一条坏路由（会真改仓）。⇒ 测它**判据的那一半**：
#    「这个 .py 算不算**生产路由文件**」。这一半**恰好是重构会弄瞎的那一半**。
rl() {
  "$PY" -c '
import importlib.util, pathlib, sys
s = importlib.util.spec_from_file_location("rah", sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print("TRUE" if m.looks_like_route_file(pathlib.Path(sys.argv[2])) else "FALSE")
' "${HOOKS}/route-auth-remind.py" "$1"
}
t2() {  # <名> <期望 TRUE|FALSE> <相对仓根的路径>
  local got; got="$(rl "${REPO}/$3")"
  if [ "${got}" = "$2" ]; then
    printf '  ✅ %s ⇒ %s\n' "$1" "${got}"; PASS=$((PASS + 1))
  else
    printf '  ❌ %s ⇒ %s（期望 %s）\n' "$1" "${got}" "$2"; FAIL=$((FAIL + 1))
  fi
}
t2 "T15 组目录里的路由文件（api_v1）"     TRUE  "app/routing/api_v1.py"
t2 "T16 组目录里的路由文件（api_v1_rag）" TRUE  "app/routing/api_v1_rag.py"
t2 "T17 非路由模块 ⇒ 不算"                FALSE "app/core/config.py"
t2 "T18 tests/ 下的测试 ⇒ 不算"           FALSE "app/tests/test_api_v1.py"
t2 "T19 仓根脚本 ⇒ 不算（不在 app/ 下）"   FALSE "scripts/check_route_auth.py"

echo
if [ "${FAIL}" -eq 0 ]; then
  echo "结果: ${PASS} 通过 / ${FAIL} 失败"
else
  echo "结果: ${PASS} 通过 / ${FAIL} 失败"
  echo "⛔ 有用例失败"
  exit 1
fi
