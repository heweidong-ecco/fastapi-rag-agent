#!/usr/bin/env bash
# 自测：`.claude/hooks/` 下两个【提醒型】hook —— `py-compile-remind.py` · `claim-evidence-remind.py`
#
# ── 为什么要有这个文件 ──────────────────────────────────────────────
# 本仓纪律：**「门挂在别处，就等于没有门」**（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）。
# 这两个 hook 是 2026-10-05（批 4）为 `docs/待办总表.md` §五·1 / §五·4 建的 ——
# ⚠️ **而"它到底会不会说话"没有任何东西证明过**。
# 一个**永远不会说话**的提醒，与"说话了但没问题"在机器痕迹上**完全一样**（`DEC-061`）
# ⇒ 所以下面每一条**都必须能打印出一个可判的退出码 + 一句能 grep 的输出**。
#
# ── 判据（可打印） ──────────────────────────────────────────────────
#   bash scripts/test_remind_hooks.sh        ⇒ 期望末行 `10 通过 / 0 失败`
#
# ── 🔴 还要在【副本里】跑一遍（本仓真踩过） ──────────────────────────
#   ROOT=$(mktemp -d); mkdir -p "$ROOT/.claude/hooks" "$ROOT/scripts"
#   cp .claude/hooks/*.py "$ROOT/.claude/hooks/"; cp scripts/test_remind_hooks.sh "$ROOT/scripts/"
#   bash "$ROOT/scripts/test_remind_hooks.sh"       # ⇒ 也必须 10 通过
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
  "$(mkjson "${CLAIM_FILE}" '`/rag/ask` 不存在 —— 判据：`grep -n "rag/ask" api/*.py` ⇒ 0 行。')"

t "T8 「全称否定」旁路 ⇒ 静默"           静默  claim-evidence-remind.py \
  "$(mkjson "${CLAIM_FILE}" '复盘里那句「全称否定」（X 不存在）是我写错的。')"

t "T9 docs/复盘/ ⇒ 静默（历史不改写）"   静默  claim-evidence-remind.py \
  "$(mkjson "${REPO}/docs/复盘/2026-09-29-结果为空就断言能力不存在.md" '$X$ 不存在，且是唯一的。')"

echo
if [ "${FAIL}" -eq 0 ]; then
  echo "结果: ${PASS} 通过 / ${FAIL} 失败"
else
  echo "结果: ${PASS} 通过 / ${FAIL} 失败"
  echo "⛔ 有用例失败"
  exit 1
fi
