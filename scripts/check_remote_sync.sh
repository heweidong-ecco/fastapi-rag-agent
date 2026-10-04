#!/usr/bin/env bash
#
# check_remote_sync.sh —— **三方比对**：本地分支 / 本地视图 `origin/*` / **远端真值**
#
# ## 它治什么病
#
# `docs/复盘/2026-09-20-同源的两个输入不能互相作证.md`——
# 我当时判「本地 main 与远端同步」用的是：
#
#     [ "$(git rev-parse main)" = "$(git rev-parse origin/main)" ]
#
# 🔴 **`main` 与 `origin/main` 都是【本地仓库的视图】** ⇒ 它们相等**只说明本地自洽**，
#    不说明与远端一致。而当时 `git fetch` 已经失败了 ⇒ **两个输入来自同一个陈旧快照**、
#    比较**必然"相等"** ⇒ 我打印了 `✅ 已同步`，**实际落后远端一个 commit**。
#
# ⇒ 本脚本把那条判据**从"写在文档里"变成"一个动作"**（复盘 §三 行动项 2）。
#    复盘自己写着：「⚠️ 按本仓已三次的教训，**只写在文档里等于没写**」。
#
# ## 三方是哪三方
#
# | 记号 | 是什么 | 怎么取 | 新鲜度由谁保证 |
# |---|---|---|---|
# | **L** local | 本地分支 | `git rev-parse refs/heads/<b>` | 无（就是本地现状） |
# | **V** view | 本地**视图** `origin/<b>` | `git rev-parse refs/remotes/origin/<b>` | 🔴 **上一次 `git fetch` 的时刻 —— 会陈旧且不声明** |
# | **R** remote | **远端真值** | `git ls-remote origin refs/heads/<b>` | ✅ **本次真的连上了远端** |
#
# ## 🔴 硬规矩：**取不到真值必须报「未知」，⛔ 不许报绿**
#
# 本脚本最容易的失败模式，**恰好是它要防的那个错**：
# `git ls-remote` 失败时输出为空 ⇒ 若把"空"当成"一致/没问题" ⇒ **又是一个假 ✅**。
# ⇒ **R 取不到时，结论是「⚪ 未知」，退出码 3（⛔ 不是 0）**，并且**说清是哪一步失败的**。
#
# ⚠️ **「R 为空」与「R 取不到」是两件事**，靠 **`git ls-remote` 的退出码**分开：
#   * 退出码 0 + 无输出 ⇒ ✅ **远端确实没有这个分支**（一个确定的答案）
#   * 退出码 ≠ 0        ⇒ ⚪ **连不上 / 认证失败**（→ 未知）
#   📌 复盘里那三次假 ✅ 之一「`ls-remote` 空」，错的正是**没分这两件事**。
#
# ## 💰 成本：**0 次 GitHub REST API 调用**（2026-10-04 实测）
#
# `git ls-remote` 走的是 **git 传输协议**（本仓 `origin` 是 SSH），**不碰 `api.github.com`**。
# 实测：连跑 **5 次** `git ls-remote`，`gh api rate_limit` 的 `used` **仍是 0**。
# ⇒ **一次运行的网络量与一次 `git fetch` 同量级**（本仓每次推送本来就要 fetch）。
# ⚠️ 但**说清这是推理**：GitHub 的自动风控如何判定**不是本脚本能保证的**
#   —— 按本仓规矩「凡说风控，先问一句：**这是 GitHub 说的，还是谁推的？**」：
#   本条是**实测配额 + 同量级推理**，⛔ **不是 GitHub 的承诺**。
#
# ## ⛔ 它不是 CI 门（**故意的**）
#
# 与 `check_doc_links.sh` 那三兄弟**性质不同**：它**需要网络 + 一个能解析的远端**。
# 在 CI 里"本地"就是刚 checkout 出来的那份，**三方恒等 ⇒ 跑了等于没跑**。
# ⇒ 它是**本机收尾工具**（**推完 / 收工前**跑），⛔ **不要挂进 `pre-commit-gates.py`**。
#
# ## 用法
#
#     bash scripts/check_remote_sync.sh              # 默认查当前分支
#     bash scripts/check_remote_sync.sh main         # 查指定分支
#     bash scripts/check_remote_sync.sh --self-test   # 🔴 证明"它真的会红"（⛔ 不连网）
#
# ## 退出码
#
#     0  三方一致（同步）
#     1  不一致（有真问题 —— 见输出里指的那一条）
#     2  用法错误
#     3  ⚪ **未知** —— 取不到远端真值。⛔ **不许把它当成 0 读**
#
set -uo pipefail   # ⚠️ **故意不加 `-e`** —— 本脚本的活就是"分清楚哪一步失败了"，
                   #    用 `-e` 会让失败直接退出、拿不到"是哪一步"的信息。

BRANCH=""
SELF_TEST=0
for a in "$@"; do
  case "$a" in
    --self-test) SELF_TEST=1 ;;
    -h|--help)   sed -n '1,55p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)          echo "未知参数: $a" >&2; exit 2 ;;
    *)           [ -z "${BRANCH}" ] || { echo "只接受一个分支名" >&2; exit 2; }; BRANCH="$a" ;;
  esac
done

# ==================== 判定（**纯函数** —— 所以能自测） ====================
# 入参：L 本地分支 · V 本地视图 · R 远端真值 · R_KNOWN 是否取到了 R
# 出参：往 stdout 打两行 "裁决<TAB>退出码" 与 "说明"
#       ⚠️ 裁决用 ASCII 词（`synced` / `view-stale` / `drift` / `diverged` / `unknown` /
#          `no-local-branch` / `no-remote-branch`），⛔ 不用中文 —— 好让自测逐字比。
verdict_for() {
  local L="$1" V="$2" R="$3" R_KNOWN="$4"

  # 🔴 第一判：真值取不到 ⇒ 立刻「未知」，**不再往下比**
  #    ⛔ 绝不允许"取不到"掉进下面任何一个 ✅ 分支 —— 那就是本脚本要防的假绿。
  if [ "${R_KNOWN}" != "1" ]; then
    echo "unknown	3"
    echo "⚪ 未知 —— 取不到远端真值（ls-remote 连不上或认证失败）。⛔ 这不等于「同步」。"
    return
  fi

  if [ -z "${L}" ]; then
    echo "no-local-branch	1"
    echo "🔴 本地没有分支 refs/heads/${BRANCH}（远端有：${R:0:7}）"
    return
  fi
  if [ -z "${R}" ]; then
    # ⚠️ 这是"确定的事实"（连上了、远端就是没有），⛔ 不是"取不到"
    echo "no-remote-branch	1"
    echo "🔴 远端确实没有 refs/heads/${BRANCH}（本地在 ${L:0:7} —— 还没推过？）"
    return
  fi

  if [ "${L}" = "${V}" ] && [ "${V}" = "${R}" ]; then
    echo "synced	0"
    echo "✅ 三方一致 —— 本地 / 本地视图 / 远端真值 都是 ${L:0:7}"
  elif [ "${L}" = "${V}" ] && [ "${V}" != "${R}" ]; then
    # 🔴 **这就是复盘记的那个病**：L==V 是"本地自洽"，**不携带远端信息**
    echo "view-stale	1"
    echo "🔴 本地视图陈旧 —— 本地与 origin/${BRANCH} 都是 ${L:0:7}，而远端真值是 ${R:0:7}。"
    echo "   （⚠️ L==V 只说明**本地自洽**，⛔ 不代表与远端一致 —— 上一次 fetch 没成功）"
  elif [ "${L}" != "${V}" ] && [ "${V}" = "${R}" ]; then
    echo "drift	1"
    echo "🟡 本地分支与远端不同步 —— 本地 ${L:0:7} / 远端 ${R:0:7}（视图是对的）"
  else
    echo "diverged	1"
    echo "🔴 三者互不一致 —— 本地 ${L:0:7} / 视图 ${V:0:7} / 远端 ${R:0:7}"
  fi
}

# ==================== 自测：**证明它真的会红** ====================
# 📌 本仓立场（`DEC-061` 幽灵锚点）：**一条测不出"不成立"的守卫 = 没有守卫**。
#    ⇒ 逐个走一遍每个裁决分支，⛔ 不连网、⛔ 不改任何东西。
if [ "${SELF_TEST}" = "1" ]; then
  echo "=== 自测：逐个走一遍裁决分支（⛔ 不连网） ==="
  aaa="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  bbb="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  fails=0
  expect() {  # $1=说明 $2=期望裁决 $3..=入参
    local what="$1" want="$2"; shift 2
    local got; got="$(verdict_for "$@" | head -1 | cut -f1)"
    if [ "${got}" = "${want}" ]; then
      printf '  ✅ %-22s ⇒ %s\n' "${what}" "${got}"
    else
      printf '  🔴 %-22s ⇒ 期望 %s，实得 %s\n' "${what}" "${want}" "${got}"; fails=$((fails+1))
    fi
  }
  BRANCH=selftest
  expect "三方一致"            synced           "$aaa" "$aaa" "$aaa" 1
  expect "视图陈旧（复盘那个病）" view-stale       "$aaa" "$aaa" "$bbb" 1
  expect "本地落后/领先"        drift            "$aaa" "$bbb" "$bbb" 1
  expect "三者互不一致"         diverged         "$aaa" "$bbb" "ccc" 1
  expect "🔴 真值取不到 ⇒ 未知"  unknown          "$aaa" "$aaa" ""    0
  expect "真值取不到 ⇒ 未知②"   unknown          "$aaa" ""    ""    0
  expect "远端确实没这个分支"    no-remote-branch "$aaa" ""    ""    1
  expect "本地没这个分支"        no-local-branch  ""     ""    "$bbb" 1
  echo
  if [ "${fails}" = "0" ]; then
    echo "✅ 自测通过（8/8）—— ⭐ 尤其是「真值取不到 ⇒ unknown，⛔ 不是 synced」这条："
    echo "   它是本脚本唯一存在的理由，也是它最容易自己犯的错。"
    exit 0
  fi
  echo "🔴 自测失败 ${fails} 条 —— 判决逻辑坏了，⛔ 别信它任何输出。" >&2
  exit 1
fi

# ==================== 正式运行 ====================
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "❌ 不在 git 仓里。" >&2; exit 2; }
[ -n "${BRANCH}" ] || BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ -n "${BRANCH}" ] || { echo "❌ 取不到当前分支名（detached HEAD？直接传分支名）。" >&2; exit 2; }

echo "==================== check_remote_sync · ${BRANCH} ===================="

# ---- L：本地分支 ----
L="$(git rev-parse --verify --quiet "refs/heads/${BRANCH}" || true)"

# ---- V：本地视图（⚠️ **会陈旧，且不会自己声明**） ----
V="$(git rev-parse --verify --quiet "refs/remotes/origin/${BRANCH}" || true)"
if [ -n "${V}" ]; then
  v_age="$(git log -1 --format=%cr "${V}" 2>/dev/null || echo '?')"
else
  v_age="（本地没有这个视图 ref）"
fi

# ---- 网络加固：⛔ 不许"静静地挂着" ----
# 🔴 **不加这段会怎样**（2026-10-04 实测推演）：远端不可达时 `git ls-remote` 默认会**一直重试/等待**；
#    而 SSH 若需要口令，会**弹提示把脚本挂死**在交互上 —— 那既不是 ✅ 也不是「未知」，是**没有结论**。
# ⚠️ 本脚本的立场是「取不到 ⇒ **明确报未知**」 ⇒ 必须让它**在有限时间内失败**，而不是挂着。
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o ConnectTimeout=8 -o BatchMode=yes}"
export GIT_HTTP_LOW_SPEED_LIMIT="${GIT_HTTP_LOW_SPEED_LIMIT:-1000}"   # 低于 1000 B/s …
export GIT_HTTP_LOW_SPEED_TIME="${GIT_HTTP_LOW_SPEED_TIME:-10}"       # … 持续 10 秒即放弃

# ---- R：远端真值（⚠️ **退出码必须分开读** —— 见文件头） ----
R=""; R_KNOWN=0
if R_OUT="$(git ls-remote origin "refs/heads/${BRANCH}" 2>&1)"; then
  R="$(printf '%s\n' "${R_OUT}" | awk 'NR==1{print $1}')"
  R_KNOWN=1
else
  # ⚠️ **取最后两行**：git 的报错常是「前半句说原因 + 后半句说下一步」两行，
  #    只取 `tail -1` 会剩下半句（2026-10-04 实测：剩下的是 `and the repository exists.`）
  R_ERR="$(printf '%s\n' "${R_OUT}" | grep -v '^$' | tail -2 | tr '\n' ' ')"
fi

# ---- 打印三方 ----
printf '  L 本地分支   : %s\n' "${L:-（无）}"
printf '  V 本地视图   : %s   %s\n' "${V:-（无）}" "${v_age}"
if [ "${R_KNOWN}" = "1" ]; then
  printf '  R 远端真值   : %s   ✅ 本次真的连上了远端\n' "${R:-（远端无此分支）}"
else
  printf '  R 远端真值   : ⚪ 取不到 —— %s\n' "${R_ERR:-（ls-remote 失败）}"
fi

# ---- ahead / behind ----
# 🔴 **2026-10-04 自纠**：这里原先写「左边=本地独有 / 右边=远端独有」—— **那句话是假的**。
#   `branch...origin/branch` 比的是 **本地 vs 【本地视图】**，⛔ **不是**远端。
#   ⚠️ 而"拿本地视图冒充远端"**正是本脚本唯一存在的理由** —— 我把同一个病又写在了自己的输出里。
#   ⇒ 改成明确标「**⛔ 不是远端**」，并在视图陈旧时**明确说这个数不可用**（要真数得先 fetch）。
if [ -n "${L}" ] && [ -n "${V}" ]; then
  ab="$(git rev-list --left-right --count "${BRANCH}...origin/${BRANCH}" 2>/dev/null || echo '?')"
  printf '  本地 vs 视图 : %s  （左边=本地独有 / 右边=**视图**独有 —— ⛔ 不是远端）\n' "${ab}"
  if [ "${V}" != "${R}" ] && [ "${R_KNOWN}" = "1" ]; then
    printf '                 🔴 上面那个数**不可用于判断远端** —— 视图是陈旧的；要真数先 `git fetch`\n'
  fi
fi
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  printf '  ⚠️ 工作区     : 有未提交改动 —— 「同步」说的是 commit，⛔ 不含工作区\n'
fi

echo "------------------------------------------------------------------"
# ⚠️ 捕获裁决输出（第一行是 "裁决<TAB>退出码"，其余行是给人看的说明）
VERDICT_OUT="$(verdict_for "${L}" "${V}" "${R}" "${R_KNOWN}")"
RC="$(printf '%s\n' "${VERDICT_OUT}" | head -1 | cut -f2)"
printf '%s\n' "${VERDICT_OUT}" | tail -n +2

echo "------------------------------------------------------------------"
case "${RC}" in
  0) echo "✅ check_remote_sync 通过（退出码 0）。"
     echo "   ⚠️ 它只说「**这一刻**」一致 —— 之后远端一动就不成立了。" ;;
  1) echo "🔴 check_remote_sync 失败（退出码 1）。"
     echo "   ⛔ 别用本地 origin/* 代表远端 —— 先 git fetch，再重跑本脚本核对。" ;;
  3) echo "⚪ check_remote_sync 未知（退出码 3）。"
     echo "   ⛔ **这【不是】通过** —— 按本仓纪律，取不到真值就必须是「未知」，不许退化成绿。"
     echo "      先查网络（判据见 CLAUDE.md「推送节奏」）："
     echo "        curl -sS -o /dev/null -w '%{http_code}\n' --max-time 8 https://github.com   # 000 ⇒ 拦截 ⇒ 换 SSH"
     echo "        ssh -T git@github.com                                                        # 回 Hi <user>! 才算通" ;;
  *) echo "🔴 内部错误：裁决没给出退出码（RC='${RC}'）。" >&2; exit 2 ;;
esac
exit "${RC}"
