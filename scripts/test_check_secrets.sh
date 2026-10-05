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
#
# ──────────────────────────────────────────────────────────────────
# 🔴 2026-10-05 加（批 4 · `DEC-080`）：**先摘掉调用方可能带进来的降级开关**
#
#     unset SECRETS_GATE_ALLOW_NO_ENV
#
# ⚠️ **实测踩出来的**（把本文件接进 CI 的那一步）：
#    `ci.yml` 的 env 段里有 `SECRETS_GATE_ALLOW_NO_ENV: "1"` —— CI 的新鲜检出**没有 `.env`**
#    （gitignore），不显式降级的话凭据门自己就以 exit 2 红掉；`ci-local.sh` 又**逐字**把那段
#    env 注进它执行的环境。⇒ 本文件在**同一个环境里**被调用时，那条开关会顺着环境进来，
#    把 **T7「无 .env ⇒ 不得当作通过」直接洗成 exit 0**。
#    实测两个结果：`本机 17 通过 / 0 失败` ↔ `ci-local 16 通过 / 1 失败`（红的正是 T7）。
#
# ⇒ **用例必须自足**：默认环境 = 调用方不额外给东西；**需要降级的用例自己显式设**
#    （T8 / T17 就是这么写的，⛔ 别改成靠环境）。
#    ⚠️ 这与文件头那句「为什么用 shim + 临时仓根」是同一条要求：**别让外部环境决定结论**。
# 📌 判据（可打印）：`SECRETS_GATE_ALLOW_NO_ENV=1 bash scripts/test_check_secrets.sh`
#    ⇒ 与本文件不带该变量时**结果相同**（都 17 通过 / 0 失败）。
unset SECRETS_GATE_ALLOW_NO_ENV

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

# 造 shim 目录 —— 给 `--diff <range>` 用（2026-10-05 加 · `DEC-076`）。
# ⚠️ 上面那个 make_shims() 只匹配 *"diff --cached"*，而 `--diff` 发出去的是
#    `git diff <range> -U0`（**三点**范围），匹配不上 ⇒ 落到它自己的 `*)` 分支去【真跑 git】。
# 🔴 这里**故意只认三点范围** `*"..."*`，⛔ 不写成 `*"diff "*`：
#    `*"diff "*` 会把 `git diff --cached` **也**接住 ⇒ 用例在"`--diff` 还没实现"时
#    **撞巧变绿**（落进 staged 分支照样拿到 payload）⇒ 那就不算"因该原因而红"了。
#    只认 `...` ⇒ 实现前这些用例必红（真跑 git 会失败），实现后才绿。
# $1=目录 · $2=行为：ok/empty/delonly/fail · $3=ok 时那行"新增行"的内容
make_diff_shims() {
    local dir="$1" dmode="$2" payload="${3:-+benign line}"
    mkdir -p "$dir"
    # 🔴 这个 heredoc **不加引号**（要展开 `$dmode`/`$payload`）⇒ 体内 **反引号会被当命令替换执行**、
    #    **裸 `$` 会被当变量展开**。⛔ 体内一律不许出现反引号；`$*` 必须写成 `\$*`。
    #    📌 这条是**实测踩出来的**（2026-10-05）：本函数体内一句**注释**里写了 `` `git diff --cached` ``，
    #    生成 shim 时它被真的执行了 ⇒ 整个暂存区 diff(59.5KB)被塞进 shim 正文、
    #    把 `case` 结构冲烂 ⇒ shim 一跑就是 **bash 语法错误 = exit 2**
    #    ⇒ T11–T17 集体假红（而 T13/T15 那两条"期望 exit 2"的用例**反倒撞巧变绿**）。
    #    ⚠️ 与 `scripts/ci-local.sh` 那次(双引号里的反引号被执行 · `DEC-076`)是**同一个坑**。
    cat > "$dir/git" <<EOF
#!/bin/bash
case "\$*" in
  *"..."*)
    case "$dmode" in
      ok)      printf '%s\n' '$payload'; exit 0 ;;
      empty)   exit 0 ;;
      delonly) printf -- '--- a/x\n+++ b/x\n-old-secret-line\n'; exit 0 ;;
      fail)    echo "fatal: bad revision" >&2; exit 128 ;;
    esac ;;
  # 🔴 未预期的调用（实现前 = 门还在发「diff --cached」）⇒ 回**良性空**，⛔ 不回真 git。
  #    回真 git 会"以失败告终"也报 exit 2 ⇒ 与「范围取不到」的 2 **分不开** ⇒
  #    T13/T15 那类断言 exit 2 的用例就会**撞巧变绿**。回良性空则：
  #    门一路跑到结论行 ⇒ T16 能真的测到那句覆盖度声明（红在正确的地方）。
  *) echo "[shim] ⚠️ 未预期的 git 调用: \$*" >&2; exit 0 ;;
esac
EOF
    chmod +x "$dir/git"
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

# =====================================================================
# T11–T16：【--diff <range>】模式（2026-10-05 加 · `DEC-076` · 为把凭据门接进 CI）
# ⚠️ 合成样本一律**运行时拼接** —— 写字面量会让本文件【自己命中自己的模式】(门自噬)，
#    这条纪律文件开头已有；下面 T12 就是那个负控。
# =====================================================================

# ------------------- T11 --diff 干净范围(只有普通新增行) ⇒ exit 0
# ⚠️ 与 T8 同理，**必须附带断言文案** —— 只看退出码分不开"这真走了 --diff"
#    与"它落回 staged 模式、又恰好扫了个空"。
# ⛔ 锚点必须是**范围字符串本身**：'新增行' 三个字 **staged 分支也有**（见 112 行），
#    拿它当锚点等于没锚（本条第一版就是这么错的）。
R11="$TMP/r11"; S11="$TMP/s11"; make_root "$R11" yes yes; make_diff_shims "$S11" ok '+print("hello")'
out11=$(run_gate_out "$R11" "$S11" "--diff origin/main...HEAD"); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out11" | grep -qF "origin/main...HEAD"; then
    ok "T11 --diff 干净范围 ⇒ exit 0（该绿的不红），且确认扫描范围就是传入的那个范围"
else
    bad "T11 --diff 干净范围 ⇒ exit ${rc}；输出回显了传入范围? $(printf '%s' "$out11" | grep -cF 'origin/main...HEAD') 次"
fi

# ------------------- T12 【负控】范围内含合成泄漏 ⇒ exit 1（证明新增行【确实被扫】）
# ⛔ 若本条变绿(exit 0)，说明"范围没扫到东西"被静默当成了通过 —— 正是要防的假绿。
DTOK="ghp_$(printf 'C%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20)"
R12="$TMP/r12"; S12="$TMP/s12"; make_root "$R12" yes yes; make_diff_shims "$S12" ok "+token=$DTOK"
rc=$(run_gate "$R12" "$S12" "--diff origin/main...HEAD")
[ "$rc" -eq 1 ] && ok "T12 --diff 范围内合成泄漏 ⇒ exit 1（新增行确实被扫 —— 负控）" \
                || bad "T12 --diff 范围内合成泄漏 ⇒ exit ${rc}（应为 1；0 = 新增行没被扫/静默空跑）"

# ------------------- T13 范围取不到(浅克隆/范围写错) ⇒ exit 2（⛔ 不许静默变绿）
# ⚠️ 同样要看文案：'扫描没有执行' 是**这一支**的话；别的分支出错也报 2，靠码分不开。
R13="$TMP/r13"; S13="$TMP/s13"; make_root "$R13" yes yes; make_diff_shims "$S13" fail
out13=$(run_gate_out "$R13" "$S13" "--diff origin/main...HEAD"); rc=$?
if [ "$rc" -eq 2 ] && printf '%s' "$out13" | grep -q "扫描没有执行"; then
    ok "T13 --diff 范围取不到 ⇒ exit 2（⛔ 没扫成 ≠ 通过），且确认是【扫描没有执行】那一支"
else
    bad "T13 --diff 范围取不到 ⇒ exit ${rc}（应为 2；0 = 把'没扫成'当成了通过）；文案含'扫描没有执行'? $(printf '%s' "$out13" | grep -c '扫描没有执行') 次"
fi

# ------------------- T14 范围里【只有删除行】⇒ exit 0（未把"合法的空"判成失败）
R14="$TMP/r14"; S14="$TMP/s14"; make_root "$R14" yes yes; make_diff_shims "$S14" delonly
out14=$(run_gate_out "$R14" "$S14" "--diff origin/main...HEAD"); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out14" | grep -qF "origin/main...HEAD"; then
    ok "T14 --diff 只有删除行 ⇒ exit 0（删密钥是好事，不该拦）"
else
    bad "T14 --diff 只有删除行 ⇒ exit ${rc}（应为 0）；走了 --diff 那支? $(printf '%s' "$out14" | grep -cF 'origin/main...HEAD') 次"
fi

# ------------------- T15 --diff 缺范围参数 ⇒ exit 2（用法错误不得当作通过）
# ⚠️ 同上，要认那句「用法错误」—— 否则"缺参数"和"范围取不到"全都是 2，测不出是哪一条。
R15="$TMP/r15"; S15="$TMP/s15"; make_root "$R15" yes yes; make_diff_shims "$S15" ok
out15=$(run_gate_out "$R15" "$S15" "--diff"); rc=$?
if [ "$rc" -eq 2 ] && printf '%s' "$out15" | grep -q "用法错误"; then
    ok "T15 --diff 缺范围 ⇒ exit 2（用法错误不得当作通过）"
else
    bad "T15 --diff 缺范围 ⇒ exit ${rc}（应为 2）；文案含'用法错误'? $(printf '%s' "$out15" | grep -c '用法错误') 次"
fi

# ------------------- T16 【覆盖度】有 .env、无 denylist ⇒ 只许声明 覆盖 ①③
# 测的是【过度声明的回归】：CI 恰恰是那个【没有 .secret-denylist】的环境(它被 gitignore)。
R16="$TMP/r16"; S16="$TMP/s16"; make_root "$R16" yes no; make_diff_shims "$S16" ok
out16=$(run_gate_out "$R16" "$S16" "--diff origin/main...HEAD")
if printf '%s' "$out16" | grep -q "覆盖 ①③" && ! printf '%s' "$out16" | grep -q "覆盖 ①②③"; then
    ok "T16 无 denylist ⇒ 结论声明【覆盖 ①③】，⛔ 不再谎称覆盖 ②"
else
    bad "T16 无 denylist ⇒ 覆盖度声明错：含'覆盖 ①③' $(printf '%s' "$out16" | grep -c '覆盖 ①③') 次 · 含'覆盖 ①②③' $(printf '%s' "$out16" | grep -c '覆盖 ①②③') 次"
fi

# ------------------- T17 🔴【**CI 的真实形状**】无 .env + 无 denylist + 降级开关
# ⚠️ T16 测的是"**有** .env、没 denylist" ⇒ `覆盖 ①③`。
#    **CI 不是这个形状** —— 它的新鲜检出里 **`.env` 和 `.secret-denylist` 都没有**（都被 gitignore）
#    ⇒ 覆盖度只能是 **`③`**。
#    📌 本条是**实测逼出来的**：我原先在 `DEC-076` 里把 CI 的覆盖度写成了 `①③`（**错了**），
#       真跑一遍 CI 形状才发现是 `③`。⇒ 这条测的就是那个真形状，⛔ 别再按想象写。
#    ⚠️ **诚实交代**：本条**第一次跑就是绿的**（实现先于它）—— 它不是 TDD 先红后绿，
#       是**给一个我刚刚描述错的配置上的回归钉**。
R17="$TMP/r17"; S17="$TMP/s17"; make_root "$R17" no no; make_diff_shims "$S17" ok
out17=$(PATH="$S17:$PATH" SECRETS_GATE_ALLOW_NO_ENV=1 bash "$R17/scripts/check_secrets.sh" \
        --diff origin/main...HEAD 2>&1); rc17=$?
if [ "$rc17" -eq 0 ] \
   && printf '%s' "$out17" | grep -q "覆盖 ③" \
   && ! printf '%s' "$out17" | grep -q "覆盖 ①" \
   && ! printf '%s' "$out17" | grep -q "覆盖 ①②③"; then
    ok "T17 🔴 CI 真实形状(无 .env 无 denylist) ⇒ exit 0，覆盖度只许写【③】"
else
    bad "T17 CI 真实形状 ⇒ exit ${rc17}；含'覆盖 ③' $(printf '%s' "$out17" | grep -c '覆盖 ③') 次 · 含'覆盖 ①' $(printf '%s' "$out17" | grep -c '覆盖 ①') 次"
fi

# ------------------- T18 🔴 `--selftest`：**这道门自己还抓不抓得住**
# 📄 出处：待办总表 §五·5 · `docs/复盘/2026-09-17-一道硬币做的门.md`
# ⚠️ 它与上面 T4 那个"自证"不是一回事：T4 是**每次跑一遍**（挡"机制整体失灵"），
#    本条是「**大载荷 × 连跑 N 次**」，专抓 v4 那种**概率性**漏报。
# ⚠️ 冷启动成本 ~1.5s（10 次 × 6 模式 × 256 KiB）—— 这是它唯一"贵"的地方，别嫌。
# 📌 判据（可打印）：把门里的 `match_re() { grep -E -- "$1" >/dev/null; }` 改成 `grep -E -q`
#    ⇒ 本条**必红**（实测 120/120 次漏报）。
GATE_N=10
out18=$(bash "$GATE" --selftest "$GATE_N" 2>&1); rc18=$?
if [ "$rc18" -eq 0 ]; then
    ok "T18 --selftest（${GATE_N} 次）⇒ exit 0（门还抓得住）"
else
    bad "T18 --selftest ⇒ exit ${rc18}（0 才对）；$(printf '%s' "$out18" | tail -1)"
fi

echo
echo "结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] || { echo "⛔ 有用例失败"; exit 1; }
echo "✅ 全部通过"
