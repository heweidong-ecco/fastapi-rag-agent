#!/usr/bin/env bash
#
# check_template_sync.sh —— 「可移植包」的**防漂移门**
#
# ## 为什么要有它
#
# `docs/可移植清单-开新项目时搬什么/新项目骨架/` 里是**活文件的【快照】** ——
# 一旦本仓那几份源文件改了，包里的副本就**悄悄过期**，而**没有任何信号**。
#
# 🔴 **本仓刚栽过一模一样的坑**：一个"启动新项目"的 skill **把路径写死**，
#    而 2026-09-20 的分层重构**挪了目录** ⇒ 它**从那天起跑不通、没人知道**
#    （2026-10-10 才发现；那份用户级的已被删）。
#
# ⇒ 所以这个包**不能靠"记得同步"** —— 得让它**撞了就红**。
#
# ## 判据（一句话）
#
# **对 `scripts/template-manifest.txt` 里的每一对，源文件的 sha256 必须和记录一致。**
# ⚠️ **它比的是【源文件】，⛔ 不是副本** —— 副本按设计就**故意和源不同**
#    （裁掉了项目特定的东西：GATES 表 · KEY_TARGETS · 豁免名单 …）。
#    ⇒ **源一动，就是"该去看副本要不要跟"的信号。**
#
# ## 退出码（三态）
#
#   0 ⇒ 全部一致
#   1 ⇒ **有漂移**（列出是哪些源文件动了）
#   3 ⇒ **没跑**（manifest 不在 / git 读不到）
#
# ## 用法
#
#     bash scripts/check_template_sync.sh              # 查
#     bash scripts/check_template_sync.sh --update     # ⚠️ **人确认副本跟上了之后**，重记 sha
#     bash scripts/check_template_sync.sh --self-test  # 正反例
#
set -uo pipefail   # ⚠️ 不开 -e：自测要能"故意失败"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SELF_DIR}/.." && pwd)"
MANIFEST="${REPO}/scripts/template-manifest.txt"

MODE="check"
case "${1:-}" in
  --update)    MODE="update" ;;
  --self-test) MODE="self-test" ;;
  "" )         MODE="check" ;;
  *) echo "未知参数: $1" >&2; exit 3 ;;
esac

# ── 读 manifest ────────────────────────────────────────────────────────────
read_pairs() {   # 输出 "<sha> <源> <副本>" 三列（跳过注释与空行）
  [ -f "$1" ] || return 1
  grep -vE '^\s*(#|$)' "$1" | awk '{print $1, $2, $4}'
}

# ── 查 ─────────────────────────────────────────────────────────────────────
do_check() {
  local manifest="$1" repo="$2"
  local n_pairs=0 n_bad=0 n_missing=0
  local line sha src dst now

  while IFS= read -r line; do
    # shellcheck disable=SC2086
    set -- ${line}
    sha="$1"; src="$2"; dst="$3"
    n_pairs=$((n_pairs+1))

    if [ ! -f "${repo}/${dst}" ]; then
      echo "   🔴 副本不见了：${dst}（源 ${src} 的快照）"
      n_missing=$((n_missing+1)); continue
    fi
    if [ ! -f "${repo}/${src}" ]; then
      echo "   🔴 源文件不见了：${src}（副本 ${dst} 在）—— manifest 该改了"
      n_missing=$((n_missing+1)); continue
    fi

    now="$(shasum -a 256 "${repo}/${src}" | awk '{print $1}')"
    if [ "$now" != "$sha" ]; then
      echo "   🔴 源文件动过了：${src}"
      echo "        落在包里的快照 ⇒ ${dst}"
      n_bad=$((n_bad+1))
    fi
  done < <(read_pairs "$manifest")

  echo "比对 ${n_pairs} 对（源文件 ⇄ 包内快照）"
  if [ "${n_missing}" -gt 0 ]; then
    echo ""
    echo "❌ 有 ${n_missing} 对【文件对不上】—— 先修 manifest 或把文件放回去。"
    return 3
  fi
  if [ "${n_bad}" -gt 0 ]; then
    echo ""
    echo "🔴 有 ${n_bad} 个源文件动过 —— **去看包里的快照要不要跟着改**："
    echo "   ① 改了副本 ⇒ 跑 \`bash scripts/check_template_sync.sh --update\` 重记 sha"
    echo "   ② 不用改副本 ⇒ 也跑 \`--update\`（表示"我看过了，差异是有意的"）"
    echo "   ⛔ **别把 --update 当"消红按钮"** —— 它记的是"人确认过"，不是"自动同步"。"
    return 1
  fi
  echo "✅ 包内快照与源文件一致（记录的 sha 全部对上）。"
  return 0
}

# ── 重记 sha ───────────────────────────────────────────────────────────────
do_update() {
  local tmp; tmp="$(mktemp)"
  {
    echo "# template-manifest.txt —— 「可移植包」里每份快照【源文件】的 sha256"
    echo "#"
    echo "# 格式： <sha256>  <源文件>  ->  <包内副本>"
    echo "# ⚠️ 改这个文件【只能】通过 bash scripts/check_template_sync.sh --update"
    echo "#    （它的含义是「人已经确认过副本和源之间的差异是有意的」）"
    echo "# 🔴 别手改 —— 手改的值下次源一动就假绿。"
    echo "#"
    while IFS= read -r line; do
      # shellcheck disable=SC2086
      set -- ${line}
      local src="$2" dst="$3"
      if [ -f "${REPO}/${src}" ]; then
        echo "$(shasum -a 256 "${REPO}/${src}" | awk '{print $1}')  ${src}  ->  ${dst}"
      else
        echo "🔴 源不在: ${src}" >&2
      fi
    done < <(read_pairs "$MANIFEST")
  } > "$tmp"
  mv "$tmp" "$MANIFEST"
  echo "✅ 已重记 ${MANIFEST}"
}

# ── 自测：**必须能测出「不成立」** ───────────────────────────────────────────
do_self_test() {
  local pass=0 fail=0 tmp repo
  tmp="$(mktemp -d)"; repo="${tmp}/repo"
  mkdir -p "${repo}/src" "${repo}/pkg"
  printf 'a\n' > "${repo}/src/a.sh"
  printf 'A\n' > "${repo}/pkg/a.sh"
  : > "${repo}/pkg/.keep"

  set +u
  read_pairs() { grep -vE '^\s*(#|$)' "$1" | awk '{print $1, $2, $4}'; }

  # T1 记完之后 ⇒ 绿
  printf '%s  src/a.sh  ->  pkg/a.sh\n' "$(shasum -a 256 "${repo}/src/a.sh" | awk '{print $1}')" > "${repo}/m.txt"
  do_check "${repo}/m.txt" "$repo" >/dev/null 2>&1
  if [ $? -eq 0 ]; then echo "  ✅ T1 记录一致 ⇒ 绿"; pass=$((pass+1));
  else echo "  🔴 T1 期望绿"; fail=$((fail+1)); fi

  # T2 源文件改了 ⇒ 必须红（这正是要拦的漂移）
  printf 'changed\n' > "${repo}/src/a.sh"
  out="$(do_check "${repo}/m.txt" "$repo" 2>&1)"; rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "src/a.sh"; then
    echo "  ✅ T2 源改了 ⇒ 红，且指名 src/a.sh"; pass=$((pass+1));
  else echo "  🔴 T2 期望红并指名，实际 rc=${rc}"; fail=$((fail+1)); fi

  # T3 重记之后 ⇒ 回绿（证明 T2 钉的真是那个 sha）
  printf '%s  src/a.sh  ->  pkg/a.sh\n' "$(shasum -a 256 "${repo}/src/a.sh" | awk '{print $1}')" > "${repo}/m.txt"
  if do_check "${repo}/m.txt" "$repo" >/dev/null 2>&1; then
    echo "  ✅ T3 重记后 ⇒ 回绿"; pass=$((pass+1));
  else echo "  🔴 T3 重记后仍红"; fail=$((fail+1)); fi

  # T4 副本被删 ⇒ 必须红（不是"跳过"）
  rm -f "${repo}/pkg/a.sh"
  if do_check "${repo}/m.txt" "$repo" >/dev/null 2>&1; then
    echo "  🔴 T4 副本没了却仍绿"; fail=$((fail+1));
  else echo "  ✅ T4 副本不见 ⇒ 红"; pass=$((pass+1)); fi

  set -u
  rm -rf "$tmp"
  echo
  echo "结果: ${pass} 通过 / ${fail} 失败"
  [ "$fail" -eq 0 ]
}

case "$MODE" in
  update)    do_update ;;
  self-test) do_self_test; exit $? ;;
  check)
    if [ ! -f "$MANIFEST" ]; then
      echo "⚠️ ${MANIFEST} 不在 ⇒ 本门【未跑】"; exit 3
    fi
    do_check "$MANIFEST" "$REPO"; exit $?
    ;;
esac
