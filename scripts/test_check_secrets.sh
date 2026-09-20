#!/usr/bin/env bash
# ============================================================================
# 凭据门 · 回归测试 —— 断言【退出码】，不断言文案
# ============================================================================
#
# ⚠️ 为什么断言退出码、不断言文案（2026-09-20）:
#   门自己的判据就是"命中即 exit 1 中止" ⇒ **退出码才是门的语义**。
#   文案是给人读的;拿文案当判据,改一个词测试就假红/假绿。
#   （唯一例外是 T8：它测的**就是**那句限定语本身,见该用例注释。）
#
# ⚠️ 为什么用 git/grep shim + 临时"仓根"，而不是直接在真仓里跑:
#   ① 要复现的是【环境不对劲】时的行为 —— 真把仓库弄坏才能测的话，就没人会去测它;
#   ② 门从**自己所在路径**推出 REPO_ROOT 并去读 `.env` —— 不搬家就没法测"缺 .env"这一支;
#   ③ 直接跑真仓的话，暂存区里恰好有命中模式的内容就会让 T1 假红（**非自足**）。
#   ⇒ 每个用例都搬到一个临时"仓根"里跑（只有门脚本被 `cp`，不动真仓）。
#
# 用法: bash scripts/test_check_secrets.sh
#   exit 0 = 全部通过 · exit 1 = 有用例失败
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$REPO_ROOT/scripts/check_secrets.sh"
REAL_GIT="$(command -v git)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# 造一个临时"仓根"：只放门脚本的副本，其余靠 shim 控制。
# $1=目录 · $2=有 .env 吗(yes/no) · $3=有 .secret-denylist 吗(yes/no)
make_root() {
    mkdir -p "$1/scripts"
    cp "$GATE" "$1/scripts/check_secrets.sh"
    if [ "$2" = yes ]; then
        printf 'REAL_SECRET=zzq4canaryvaluezzq4\n' > "$1/.env"
    fi
    if [ "$3" = yes ]; then
        printf 'denylist-canary-zzq4\n' > "$1/.secret-denylist"
    fi
}

# 造 shim 目录。
# $1=目录 · $2=git diff --cached 的行为 · $3=git grep 的行为 · $4=grep 是否失灵(yes/no)
make_shims() {
    local dir="$1" dmode="$2" gmode="$3" gbroken="${4:-no}"
    mkdir -p "$dir"
    cat > "$dir/git" <<EOF
#!/bin/bash
case "\$*" in
  *"diff --cached"*)
    case "$dmode" in
      ok)      printf '+benign line\n'; exit 0 ;;
      empty)   exit 0 ;;
      fail)    echo "fatal: unable to read index" >&2; exit 128 ;;
      partial) printf '+benign\n'; echo "fatal: unable to read index" >&2; exit 128 ;;
    esac ;;
  *"grep"*)
    case "$gmode" in
      ok)   exit 0 ;;
      fail) echo "fatal: bad revision" >&2; exit 128 ;;
      none) exit 1 ;;
    esac ;;
  *) exec "$REAL_GIT" "\$@" ;;
esac
EOF
    chmod +x "$dir/git"
    if [ "$gbroken" = yes ]; then
        printf '#!/bin/bash\nexit 2\n' > "$dir/grep"; chmod +x "$dir/grep"
    fi
}

# 跑门，回显退出码。$1=仓根 · $2=shim 目录 · $3=门的模式参数(可空)
run_gate() {
    local root="$1" shims="$2" mode="${3:-}"
    PATH="$shims:$PATH" bash "$root/scripts/check_secrets.sh" $mode >/dev/null 2>&1
    echo $?
}
# 同上，但回显输出（给必须看文案的用例用）
run_gate_out() {
    local root="$1" shims="$2" mode="${3:-}"
    PATH="$shims:$PATH" bash "$root/scripts/check_secrets.sh" $mode 2>&1
}

echo "凭据门 · 回归测试"
echo "门 = $GATE"
echo

# ---------------------------------------------------------------- T1 正向
R1="$TMP/r1"; S1="$TMP/s1"; make_root "$R1" yes yes; make_shims "$S1" ok ok
rc=$(run_gate "$R1" "$S1")
[ "$rc" -eq 0 ] && ok "T1 正常环境 ⇒ exit 0（门仍可用）" \
                || bad "T1 正常环境 ⇒ exit ${rc}（应为 0 —— 修复引入了假红）"

# ------------------------------------------------- T2 环境坏：git diff 直接失败
R2="$TMP/r2"; S2="$TMP/s2"; make_root "$R2" yes yes; make_shims "$S2" fail ok
rc=$(run_gate "$R2" "$S2")
[ "$rc" -ne 0 ] && ok "T2 git diff 失败 ⇒ exit ${rc}（非 0 = 不当通过）" \
                || bad "T2 git diff 失败 ⇒ exit 0 ⚠️ 假通过"

# ------------------------------------- T3 环境坏：git diff 输出一部分后才失败
# 这个变体最危险：修复前它打印的是【货真价实】的 ✅ 通过，靠看输出发现不了。
R3="$TMP/r3"; S3="$TMP/s3"; make_root "$R3" yes yes; make_shims "$S3" partial ok
rc=$(run_gate "$R3" "$S3")
[ "$rc" -ne 0 ] && ok "T3 git diff 部分输出后失败 ⇒ exit ${rc}（非 0）" \
                || bad "T3 git diff 部分输出后失败 ⇒ exit 0 ⚠️ 绿得毫无破绽"

# ------------------------------------------- T4 匹配机制坏：grep 全失败（自证）
# 判据能说"没查到"的前提是：它【抓得住已知该命中的东西】。
R4="$TMP/r4"; S4="$TMP/s4"; make_root "$R4" yes yes; make_shims "$S4" ok ok yes
rc=$(run_gate "$R4" "$S4")
[ "$rc" -ne 0 ] && ok "T4 模式匹配机制失灵 ⇒ exit ${rc}（自证生效）" \
                || bad "T4 模式匹配机制失灵 ⇒ exit 0 ⚠️ 自证没生效，门是瞎的"

# ------------------------------------ T5 合法空集：暂存区真的为空 ⇒ 必须 exit 0
# ⚠️ 防【矫枉过正】：不许把"合法的空"也判成失败。
#    （脚本是 set -uo pipefail，暂存区只有删除行时 grep 返回 1 —— 若拿管道状态判失败，
#      这里就会假红。参见脚本 v1→v2 记过的同一个坑。）
R5="$TMP/r5"; S5="$TMP/s5"; make_root "$R5" yes yes; make_shims "$S5" empty ok
rc=$(run_gate "$R5" "$S5")
[ "$rc" -eq 0 ] && ok "T5 合法的空暂存区 ⇒ exit 0（未矫枉过正）" \
                || bad "T5 合法的空暂存区 ⇒ exit ${rc}（应为 0 —— 把'合法的空'判成了失败）"

# --------------------------------- T6 反向对照:门对【合成泄漏】必须仍然报红
# ⚠️ 只证明"该绿的不红了"是不够的 —— 还必须证明"**该红的仍然红**"。
#    否则"修复"可能只是把门改瞎了(比如 exit 2 写成了无条件 exit 2)。
#    ⛔ 样本必须**运行时拼接**:写成字面量的话,本文件自己会被门拦下(门自噬)。
TOK="ghp_$(printf 'B%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20)"
R6="$TMP/r6"; S6="$TMP/s6"; make_root "$R6" yes yes; mkdir -p "$S6"
cat > "$S6/git" <<EOF
#!/bin/bash
case "\$*" in
  *"diff --cached"*) printf '+token=%s\n' "$TOK"; exit 0 ;;
  *) exec "$REAL_GIT" "\$@" ;;
esac
EOF
chmod +x "$S6/git"
rc=$(run_gate "$R6" "$S6")
[ "$rc" -eq 1 ] && ok "T6 合成泄漏样本 ⇒ exit 1（该红的仍然红，且是「命中」那一码）" \
                || bad "T6 合成泄漏样本 ⇒ exit ${rc}（应为 1 —— 门抓不住了，或错用了别的码）"


# --------------------------- T7 【无 .env】⇒ 不得当作通过（v5→v6 修的那条路径）
# ⚠️ 本条是 v5 的半拉子所在：缺 .env 时 ① 整段不跑，v5 仍打印无限定语的 ✅ 通过 + exit 0。
R7="$TMP/r7"; S7="$TMP/s7"; make_root "$R7" no yes; make_shims "$S7" ok ok
rc=$(run_gate "$R7" "$S7")
out7=$(run_gate_out "$R7" "$S7")
if [ "$rc" -ne 0 ] && ! printf '%s' "$out7" | grep -q "✅ 凭据门: 通过"; then
    ok "T7 无 .env ⇒ exit ${rc}，且【不再打印】无限定语的 ✅ 通过"
else
    bad "T7 无 .env ⇒ exit ${rc}；输出里出现无定语的通过行？$(printf '%s' "$out7" | grep -c '✅ 凭据门: 通过') 次 ⚠️ 半拉子修复"
fi

# ------------------------- T8 显式降级(ALLOW_NO_ENV=1) ⇒ 可 exit 0，但结论必须标注"部分覆盖"
# ⚠️ 本条**故意断言文案** —— 它测的就是那句限定语本身：
#    降级后退出码与"全跑了没命中"相同(都是 0),不靠文案就无从区分。
R8="$TMP/r8"; S8="$TMP/s8"; make_root "$R8" no yes; make_shims "$S8" ok ok
out8=$(PATH="$S8:$PATH" SECRETS_GATE_ALLOW_NO_ENV=1 bash "$R8/scripts/check_secrets.sh" 2>&1); rc8=$?
if [ "$rc8" -eq 0 ] && printf '%s' "$out8" | grep -q "部分覆盖"; then
    ok "T8 显式降级 ⇒ exit 0，且结论标注【部分覆盖】（不会被误读成'全查过了'）"
else
    bad "T8 显式降级 ⇒ exit ${rc8}；结论含'部分覆盖'? $(printf '%s' "$out8" | grep -c '部分覆盖') 次"
fi

# ------------------- T9 【--all 模式】git grep 出错(rc≥2) ⇒ 不得当作通过（补测 v5 改过的分支）
R9="$TMP/r9"; S9="$TMP/s9"; make_root "$R9" yes yes; make_shims "$S9" ok fail
rc=$(run_gate "$R9" "$S9" "--all")
[ "$rc" -ne 0 ] && ok "T9 --all 下 git grep 出错 ⇒ exit ${rc}（非 0）" \
                || bad "T9 --all 下 git grep 出错 ⇒ exit 0 ⚠️ 该分支零覆盖且行为错误"

# ------------------- T10 --all 下 git grep【无匹配】(rc=1) 是【合法的空】⇒ 必须 exit 0
R10="$TMP/r10"; S10="$TMP/s10"; make_root "$R10" yes yes; make_shims "$S10" ok none
rc=$(run_gate "$R10" "$S10" "--all")
[ "$rc" -eq 0 ] && ok "T10 --all 下无匹配(rc=1) ⇒ exit 0（合法的空，未矫枉过正）" \
                || bad "T10 --all 下无匹配 ⇒ exit ${rc}（应为 0 —— 把 git grep 的 rc=1 当成了出错）"

echo
echo "结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] || { echo "⛔ 有用例失败"; exit 1; }
echo "✅ 全部通过"
