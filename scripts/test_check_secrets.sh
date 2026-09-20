#!/usr/bin/env bash
# ============================================================================
# 凭据门 · 回归测试 —— 断言【退出码】，不断言文案
# ============================================================================
#
# ⚠️ 为什么断言退出码、不断言文案（2026-09-20）:
#   门自己的判据就是"命中即 exit 1 中止" ⇒ **退出码才是门的语义**。
#   文案是给人读的;拿文案当判据,改一个词测试就假红/假绿。
#   （起因见 docs/复盘/2026-09-20-查不到不等于不存在.md：那次我锁错了靶子。）
#
# ⚠️ 为什么用 git/grep shim 而不是真造一个坏仓库:
#   要复现的是【环境不对劲】时的行为 —— 真把仓库弄坏才能测的话，就没人会去测它。
#   shim 只改 `git diff --cached` / `grep` 的行为，其余照旧。
#
# 用法: bash scripts/test_check_secrets.sh
#   exit 0 = 全部通过 · exit 1 = 有用例失败
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$REPO_ROOT/scripts/check_secrets.sh"
REAL_GIT="$(command -v git)"
REAL_GREP="$(command -v grep)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# 跑门，返回退出码（丢弃输出，只关心码）
run_gate() { PATH="$1:$PATH" bash "$GATE" >/dev/null 2>&1; echo $?; }

# ---------------------------------------------------------------- shim 工厂
# $1 = 目录 · $2 = diff --cached 的行为(ok|fail-fast|fail-partial) · $3 = grep 是否可用(yes|no)
make_shims() {
    local dir="$1" diffmode="$2" grepmode="${3:-yes}"
    mkdir -p "$dir"
    cat > "$dir/git" <<EOF
#!/bin/bash
case "\$*" in
  *"diff --cached"*)
    case "$diffmode" in
      ok)           exec "$REAL_GIT" "\$@" ;;
      fail-fast)    echo "fatal: unable to read index" >&2; exit 128 ;;
      fail-partial) printf '+benign\n'; echo "fatal: unable to read index" >&2; exit 128 ;;
    esac ;;
  *) exec "$REAL_GIT" "\$@" ;;
esac
EOF
    chmod +x "$dir/git"
    if [ "$grepmode" = "no" ]; then
        # grep 一律失败 —— 模拟"模式匹配机制本身坏了"
        printf '#!/bin/bash\nexit 2\n' > "$dir/grep"; chmod +x "$dir/grep"
    fi
}

echo "凭据门 · 回归测试"
echo "门 = $GATE"
echo

# ---------------------------------------------------------------- T1 正向
# 门在正常环境下必须仍然可用（否则这个修复本身就是坏的）
S1="$TMP/s1"; make_shims "$S1" ok
rc=$(run_gate "$S1")
[ "$rc" -eq 0 ] && ok "T1 正常环境 ⇒ exit 0（门仍可用）" \
                || bad "T1 正常环境 ⇒ exit ${rc}（应为 0 —— 修复引入了假红）"

# ------------------------------------------------- T2 环境坏：git diff 直接失败
# 回归用例：本次修的缺陷。修复前它 exit 0（假通过）。
S2="$TMP/s2"; make_shims "$S2" fail-fast
rc=$(run_gate "$S2")
[ "$rc" -ne 0 ] && ok "T2 git diff 失败 ⇒ exit ${rc}（非 0 = 不当通过）" \
                || bad "T2 git diff 失败 ⇒ exit 0 ⚠️ 假通过（本次要修的缺陷）"

# ------------------------------------- T3 环境坏：git diff 输出一部分后才失败
# 这个变体最危险：它打印的是【货真价实】的 ✅ 通过，靠看输出发现不了。
S3="$TMP/s3"; make_shims "$S3" fail-partial
rc=$(run_gate "$S3")
[ "$rc" -ne 0 ] && ok "T3 git diff 部分输出后失败 ⇒ exit ${rc}（非 0）" \
                || bad "T3 git diff 部分输出后失败 ⇒ exit 0 ⚠️ 绿得毫无破绽"

# ------------------------------------------- T4 匹配机制坏：grep 全失败（自证）
# 判据能说"没查到"的前提是：它【抓得住已知该命中的东西】。
S4="$TMP/s4"; make_shims "$S4" ok no
rc=$(run_gate "$S4")
[ "$rc" -ne 0 ] && ok "T4 模式匹配机制失灵 ⇒ exit ${rc}（自证生效）" \
                || bad "T4 模式匹配机制失灵 ⇒ exit 0 ⚠️ 自证没生效，门是瞎的"

# ------------------------------------ T5 合法空集：暂存区真的为空 ⇒ 必须 exit 0
# ⚠️ 这一条是防【矫枉过正】：不许把"合法的空"也判成失败。
#    （脚本是 set -uo pipefail，暂存区只有删除行时 grep 会返回 1 —— 若拿管道状态判失败，
#      这里就会假红。参见脚本 v1→v2 记过的同一个坑。）
S5="$TMP/s5"; mkdir -p "$S5"
cat > "$S5/git" <<EOF
#!/bin/bash
case "\$*" in
  *"diff --cached"*) exit 0 ;;   # 成功、且输出为空
  *) exec "$REAL_GIT" "\$@" ;;
esac
EOF
chmod +x "$S5/git"
rc=$(run_gate "$S5")
[ "$rc" -eq 0 ] && ok "T5 合法的空暂存区 ⇒ exit 0（未矫枉过正）" \
                || bad "T5 合法的空暂存区 ⇒ exit ${rc}（应为 0 —— 把'合法的空'判成了失败）"

# --------------------------------- T6 反向对照:门对【合成泄漏】必须仍然报红
# ⚠️ 只证明"该绿的不红了"是不够的 —— 还必须证明"**该红的仍然红**"。
#    否则"修复"可能只是把门改瞎了(比如 exit 2 写成了无条件 exit 2)。
#    ⛔ 样本必须**运行时拼接**:写成字面量的话,本文件自己会被门拦下(门自噬)。
TOK="ghp_$(printf 'B%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20)"
S6="$TMP/s6"; mkdir -p "$S6"
cat > "$S6/git" <<EOF
#!/bin/bash
case "\$*" in
  *"diff --cached"*) printf '+token=%s\n' "$TOK"; exit 0 ;;
  *) exec "$REAL_GIT" "\$@" ;;
esac
EOF
chmod +x "$S6/git"
rc=$(run_gate "$S6")
[ "$rc" -ne 0 ] && ok "T6 合成泄漏样本 ⇒ exit ${rc}（该红的仍然红）" \
                || bad "T6 合成泄漏样本 ⇒ exit 0 ⚠️ 门已经抓不住了 —— 修复把门改瞎了"

echo
echo "结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] || { echo "⛔ 有用例失败"; exit 1; }
echo "✅ 全部通过"
