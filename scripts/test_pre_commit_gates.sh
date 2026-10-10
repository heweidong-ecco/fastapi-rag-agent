#!/usr/bin/env bash
# 自测：**提交门本体** —— `.claude/hooks/pre-commit-gates.py`
#
# ── 为什么要有这个文件 ──────────────────────────────────────────────
# `docs/待办总表.md` 的 `§七·3`（2026-10-07 登记）：
#   🔴 **八道门里，只有它自己【没有任何测试】** —— 另外七道各有 `test_check_*.sh`。
# 本仓立场：**「一条测不出『不成立』的守卫 = 没有守卫」**（`DEC-061`），
# 而这一份是**把八道门串起来跑的那段胶水** —— 它坏掉的表现是**门全被跳过**，
# ⚠️ 而那与"全绿"在机器痕迹上**完全一样**。
#
# ── 🔴 三条最容易写歪的地方（都实测过） ─────────────────────────────
# 1. **别直接 `python3 pre-commit-gates.py`** —— 它**只从 stdin 读 hook JSON**，
#    没有输入时**静默 exit 0** ⇒ 那是**静默假通过**（本文件每条都喂真 JSON）。
# 2. **夹具必须自带 `scripts/` 与 `.claude/hooks/`** ——
#    门脚本是按 `cwd` 找的 ⇒ 临时仓里没有它们 ⇒ **八道门全进"跳过"** ⇒ **exit 0 假绿**。
#    ⚠️ 这正是本文件要防的那个形态，所以**必须**把脚本一起拷进去。
# 3. **夹具必须 `touch .env`** —— 凭据门在**没有 `.env`** 时 **exit 2**，
#    而 hook 把"非 0/3"当**失败** ⇒ 所有用例都会被它顶成 exit 2，**分不出别的门**。
#
# ── 判据（可打印） ──────────────────────────────────────────────────
#   bash scripts/test_pre_commit_gates.sh      ⇒ 期望末行 `8 通过 / 0 失败`
#
# ── 变异自证（改坏它，哪条必须红） ──────────────────────────────────
#   · 把 hook 里的 `GIT_COMMIT` 正则去掉（改成永远匹配）⇒ **T1** 必红
#   · 把 hook 的 `return 2` 改成 `return 0`（门全不拦）⇒ **T4/T5/T6 全红**
#   · 把第 ⑧ 道门从 `GATES` 表里删掉 ⇒ **T6** 必红（它专钉那一道）
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="${REPO}/.claude/hooks/pre-commit-gates.py"
PY=python3

command -v "${PY}" >/dev/null || { echo "⛔ 找不到 python3" >&2; exit 2; }
[ -f "${HOOK}" ] || { echo "⛔ 缺 hook：${HOOK}" >&2; exit 2; }

pass=0; fail=0

jqstr() { "${PY}" -c 'import json,sys;print(json.dumps(sys.argv[1]))' "${1}"; }
mkjson() { printf '{"cwd":%s,"tool_input":{"command":%s}}' "$(jqstr "${1}")" "$(jqstr "${2}")"; }

# t <描述> <期望退出码> <JSON>
t() {
  local desc="${1}" want="${2}" json="${3}" out rc
  out="$(printf '%s' "${json}" | "${PY}" "${HOOK}" 2>&1)"; rc=$?
  if [ "${rc}" = "${want}" ]; then
    echo "  ✅ ${desc}（exit ${rc}）"; pass=$((pass+1))
  else
    echo "  🔴 ${desc} —— 期望 exit ${want}，实际 ${rc}"
    printf '%s\n' "${out}" | sed 's/^/       /' | head -6
    fail=$((fail+1))
  fi
}

# ── 夹具：一个【自带门脚本】的临时仓 ────────────────────────────────
FIX="$(mktemp -d)"
cleanup() { rm -rf "${FIX}"; }
trap cleanup EXIT

mkdir -p "${FIX}/.claude/hooks" "${FIX}/docs" "${FIX}/app/core"
cp -R "${REPO}/scripts" "${FIX}/scripts"
cp "${REPO}/.claude/hooks/"*.py "${FIX}/.claude/hooks/"
# 🔴 **只拷【脚本】，⛔ 不拷它们旁边的 `.md`** —— 本夹具测的是**门的判定逻辑**，
#    ⛔ 不是"本仓自己的文档有没有断链"。
#    ⚠️ **实测踩过两次**：一拷 `scripts/CLAUDE.md`，它就引 `.claude/README.md`；
#       再拷 `.claude/README.md`，它又引 `docs/规范/…` + `docs/复盘/…` —— **链式追下去追不完**，
#       而每追一步都会让本夹具的"干净仓"用例**恒红**。
rm -f "${FIX}/scripts"/*.md "${FIX}/.claude/hooks/"*.md

# ── 下面这一小撮，是让【八道门同时为绿】的最小形状。每一行为什么非有不可： ──
# ① 第 ⑧ 道门要求【每个含 tracked 文件的目录都有 `CLAUDE.md`】——
#    `scripts/`(拷来的 ~40 个脚本) · `.claude/hooks/` · `docs/` · `app/` · `app/core/` 各要一份。
printf '# scripts（夹具占位）\n'      > "${FIX}/scripts/CLAUDE.md"
printf '# .claude/hooks（夹具占位）\n' > "${FIX}/.claude/hooks/CLAUDE.md"
printf '# docs（夹具占位）\n'          > "${FIX}/docs/CLAUDE.md"
printf '# app（夹具占位）\n'           > "${FIX}/app/CLAUDE.md"
printf '# app/core（夹具占位）\n'      > "${FIX}/app/core/CLAUDE.md"
# ② 凭据门没有 `.env` 时 **exit 2** ⇒ 会被当失败顶掉别的门（见文件头理由 3）
touch "${FIX}/.env"
# ③ 孤儿门要 `KEY_TARGETS`（`docs/文档地图.md` · `ROADMAP.md` · `CLAUDE.md`）**每个都被指向**，
#    且 `docs/文档地图.md` 要被**三个入口里的至少两个**指到。
printf '# CLAUDE.md\n\n见 `ROADMAP.md` · `docs/文档地图.md`。\n'   > "${FIX}/CLAUDE.md"
printf '# ROADMAP\n\n见 `CLAUDE.md` · `docs/文档地图.md`。\n'      > "${FIX}/ROADMAP.md"
printf '# README\n\n见 `CLAUDE.md` · `docs/文档地图.md`。\n'       > "${FIX}/README.md"
printf '# 文档地图\n\n见 `CLAUDE.md` · `ROADMAP.md`。\n'           > "${FIX}/docs/文档地图.md"
# ④ 过期导入门要 `app/` 下**至少有一个模块组**，否则报「无法判定」**exit 2**
printf 'X = 1\n' > "${FIX}/app/core/zz_stub.py"

# ⚠️ 用 `git -C <dir>` 形式 —— 命令串里出现「git commit」会触发本仓自己的提交门，白跑一遍
git -C "${FIX}" init -q -b main
git -C "${FIX}" add -A
git -C "${FIX}" -c user.email=t@t -c user.name=t commit -qm init

echo "── 夹具：${FIX}（自带 scripts/ + .claude/hooks/）"
echo

# ── T1 · 不是 commit ⇒ 放行 ─────────────────────────────────────────
t "T1 不是 git commit（git status）⇒ 放行" 0 "$(mkjson "${FIX}" "git status")"

# ── T2 · 输入不是 JSON ⇒ 放行 ───────────────────────────────────────
out="$(printf 'not-json' | "${PY}" "${HOOK}" 2>&1)"; rc=$?
if [ "${rc}" = 0 ]; then echo "  ✅ T2 非 JSON 输入 ⇒ 放行（exit 0）"; pass=$((pass+1));
else echo "  🔴 T2 期望 exit 0，实际 ${rc}"; fail=$((fail+1)); fi

# ── T3 · 干净仓 + 真 commit ⇒ 放行 ──────────────────────────────────
t "T3 干净仓 + 真 commit ⇒ 全门绿、放行" 0 "$(mkjson "${FIX}" "git commit -m x")"

# ── T4 · 断链 ⇒ 拦（第 ② 道门） ─────────────────────────────────────
printf '见 `不存在的文件-zzz.md`。\n' > "${FIX}/BROKEN.md"
git -C "${FIX}" add -A
t "T4 新增一个【断链】的 .md ⇒ 被拦（第 ② 道门）" 2 "$(mkjson "${FIX}" "git commit -m x")"
git -C "${FIX}" rm -q --cached BROKEN.md; rm -f "${FIX}/BROKEN.md"

# ── T5 · 新增模块没 spec ⇒ 拦（第 ④ 道门） ──────────────────────────
mkdir -p "${FIX}/app"
printf 'x = 1\n' > "${FIX}/app/zz_probe_mod.py"
git -C "${FIX}" add -A
t "T5 新增模块但【同目录没 spec】⇒ 被拦（第 ④ 道门）" 2 "$(mkjson "${FIX}" "git commit -m x")"
git -C "${FIX}" rm -q --cached app/zz_probe_mod.py; rm -f "${FIX}/app/zz_probe_mod.py"

# ── T6 · 新增目录没 CLAUDE.md ⇒ 拦（第 ⑧ 道门 · 2026-10-10 新加的那道）──
mkdir -p "${FIX}/newdir"
printf 'x = 1\n' > "${FIX}/newdir/a.py"
git -C "${FIX}" add -A
t "T6 新增目录但【没 CLAUDE.md】⇒ 被拦（第 ⑧ 道门）" 2 "$(mkjson "${FIX}" "git commit -m x")"

# ── T7 · 补上 CLAUDE.md ⇒ 回绿（**证明 T6 钉的真是那一件**）───────────
printf '# newdir\n\n占位。\n' > "${FIX}/newdir/CLAUDE.md"
git -C "${FIX}" add -A
t "T7 给那个目录补上 CLAUDE.md ⇒ 回绿" 0 "$(mkjson "${FIX}" "git commit -m x")"

# ── T8 · 汇总行必须出现（⛔ 别只看退出码） ───────────────────────────
out="$(printf '%s' "$(mkjson "${FIX}" "git commit -m x")" | "${PY}" "${HOOK}" 2>&1)"
if printf '%s' "${out}" | grep -q "提交前八道门" && printf '%s' "${out}" | grep -q "分层CLAUDE.md门"; then
  echo "  ✅ T8 汇总行打出「提交前八道门」且含「分层CLAUDE.md门」"; pass=$((pass+1))
else
  echo "  🔴 T8 汇总行不对：$(printf '%s' "${out}" | tail -2)"; fail=$((fail+1))
fi

echo
echo "结果: ${pass} 通过 / ${fail} 失败"
[ "${fail}" -eq 0 ]
