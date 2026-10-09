#!/usr/bin/env bash
#
# test_check_stale_imports.sh —— `check_stale_imports.py` 的回归测试（2026-10-09 · `N21`）
#
# ## 为什么有这个文件
#
# 本仓立场：**一条测不出「不成立」的守卫 = 没有守卫**（`DEC-061`）。
# 过期导入门是 2026-10-09 新立的（背景：`#123` 重构静默打断两个活工具，
# 913 条 pytest 与 `compileall` 双双照不到）—— **它必须自证会红**。
#
# ## 钉住的不变量
#
#   T1 **干净 ⇒ exit 0**（⛔ 不许"永远红"）
#   T2 **有【模块搬家了但导入没改】的 ⇒ exit 1，且点名 `文件:行` 与【新家】**
#   T3 **`archive/` 里的同款 ⇒ 仍 exit 0**（归档 = 留痕，⛔ 不该红）
#   T4 **文件名含「探针」的 ⇒ 仍 exit 0**（探针是一次性的）
#   T5 **拿不到 git ⇒ exit 2【不得当作通过】**（⛔ 不许把"没能判定"压成"没有"）
#   T6 **找不到 `app/` ⇒ exit 2**（同上）
#   T7 **`app/` 根下的模块名仍算正常**（`from main import app` 这种⛔ 不该被误报）
#
# ## 为什么造临时"仓根"
#
# 门把自己所在目录的**上一级**当成仓根（`__file__/../..`）。
# 直接在本仓上测 = 拿**真实数据**当夹具 ⇒ 结论随仓里文件增删而漂。
# ⇒ 每例造一个**独立小仓**，并把门脚本**复制**进去（同 `test_check_doc_orphans.sh`）。
#
# ⚠️ **必须摘掉继承来的 `GIT_DIR` / `GIT_WORK_TREE`** —— 它们会指回主检出
#    （且 `GIT_DIR` **盖过 `git -C`**）⇒ 夹具里的 `git add` 会打到**真仓**上。
#    实测教训见 `test_check_doc_orphans.sh` 顶部。
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE_SRC="${REPO}/scripts/check_stale_imports.sh"
PY="$(command -v python3)"

unset GIT_DIR GIT_WORK_TREE
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

fails=0
ok()   { echo "  ✅ $1"; }
bad()  { echo "  🔴 $1"; fails=$((fails + 1)); }

# ── 造一个独立小仓：app/ <组>/<模块> + app/根模块 + scripts/ ──────────────
build_fixture() {
  local d; d="$(mktemp -d)"
  mkdir -p "${d}/app/access" "${d}/app/rag" "${d}/scripts" "${d}/archive" \
           "${d}/fastapi-rag-agent-TODO待办"
  : > "${d}/app/__init__.py"
  : > "${d}/app/main.py"                       # app/ 根的模块（T7 用）
  : > "${d}/app/access/auth.py"                # 搬进组的模块
  : > "${d}/app/access/__init__.py"
  : > "${d}/app/rag/chunker.py"
  : > "${d}/app/rag/__init__.py"
  cp "${GATE_SRC}" "${d}/scripts/check_stale_imports.sh"
  git -C "${d}" init -q
  git -C "${d}" -c user.email=t@t -c user.name=t add -A
  git -C "${d}" -c user.email=t@t -c user.name=t commit -qm init
  echo "${d}"
}

# 跑门（在夹具仓里），回它的退出码
run_gate() { bash "$1/scripts/check_stale_imports.sh" >"$1/.out" 2>&1; echo $?; }

echo "── T1 干净 ⇒ exit 0 ──"
D="$(build_fixture)"
printf 'from access.auth import create_user_api_key\nfrom rag.chunker import split\n' > "${D}/scripts/good.py"
git -C "${D}" add -A
rc="$(run_gate "${D}")"
[ "${rc}" = "0" ] && ok "exit 0" || { bad "期望 0 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo "── T2 有过期导入 ⇒ exit 1 + 点名【文件:行】与【新家】 ──"
D="$(build_fixture)"
printf 'from auth import create_user_api_key\n' > "${D}/scripts/bad.py"
git -C "${D}" add -A
rc="$(run_gate "${D}")"
if [ "${rc}" != "1" ]; then
  bad "期望 1 实得 ${rc}"; cat "${D}/.out"
elif grep -q "scripts/bad.py:1" "${D}/.out" && grep -q "access.auth" "${D}/.out"; then
  ok "exit 1，且点名了 scripts/bad.py:1 与 access.auth"
else
  bad "红了但没点名对"; cat "${D}/.out"
fi
rm -rf "${D}"

echo "── T3 archive/ 里的同款 ⇒ 仍 exit 0（归档是留痕） ──"
D="$(build_fixture)"
printf 'from auth import x\n' > "${D}/archive/old_tool.py"
git -C "${D}" add -A
rc="$(run_gate "${D}")"
[ "${rc}" = "0" ] && ok "exit 0（豁免生效）" || { bad "期望 0 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo "── T4 文件名含「探针」的 ⇒ 仍 exit 0（探针是一次性的） ──"
D="$(build_fixture)"
printf 'from auth import x\n' > "${D}/fastapi-rag-agent-TODO待办/探针-流式与记账.py"
git -C "${D}" add -A
rc="$(run_gate "${D}")"
[ "${rc}" = "0" ] && ok "exit 0（豁免生效）" || { bad "期望 0 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo "── T5 拿不到 git ⇒ exit 2【不得当作通过】 ──"
D="$(build_fixture)"
rm -rf "${D}/.git"
rc="$(run_gate "${D}")"
[ "${rc}" = "2" ] && ok "exit 2（判不了，⛔ 不是 0）" || { bad "期望 2 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo "── T6 找不到 app/ ⇒ exit 2 ──"
D="$(build_fixture)"
rm -rf "${D}/app"
rc="$(run_gate "${D}")"
[ "${rc}" = "2" ] && ok "exit 2（判不了）" || { bad "期望 2 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo "── T7 app/ 根下的模块名仍算正常（⛔ 不误报） ──"
D="$(build_fixture)"
printf 'from main import app\n' > "${D}/scripts/ok_root.py"
git -C "${D}" add -A
rc="$(run_gate "${D}")"
[ "${rc}" = "0" ] && ok "exit 0（from main import … 没被误报）" || { bad "期望 0 实得 ${rc}"; cat "${D}/.out"; }
rm -rf "${D}"

echo
if [ "${fails}" -eq 0 ]; then
  echo "✅ 过期导入门自测通过 —— 7 条全过（含两条『判不了必须是 2』的正例）。"
  exit 0
fi
echo "🔴 过期导入门自测失败 ${fails} 项 —— 这道门现在不可信。"
exit 1
