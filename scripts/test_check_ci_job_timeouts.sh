#!/usr/bin/env bash
#
# test_check_ci_job_timeouts.sh —— `check_ci_job_timeouts.py` 的回归测试（`§七·2` · 2026-10-08）
#
# ## 为什么要有它
#
# 门**改了却没有用例** ⇒ 下一次谁再把它改瞎，**没人会发现**。
# 本仓立场（`DEC-080`）：**一条测不出「不成立」的守卫 = 没有守卫**。
#
# ## 钉住五条不变量
#
#   1. **全带 ⇒ 0**（T1）
#   2. **缺一个 ⇒ 1，且【点名】**（T2 / T6）—— ⛔ 不是"数条数"，要能说出**是哪个 job**
#   3. **值非法（0 / 非数字）⇒ 1**（T3 / T5）
#   4. 🔴 **解析不出 job ⇒ 2**（T4）—— ⛔ **不许压成 0**
#   5. 🔴 **文件不在 ⇒ 2**（T7）—— 同上："**没能判定**" ≠ "**通过**"
#
# ## ⚠️ 夹具用【真文件】，不拿真 `ci.yml` 当夹具
#
# 拿真 `ci.yml` 测 = 结论随仓里 job 增删而漂（同 `test_check_doc_orphans.sh` 的理由）。
# ⇒ 每例用 `mktemp -d` 造一份**最小** workflow。
#
# 🔴 **heredoc 一律加引号**（`<<'EOF'`）—— 不加引号时 **`$` 与反引号会被 shell 真的展开/执行**
#    （本仓 2026-10-05 一天栽两次：其中一次把 59.5 KB 的 diff 塞进了生成的 shim 里）。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="${HERE}/check_ci_job_timeouts.py"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

PY=python3
[ -x "${HERE}/../venv/bin/python" ] && PY="${HERE}/../venv/bin/python"

PASS=0; FAIL=0
ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

run_gate() { "${PY}" "${GATE}" "$1" >/dev/null 2>&1; echo $?; }

echo "CI 超时门 · 回归测试"
echo "门 = ${GATE}"
echo

cat > "${TMP}/good.yml" <<'EOF'
name: x
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
  b:
    runs-on: ubuntu-latest
    timeout-minutes: 15
EOF

cat > "${TMP}/missing.yml" <<'EOF'
name: x
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
  lonely:
    runs-on: ubuntu-latest
EOF

cat > "${TMP}/zero.yml" <<'EOF'
name: x
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 0
EOF

cat > "${TMP}/garbage.yml" <<'EOF'
name: x
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: abc
EOF

cat > "${TMP}/nojobs.yml" <<'EOF'
name: x
on: push
jobs:
EOF

# ⚠️ 这条钉的是「`jobs:` **之前**的键不许被当成 job」——
#    没有它，一个把 `on:` 下面那些键也收进来的实现会**照样绿**。
cat > "${TMP}/prejobs.yml" <<'EOF'
name: x
on:
  push:
    timeout-minutes: 3
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 7
EOF

rc=$(run_gate "${TMP}/good.yml")
[ "$rc" -eq 0 ] && ok "T1 两个 job 全带 ⇒ exit 0" || bad "T1 exit ${rc}（应为 0）"

rc=$(run_gate "${TMP}/missing.yml")
[ "$rc" -eq 1 ] && ok "T2 有个 job 缺 ⇒ exit 1" || bad "T2 exit ${rc}（应为 1）"

rc=$(run_gate "${TMP}/zero.yml")
[ "$rc" -eq 1 ] && ok "T3 值 = 0 ⇒ exit 1" || bad "T3 exit ${rc}（应为 1）"

rc=$(run_gate "${TMP}/garbage.yml")
[ "$rc" -eq 1 ] && ok "T4 值 = abc ⇒ exit 1" || bad "T4 exit ${rc}（应为 1）"

rc=$(run_gate "${TMP}/nojobs.yml")
[ "$rc" -eq 2 ] && ok "T5 一个 job 都解析不出来 ⇒ exit 2（⛔ 不是 0）" || bad "T5 exit ${rc}（应为 2）"

# 🔴 这里**不能**写成 `if 门 2>&1 | grep -q 'lonely'; then …`：
#    本脚本开了 `set -o pipefail`，而**门在这一例上【故意】退出 1** ⇒
#    管道的退出码取**最右的非零** ⇒ **`grep` 明明成功了，`if` 却走 else**
#    （本机实测踩过：门打出 `· lonely`、`grep` 回 0，用例仍报 ❌）。
#    ⇒ 先把输出**收进变量**，把"跑门"与"看输出"**分成两步**。
out="$("${PY}" "${GATE}" "${TMP}/missing.yml" 2>&1 || true)"
case "$out" in
    *lonely*) ok "T6 缺的那个必须【点名】（lonely）" ;;
    *)        bad "T6 没点名 —— 只会说「有 job 缺」就点不出该改哪一行" ;;
esac

rc=$(run_gate "${TMP}/does-not-exist.yml")
[ "$rc" -eq 2 ] && ok "T7 文件不在 ⇒ exit 2（⛔ 不是 0）" || bad "T7 exit ${rc}（应为 2）"

rc=$(run_gate "${TMP}/prejobs.yml")
[ "$rc" -eq 0 ] && ok "T8 jobs: 之前的键不算 job ⇒ exit 0" || bad "T8 exit ${rc}（应为 0 —— 把 on: 下面的键当 job 了）"

echo
echo "结果: $PASS 通过 / $FAIL 失败"
if [ "$FAIL" -ne 0 ]; then
    echo "⛔ 有用例失败"
    exit 1
fi
echo "✅ 全部通过"
